"""Regression tests for one-click paper analysis scoping."""

import unittest
from unittest.mock import Mock, patch

from app.routers.chat import ChatRequest
from langchain_core.documents import Document
from pymilvus import FunctionType
from rag.factory import HYBRID_INDEX_PARAMS
from rag.retrieval import Retriever


class PaperScopeTests(unittest.TestCase):
    def test_milvus_filter_combines_section_and_paper_scope(self):
        expression = Retriever._build_expr(
            object(),
            None,
            ["method"],
            ["Paper A", "论文B"],
        )

        self.assertEqual(
            expression,
            '(section_type == "method") && '
            '(paper_id == "Paper A" || paper_id == "论文B")',
        )

    def test_cache_scope_separates_papers(self):
        left = Retriever._cache_scope(None, None, ["Paper A"], True, True, True)
        right = Retriever._cache_scope(None, None, ["Paper B"], True, True, True)

        self.assertNotEqual(left, right)

    def test_chat_request_accepts_selected_paper(self):
        request = ChatRequest(query="精读", paper_ids=["Paper A"])

        self.assertEqual(request.paper_ids, ["Paper A"])

    def test_hybrid_index_uses_sparse_bm25_index(self):
        dense, sparse = HYBRID_INDEX_PARAMS

        self.assertEqual(dense["index_type"], "HNSW")
        self.assertEqual(sparse["index_type"], "SPARSE_INVERTED_INDEX")
        self.assertEqual(sparse["metric_type"], "BM25")

    @patch("rag.retrieval.Function")
    def test_hybrid_search_uses_milvus_26_rrf_function(self, function_cls):
        reranker = object()
        function_cls.return_value = reranker
        store = Mock()
        store.similarity_search.return_value = []

        Retriever._hybrid_search(object(), store, "query", 5, 60)

        function_cls.assert_called_once_with(
            name="rrf_reranker",
            function_type=FunctionType.RERANK,
            input_field_names=[],
            params={"reranker": "rrf", "k": 60},
        )
        store.similarity_search.assert_called_once_with(
            "query", k=5, reranker=reranker, fetch_k=5
        )

    def test_parent_expansion_uses_exact_metadata_query(self):
        parent_store = Mock()
        parent_store.collection_name = "papers_parents"
        parent_store._text_field = "text"
        parent_store._primary_field = "pk"
        parent_store._get_output_fields.return_value = ["text", "pk", "chunk_id"]
        parent_store.client.query.return_value = [
            {"text": "parent text", "pk": 7, "chunk_id": "parent-1"}
        ]

        retriever = object.__new__(Retriever)
        retriever._parent_store = parent_store
        child = Document(
            page_content="child text",
            metadata={"chunk_parent_id": "parent-1", "retrieval_relevance": 0.9},
        )

        results = retriever._expand_to_parents([child])

        self.assertEqual(results[0].page_content, "parent text")
        self.assertEqual(results[0].metadata["chunk_id"], "parent-1")
        self.assertEqual(results[0].metadata["retrieval_relevance"], 0.9)
        parent_store.client.query.assert_called_once()
        parent_store.similarity_search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
