"""Trusted academic discovery providers."""

from .discovery import discover_papers, download_arxiv_pdf
from .paper_context import extract_paper_context, explain_relatedness

__all__ = [
    "discover_papers", "download_arxiv_pdf", "extract_paper_context",
    "explain_relatedness",
]
