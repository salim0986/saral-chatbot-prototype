"""
TDD - Phase 2a: RAG Service tests.
Tests the dynamic retrieval logic: threshold filtering, floor/ceiling k, and math boosting.
Qdrant client is mocked to return controlled ScoredPoint results.
"""

from unittest.mock import MagicMock, patch
import pytest
from qdrant_client.models import ScoredPoint

from app.models.chunk import Chunk


class TestRAGRetrieval:

    @patch("app.services.rag_service.EmbeddingService")
    @patch("app.services.rag_service.QdrantService")
    def test_threshold_filtering(self, mock_qdrant_cls, mock_embed_cls):
        # Setup mock Qdrant
        mock_qdrant = MagicMock()
        mock_qdrant_cls.return_value = mock_qdrant
        
        # Mock embedding return
        mock_embed = MagicMock()
        mock_embed.embed_chunks.return_value = [MagicMock(dense_vector=[0.1]*1024, sparse_indices=[1], sparse_values=[1.0])]
        mock_embed_cls.return_value = mock_embed

        from app.services.rag_service import RAGService
        svc = RAGService()

        mock_response = MagicMock()
        mock_response.points = [
            ScoredPoint(id="1", version=1, score=0.9, payload={"chunk_id": "1", "paper_id": "paper1", "page_number": 1, "section_title": "", "block_index": 0, "text": "text1", "contains_math": False, "has_figure": False}),
            ScoredPoint(id="2", version=1, score=0.8, payload={"chunk_id": "2", "paper_id": "paper1", "page_number": 1, "section_title": "", "block_index": 0, "text": "text2", "contains_math": False, "has_figure": False}),
            ScoredPoint(id="3", version=1, score=0.6, payload={"chunk_id": "3", "paper_id": "paper1", "page_number": 1, "section_title": "", "block_index": 0, "text": "text3", "contains_math": False, "has_figure": False}),
            ScoredPoint(id="4", version=1, score=0.5, payload={"chunk_id": "4", "paper_id": "paper1", "page_number": 1, "section_title": "", "block_index": 0, "text": "text4", "contains_math": False, "has_figure": False}),
            ScoredPoint(id="5", version=1, score=0.4, payload={"chunk_id": "5", "paper_id": "paper1", "page_number": 1, "section_title": "", "block_index": 0, "text": "text5", "contains_math": False, "has_figure": False}),
        ]
        mock_qdrant.client.query_points.return_value = mock_response

        chunks = svc.retrieve("test query", "paper1", top_k=10)
        
        assert len(chunks) == 3
        assert chunks[0].chunk_id == "1"
        assert chunks[1].chunk_id == "2"
        assert chunks[2].chunk_id == "3" 

    @patch("app.services.rag_service.EmbeddingService")
    @patch("app.services.rag_service.QdrantService")
    def test_math_aware_boosting(self, mock_qdrant_cls, mock_embed_cls):
        mock_qdrant = MagicMock()
        mock_qdrant_cls.return_value = mock_qdrant
        mock_embed = MagicMock()
        mock_embed.embed_chunks.return_value = [MagicMock(dense_vector=[0.1]*1024, sparse_indices=[], sparse_values=[])]
        mock_embed_cls.return_value = mock_embed

        from app.services.rag_service import RAGService
        svc = RAGService()

        # Query contains math keywords
        query = "Explain the attention equation"
        
        # Return 2 points with same base score, one has math, one doesn't
        mock_response = MagicMock()
        mock_response.points = [
            ScoredPoint(id="1", version=1, score=0.70, payload={"chunk_id": "1", "paper_id": "paper1", "page_number": 1, "section_title": "", "block_index": 0, "text": "text1", "contains_math": False, "has_figure": False}),
            ScoredPoint(id="2", version=1, score=0.70, payload={"chunk_id": "2", "paper_id": "paper1", "page_number": 1, "section_title": "", "block_index": 0, "text": "text2", "contains_math": True, "has_figure": False}),
            ScoredPoint(id="3", version=1, score=0.90, payload={"chunk_id": "3", "paper_id": "paper1", "page_number": 1, "section_title": "", "block_index": 0, "text": "text3", "contains_math": False, "has_figure": False}),
        ]
        mock_qdrant.client.query_points.return_value = mock_response

        chunks = svc.retrieve(query, "paper1", top_k=5)
        
        assert chunks[0].chunk_id == "3"
        assert chunks[1].chunk_id == "2"
        assert chunks[2].chunk_id == "1"
