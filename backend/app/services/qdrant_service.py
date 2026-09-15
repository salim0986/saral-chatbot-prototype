"""
QdrantService - manages vector storage with hybrid search (dense + sparse).
Uses qdrant-client sync API wrapped in asyncio.to_thread by the caller.
Supports in-memory mode (url=':memory:') for testing.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings
from app.exceptions import QdrantError
from app.services.embedding_service import EmbeddedChunk

# Qdrant sparse index name - must match collection config
SPARSE_VECTOR_NAME = "sparse"


class QdrantService:
    """
    Handles all Qdrant operations: collection setup, upsert, and retrieval.
    Pass url=':memory:' in tests for a zero-infra in-memory instance.
    """

    def __init__(self, url: str | None = None):
        resolved_url = url or settings.qdrant_url
        self.client = QdrantClient(
            location=resolved_url if resolved_url != ":memory:" else None,
            # in-memory: pass no location
            **({} if resolved_url != ":memory:" else {"location": ":memory:"}),
        )
        self.collection_name = settings.qdrant_collection_name

    def ensure_collection(self) -> None:
        """
        Create the Qdrant collection with hybrid-search config if it doesn't exist.
        Dense: 1024-dim cosine. Sparse: BGE-M3 lexical weights.
        """
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection_name in existing:
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=1024,
                distance=Distance.COSINE,
            ),
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: SparseVectorParams(),
            },
        )

    def upsert_chunks(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        """
        Upsert EmbeddedChunk objects into Qdrant.
        Creates the collection if it doesn't exist.
        Each point carries the full chunk metadata in its payload.

        Raises:
            QdrantError: if the upsert fails.
        """
        if not embedded_chunks:
            return

        self.ensure_collection()

        try:
            points = [
                PointStruct(
                    id=ec.chunk.chunk_id,
                    vector={
                        "": ec.dense_vector,         # default dense vector
                        SPARSE_VECTOR_NAME: SparseVector(
                            indices=ec.sparse_indices,
                            values=ec.sparse_values,
                        ),
                    },
                    payload={
                        "chunk_id": ec.chunk.chunk_id,
                        "paper_id": ec.chunk.paper_id,
                        "page_number": ec.chunk.page_number,
                        "section_title": ec.chunk.section_title,
                        "block_index": ec.chunk.block_index,
                        "text": ec.chunk.text,
                        "contains_math": ec.chunk.contains_math,
                        "has_figure": ec.chunk.has_figure,
                        "figure_caption": ec.chunk.figure_caption,
                    },
                )
                for ec in embedded_chunks
            ]
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
        except Exception as exc:
            raise QdrantError(f"Failed to upsert chunks: {exc}") from exc
