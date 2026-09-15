"""
RAG Service - handles dynamic retrieval from Qdrant.
Applies scoring thresholds, floor/ceiling constraints, and math-aware boosting.
"""

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.models.chunk import Chunk
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService


class RAGService:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.qdrant_service = QdrantService()

    def retrieve(self, query: str, paper_id: str, top_k: int = 15, threshold: float = 0.65, min_floor: int = 3) -> list[Chunk]:
        """
        Retrieves relevant chunks for a query from a specific paper.
        """
        # Embed the query
        # Since embed_chunks takes a list of Chunks, we can mock a dummy Chunk to embed just the text
        dummy_chunk = Chunk(chunk_id="", paper_id="", page_number=0, section_title="", block_index=0, text=query, contains_math=False, has_figure=False)
        embedded = self.embedding_service.embed_chunks([dummy_chunk])[0]

        # Check for math keywords in query to enable boosting
        math_keywords = {"equation", "formula", "math", "derive", "calculate", "function", "variable"}
        query_words = set(query.lower().split())
        has_math_intent = bool(query_words & math_keywords)

        # Retrieve from Qdrant
        # We retrieve more than top_k initially to allow for thresholding and boosting
        response = self.qdrant_service.client.query_points(
            collection_name=self.qdrant_service.collection_name,
            query=embedded.dense_vector,
            query_filter=Filter(
                must=[FieldCondition(key="paper_id", match=MatchValue(value=paper_id))]
            ),
            limit=top_k * 2,
            with_payload=True,
        )
        scored_points = response.points

        # Apply math boosting
        if has_math_intent:
            for pt in scored_points:
                if pt.payload.get("contains_math"):
                    pt.score += 0.10

        # Sort by boosted score
        scored_points.sort(key=lambda x: x.score, reverse=True)

        # Apply threshold filtering with floor enforcement
        final_points = []
        for pt in scored_points:
            if pt.score >= threshold or len(final_points) < min_floor:
                final_points.append(pt)
            if len(final_points) == top_k:
                break

        # Convert back to Chunk objects
        chunks = []
        for pt in final_points:
            p = pt.payload
            chunks.append(Chunk(
                chunk_id=p["chunk_id"],
                paper_id=p["paper_id"],
                page_number=p["page_number"],
                section_title=p["section_title"],
                block_index=p["block_index"],
                text=p["text"],
                contains_math=p["contains_math"],
                has_figure=p["has_figure"],
                figure_caption=p.get("figure_caption")
            ))

        return chunks
