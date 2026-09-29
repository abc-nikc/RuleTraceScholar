"""Retrieval module: hybrid search, reranking, evidence diversity, parent recall."""

import json
import logging
import re
from typing import Optional
from langchain_core.documents import Document
from langchain_milvus import Milvus
from pymilvus import Function, FunctionType
from .cache import RetrievalCache
from .factory import EmbeddingService, RerankerService, MilvusStoreFactory
from explainability.engine import logistic_relevance

logger = logging.getLogger(__name__)

RERANK_FETCH_MULTIPLIER = 2
DEDUP_FETCH_MULTIPLIER = 2


class Retriever:
    """Hybrid retriever with BM25+dense fusion, reranking, and parent-child recall."""

    def __init__(
        self,
        embedding_model: str = "BAAI/bge-small-en-v1.5",
        reranker_model: str = "BAAI/bge-reranker-v2-m3",
        milvus_uri: str = "http://localhost:19530",
        collection_name: str = "papers",
        llm: Optional[object] = None,
        enable_cache: bool = True,
        child_store: Optional[Milvus] = None,
        parent_store: Optional[Milvus] = None,
    ):
        self.embeddings = EmbeddingService.get_embeddings(embedding_model)
        self.reranker = RerankerService.get_reranker(reranker_model)
        self.milvus_uri = milvus_uri
        self.collection_name = collection_name
        self.llm = llm
        self.cache = RetrievalCache(self.embeddings) if enable_cache else None

        self._child_store = child_store or MilvusStoreFactory.create_store(
            self.embeddings, milvus_uri, collection_name, is_child=True
        )
        self._parent_store = parent_store or MilvusStoreFactory.create_store(
            self.embeddings, milvus_uri, collection_name, is_child=False
        )

    def retrieve(
        self,
        query: str,
        k: int = 5,
        use_hyde: bool = False,
        rerank: bool = True,
        expand_parent: bool = True,
        rrf_k: int = 60,
        fetch_k: int = 20,
        node_type_filter: Optional[list[str]] = None,
        section_type_filter: Optional[list[str]] = None,
        paper_ids: Optional[list[str]] = None,
        diversify: bool = True,
        diversity_weight: float = 0.25,
    ) -> list[Document]:
        """Full retrieval pipeline.

        Args:
            query: User query string.
            k: Number of final results.
            use_hyde: Whether to expand query with HyDE before search.
            rerank: Whether to rerank results with CrossEncoder.
            expand_parent: Whether to expand child hits to parent chunks.
            rrf_k: RRF constant for hybrid fusion.
            fetch_k: Number of candidates to fetch before reranking.
            node_type_filter: Restrict search to specific node types (e.g. ['table','figure']).
            section_type_filter: Restrict search to specific section types (e.g. ['method','experiment']).
            paper_ids: Restrict search to one or more uploaded papers.
        """
        cache_scope = self._cache_scope(
            node_type_filter,
            section_type_filter,
            paper_ids,
            rerank,
            expand_parent,
            diversify,
        )
        if self.cache:
            cached = self.cache.get(query, scope=cache_scope)
            if cached is not None:
                logger.debug(f"Cache hit for query: {query[:50]}...")
                return cached
        
        search_query = self._hyde(query) if use_hyde and self.llm else query
        expr = self._build_expr(node_type_filter, section_type_filter, paper_ids)

        if rerank and self.reranker:
            children = self._hybrid_search(self._child_store, search_query, fetch_k * RERANK_FETCH_MULTIPLIER, rrf_k, expr)
            if not children:
                logger.warning(f"No results found for query: {query[:50]}...")
                return []
            children = self._rerank(query, children, fetch_k)
        else:
            children = self._hybrid_search(self._child_store, search_query, fetch_k, rrf_k, expr)
            if not children:
                logger.warning(f"No results found for query: {query[:50]}...")
                return []

        if diversify:
            children = self._diversify(children, fetch_k, diversity_weight)

        if expand_parent:
            results = self._expand_to_parents(children[:k * DEDUP_FETCH_MULTIPLIER])
        else:
            results = children[:k * DEDUP_FETCH_MULTIPLIER]

        seen = set()
        deduped = []
        for doc in results:
            cid = doc.metadata.get("chunk_id", id(doc))
            if cid not in seen:
                seen.add(cid)
                deduped.append(doc)
        
        final = deduped[:k]
        for rank, doc in enumerate(final, 1):
            doc.metadata["retrieval_rank"] = rank
        
        if self.cache:
            self.cache.put(query, final, scope=cache_scope)
        
        logger.info(f"Retrieved {len(final)} results for query: {query[:50]}...")
        return final
    
    def get_updater(self):
        """Get IncrementalUpdater for this retriever's stores."""
        from .incremental import IncrementalUpdater
        return IncrementalUpdater(self._parent_store, self._child_store)

    def _build_expr(
        self,
        node_type_filter: Optional[list[str]],
        section_type_filter: Optional[list[str]],
        paper_ids: Optional[list[str]] = None,
    ) -> Optional[str]:
        """Build Milvus filter expression from routing constraints."""
        parts = []
        if node_type_filter:
            types = " || ".join(f'node_type == "{t}"' for t in node_type_filter)
            parts.append(f"({types})")
        if section_type_filter:
            types = " || ".join(f'section_type == "{t}"' for t in section_type_filter)
            parts.append(f"({types})")
        if paper_ids:
            papers = " || ".join(
                f"paper_id == {json.dumps(str(paper_id), ensure_ascii=False)}"
                for paper_id in paper_ids
            )
            parts.append(f"({papers})")
        return " && ".join(parts) if parts else None

    def _hybrid_search(
        self, store: Milvus, query: str, k: int, rrf_k: int, expr: Optional[str] = None
    ) -> list[Document]:
        reranker = Function(
            name="rrf_reranker",
            function_type=FunctionType.RERANK,
            # Milvus 2.6+ function-based RRF applies to every ANN search path.
            # The server therefore requires an empty input-field list and an
            # explicit reranker strategy in the function parameters.
            input_field_names=[],
            params={"reranker": "rrf", "k": rrf_k},
        )
        kwargs = {"k": k, "reranker": reranker, "fetch_k": k}
        if expr:
            kwargs["expr"] = expr
        results = store.similarity_search(query, **kwargs)
        return results

    def _rerank(self, query: str, docs: list[Document], top_k: int) -> list[Document]:
        if not docs:
            return docs
        pairs = [(query, doc.page_content) for doc in docs]
        scores = self.reranker.predict(pairs)
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        output = []
        for doc, score in ranked[:top_k]:
            doc.metadata["rerank_score"] = float(score)
            doc.metadata["retrieval_relevance"] = logistic_relevance(score)
            output.append(doc)
        return output

    def _diversify(
        self,
        docs: list[Document],
        top_k: int,
        diversity_weight: float,
    ) -> list[Document]:
        """Metadata-aware MMR selection for independent evidence coverage.

        In addition to text novelty, the selector rewards a new paper or
        section.  This makes evidence diversity observable in the downstream
        explanation report instead of treating it as a hidden retrieval trick.
        """
        if len(docs) <= 1 or diversity_weight <= 0:
            return docs[:top_k]

        weight = max(0.0, min(0.8, diversity_weight))
        selected: list[Document] = []
        remaining = list(docs)

        while remaining and len(selected) < top_k:
            best_index = 0
            best_score = float("-inf")
            seen_papers = {doc.metadata.get("paper_id") for doc in selected}
            seen_sections = {
                (doc.metadata.get("paper_id"), doc.metadata.get("section_path"))
                for doc in selected
            }

            for index, candidate in enumerate(remaining):
                relevance = candidate.metadata.get("retrieval_relevance")
                if relevance is None:
                    relevance = 1.0 / (1.0 + docs.index(candidate))
                novelty = 1.0
                if selected:
                    novelty = 1.0 - max(
                        self._text_overlap(candidate.page_content, chosen.page_content)
                        for chosen in selected
                    )
                paper = candidate.metadata.get("paper_id")
                section_key = (paper, candidate.metadata.get("section_path"))
                provenance_bonus = 0.0
                if paper and paper not in seen_papers:
                    provenance_bonus += 0.10
                if section_key not in seen_sections:
                    provenance_bonus += 0.05
                score = (1.0 - weight) * float(relevance) + weight * novelty + provenance_bonus
                if score > best_score:
                    best_score = score
                    best_index = index

            chosen = remaining.pop(best_index)
            chosen.metadata["diversity_selection_score"] = round(best_score, 4)
            selected.append(chosen)

        return selected

    @staticmethod
    def _text_overlap(left: str, right: str) -> float:
        left_words = set(re.findall(r"\w+", left.lower()))
        right_words = set(re.findall(r"\w+", right.lower()))
        if not left_words or not right_words:
            return 0.0
        return len(left_words & right_words) / len(left_words | right_words)

    def _expand_to_parents(self, children: list[Document]) -> list[Document]:
        parent_ids = list(dict.fromkeys(
            doc.metadata.get("chunk_parent_id")
            for doc in children
            if doc.metadata.get("chunk_parent_id")
        ))

        if not parent_ids:
            return children

        child_meta = {}
        for child in children:
            parent_id = child.metadata.get("chunk_parent_id")
            if not parent_id:
                continue
            current = child_meta.get(parent_id)
            relevance = child.metadata.get("retrieval_relevance") or 0.0
            if current is None or relevance > (current.get("retrieval_relevance") or 0.0):
                child_meta[parent_id] = child.metadata

        parents = []
        for pid in parent_ids:
            try:
                expr = f'chunk_id == "{pid}"'
                # Parent expansion is an exact metadata lookup, not another
                # similarity search. Calling similarity_search here would run
                # the dense+BM25 hybrid ranker again and can corrupt/multiply
                # reranker parameters across repeated parent lookups.
                rows = self._parent_store.client.query(
                    collection_name=self._parent_store.collection_name,
                    filter=expr,
                    output_fields=self._parent_store._get_output_fields(),
                    limit=1,
                )
                hits = []
                for raw_row in rows:
                    row = dict(raw_row)
                    page_content = row.pop(self._parent_store._text_field, "")
                    row.pop(self._parent_store._primary_field, None)
                    hits.append(Document(page_content=page_content, metadata=row))
                for hit in hits:
                    source_meta = child_meta.get(pid, {})
                    for key in ("rerank_score", "retrieval_relevance", "diversity_selection_score"):
                        if key in source_meta:
                            hit.metadata[key] = source_meta[key]
                parents.extend(hits)
            except Exception as e:
                logger.error(f"Failed to fetch parent {pid}: {e}")

        return parents if parents else children

    @staticmethod
    def _cache_scope(
        node_type_filter: Optional[list[str]],
        section_type_filter: Optional[list[str]],
        paper_ids: Optional[list[str]],
        rerank: bool,
        expand_parent: bool,
        diversify: bool,
    ) -> str:
        node_scope = ",".join(sorted(node_type_filter or []))
        section_scope = ",".join(sorted(section_type_filter or []))
        paper_scope = ",".join(sorted(paper_ids or []))
        return f"nodes={node_scope}|sections={section_scope}|papers={paper_scope}|rerank={rerank}|parent={expand_parent}|diverse={diversify}"

    def _hyde(self, query: str) -> str:
        prompt = (
            "Please write a short passage from an academic paper that would answer "
            f"the following question. Do not explain, just write the passage.\n\n"
            f"Question: {query}\n\nPassage:"
        )
        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            return content.strip()
        except Exception:
            return query
