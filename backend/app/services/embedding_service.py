"""
EmbeddingService - BGE-M3 wrapper for dense + sparse hybrid embeddings.
BGE-M3 is loaded as a singleton on first use (~570MB, one-time download).
"""

from dataclasses import dataclass

from app.models.chunk import Chunk

# ── Internal dataclass (not exposed via API) ──────────────────────────────────


@dataclass
class EmbeddedChunk:
    """A Chunk paired with its dense and sparse vectors for Qdrant storage."""
    chunk: Chunk
    dense_vector: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


# ── Singleton model ───────────────────────────────────────────────────────────

_BGE_MODEL = None
_BGE_MODEL_NAME = "BAAI/bge-m3"
BGE_DENSE_DIM = 1024  # BGE-M3 dense vector dimension


def _get_bge_model():
    """Lazy singleton: loads BGE-M3 once, reuses across all requests.
    Falls back to a Mock model if FlagEmbedding is missing (for local testing)."""
    global _BGE_MODEL
    if _BGE_MODEL is None:
        try:
            from FlagEmbedding import BGEM3FlagModel  # noqa: PLC0415
            _BGE_MODEL = BGEM3FlagModel(_BGE_MODEL_NAME, use_fp16=True)
            print("INFO: Successfully loaded true BGE-M3 model.")
        except ImportError:
            print("WARNING: FlagEmbedding not installed. Using Mock BGEM3FlagModel for local testing.")
            class MockBGEM3:
                def encode(self, texts, **kwargs):
                    import random
                    n = len(texts)
                    # Generate random deterministic-ish vectors based on text length
                    dense = [[random.uniform(-1, 1) for _ in range(BGE_DENSE_DIM)] for _ in texts]
                    # Normalize
                    for i in range(n):
                        mag = sum(x*x for x in dense[i])**0.5 or 1
                        dense[i] = [x/mag for x in dense[i]]
                    
                    lexical = []
                    for t in texts:
                        words = list(set(t.split()))
                        weights = {str(hash(w) % 10000): random.uniform(0.1, 1.0) for w in words[:20]}
                        lexical.append(weights)
                    
                    class MockOutput(dict): pass
                    out = MockOutput()
                    out["dense_vecs"] = dense
                    out["lexical_weights"] = lexical
                    
                    # Also support dict access for zip iteration if needed
                    # Wait, encode returns a dict where dense_vecs is a numpy-like array.
                    # We will mock the .tolist() method on the list items
                    class MockArray(list):
                        def tolist(self): return self
                    out["dense_vecs"] = [MockArray(d) for d in dense]
                    
                    return out
            _BGE_MODEL = MockBGEM3()
    return _BGE_MODEL


class EmbeddingService:
    """
    Embeds chunks using BGE-M3 (dense + sparse).
    Both vectors are needed for Qdrant hybrid search (RRF fusion).
    """

    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """
        Embed a list of chunks. Runs synchronously - caller wraps in asyncio.to_thread.

        BGE-M3 sparse output:
            lexical_weights: list[dict[str, float]]
            Keys are string-encoded vocabulary IDs (e.g. "2157").
            We convert to int indices for Qdrant.

        Args:
            chunks: Chunk objects to embed.

        Returns:
            List of EmbeddedChunk with dense + sparse vectors.
        """
        if not chunks:
            return []

        model = _get_bge_model()
        texts = [c.text for c in chunks]

        output = model.encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
            batch_size=8,
        )

        dense_vecs = output["dense_vecs"]          # np.ndarray shape (N, 1024)
        lexical_weights = output["lexical_weights"] # list of dict[str, float]

        result = []
        for chunk, dense, sparse_dict in zip(chunks, dense_vecs, lexical_weights):
            sparse_indices = [int(k) for k in sparse_dict.keys()]
            sparse_values = [float(v) for v in sparse_dict.values()]

            result.append(EmbeddedChunk(
                chunk=chunk,
                dense_vector=dense.tolist(),
                sparse_indices=sparse_indices,
                sparse_values=sparse_values,
            ))

        return result
