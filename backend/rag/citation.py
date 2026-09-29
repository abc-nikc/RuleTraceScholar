"""Citation and provenance extraction for retrieval results."""

import re
from typing import Dict, List
from langchain_core.documents import Document


class CitationExtractor:
    """Extract citation metadata from retrieved documents."""
    
    @staticmethod
    def extract_citation(doc: Document) -> Dict:
        """Extract a citation plus the evidence fields needed by TRACE."""
        meta = doc.metadata
        excerpt = re.sub(r"\s+", " ", doc.page_content).strip()[:500]
        internal_metadata = {
            key: meta.get(key)
            for key in ("image_path", "vlm_description")
            if meta.get(key)
        }
        return {
            "paper_id": meta.get("paper_id", ""),
            "section": meta.get("section_path", ""),
            "page": meta.get("page_num", ""),
            "chunk_id": meta.get("chunk_id", ""),
            "node_type": meta.get("node_type", ""),
            "retrieval_rank": meta.get("retrieval_rank"),
            "retrieval_relevance": meta.get("retrieval_relevance"),
            "evidence_excerpt": excerpt,
            "text": excerpt,
            "metadata": internal_metadata,
        }
    
    @staticmethod
    def format_citation(citation: Dict) -> str:
        """Format citation as readable string."""
        parts = []
        if citation["paper_id"]:
            parts.append(f"Paper: {citation['paper_id']}")
        if citation["section"]:
            parts.append(f"Section: {citation['section']}")
        if citation["page"]:
            parts.append(f"Page: {citation['page']}")
        return " | ".join(parts) if parts else "Unknown source"
    
    @staticmethod
    def extract_all(docs: List[Document]) -> List[Dict]:
        """Extract citations from multiple documents."""
        return [CitationExtractor.extract_citation(doc) for doc in docs]
