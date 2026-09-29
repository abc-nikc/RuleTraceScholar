"""Extract a source paper's local bibliography and a transparent related-paper query."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pymupdf


_STOPWORDS = {
    "about", "after", "also", "among", "based", "between", "from", "into",
    "large", "learning", "method", "methods", "paper", "results", "study",
    "that", "their", "these", "this", "through", "using", "with", "without",
    "over",
}
_REFERENCE_HEADING = re.compile(r"^(references|bibliography|works cited)$", re.I)
_SECTION_AFTER_REFERENCES = re.compile(
    r"^(?:appendix\b|acknowledg(?:e)?ments?\b|supplementary\b|[A-Z](?:\.\d+)?\s+[A-Z][A-Z\s-]{2,})",
    re.I,
)


def _clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"(?<=\w)-\s+(?=\w)", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    # PDF line wrapping often inserts spaces inside well-known URLs/identifiers.
    value = re.sub(r"(https?://(?:arxiv\.org|doi\.org|aclanthology\.org|openreview\.net)/\S*)\s+(?=[\w.-]+(?:/|\.|$))", r"\1", value)
    return value


def _document_title(document: pymupdf.Document, fallback: str) -> str:
    if not document.page_count:
        return fallback
    blocks = document[0].get_text("blocks")
    candidates = [_clean_text(block[4]) for block in blocks if _clean_text(block[4])]
    for position, candidate in enumerate(candidates):
        if 12 <= len(candidate) <= 350 and not candidate.casefold().startswith("abstract"):
            # Two-column conference PDFs often wrap a long title into a second
            # text block before the author line.  Join explicit continuations
            # so the source paper can be excluded from its own related results.
            if position + 1 < len(candidates) and re.match(
                r"^(?:and|or|with|for|towards?|through|using)\b",
                candidates[position + 1],
                re.I,
            ):
                candidate = f"{candidate} {candidates[position + 1]}"
            return candidate
    return fallback


def _abstract(document: pymupdf.Document) -> str:
    text = _clean_text("\n".join(document[index].get_text() for index in range(min(2, document.page_count))))
    match = re.search(
        r"\bAbstract\b\s*(.+?)(?=\s+(?:1\s+)?(?:Introduction|INTRODUCTION)\b)",
        text,
        flags=re.I,
    )
    return match.group(1).strip()[:4000] if match else ""


def _reference_record(text: str, index: int) -> dict[str, Any]:
    cleaned = _clean_text(text)
    # Work on a second representation for identifiers.  PDF wrapping may put
    # spaces after a slash or dot inside a DOI/URL; collapse only when the next
    # token still looks identifier-like so the human-readable citation remains
    # untouched.
    identifier_text = cleaned
    wrapped_identifier = re.compile(
        r"((?:10\.\d{4,9}/|https?://)[^\s]{1,180}[./-])\s+(?=[A-Za-z0-9][A-Za-z0-9._/-]*(?:[./-]|$))",
        re.I,
    )
    for _ in range(6):
        repaired = wrapped_identifier.sub(r"\1", identifier_text)
        if repaired == identifier_text:
            break
        identifier_text = repaired
    arxiv_match = re.search(r"(?:arXiv\s*:\s*|arxiv\.org/(?:abs|pdf)/\s*)([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?", identifier_text, re.I)
    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", identifier_text, re.I)
    url_match = re.search(r"https?://[^\s]+", identifier_text)
    arxiv_id = arxiv_match.group(1) if arxiv_match else ""
    doi = doi_match.group(0).rstrip(".,)") if doi_match else ""
    url = url_match.group(0).rstrip(".,)") if url_match else ""
    if arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    elif doi:
        url = f"https://doi.org/{doi}"
    year_match = re.search(r"\b(19|20)\d{2}[a-z]?\b", cleaned)
    return {
        "index": index,
        "citation": cleaned,
        "year": int(year_match.group(0)[:4]) if year_match else None,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "url": url,
    }


def _references(document: pymupdf.Document) -> list[dict[str, Any]]:
    collecting = False
    bibliography_blocks: list[str] = []
    for page_index in range(document.page_count):
        blocks = [_clean_text(block[4]) for block in document[page_index].get_text("blocks")]
        for block in filter(None, blocks):
            if not collecting:
                if _REFERENCE_HEADING.fullmatch(block.rstrip(":")):
                    collecting = True
                continue
            if _SECTION_AFTER_REFERENCES.match(block) and not re.search(r"\b(19|20)\d{2}\b", block):
                collecting = False
                break
            if len(block) < 20:
                continue
            bibliography_blocks.append(block)
        if not collecting and bibliography_blocks:
            break

    # Layout-aware grouping.  Many conference templates emit the author list
    # and the remainder of one citation as separate PDF blocks.  Accumulate
    # until a year makes the citation complete; keep known continuation blocks
    # (venue, URL, DOI) attached to the preceding citation.
    raw_items: list[str] = []
    current = ""
    continuation = re.compile(
        r"^(?:In\b|Proceedings\b|Journal\b|Transactions\b|Advances\b|URL\b|doi\s*:|https?://)",
        re.I,
    )
    for position, block in enumerate(bibliography_blocks):
        current = f"{current} {block}".strip()
        next_block = bibliography_blocks[position + 1] if position + 1 < len(bibliography_blocks) else ""
        has_year = bool(re.search(r"\b(?:19|20)\d{2}[a-z]?\b", current))
        if has_year and (not next_block or not continuation.match(next_block)):
            raw_items.append(current)
            current = ""
    if current:
        raw_items.append(current)

    # Numbered bibliographies are occasionally returned as one large block.
    expanded: list[str] = []
    for item in raw_items:
        marker = re.compile(r"(?:^|\s)(?:\[\d+\]|\d+\.\s+[A-Z])")
        if marker.match(item) and len(marker.findall(item)) > 1:
            numbered = re.split(r"(?=\s*(?:\[\d+\]|\d+\.\s+[A-Z]))", item)
            usable = [part.strip() for part in numbered if len(part.strip()) >= 20]
            expanded.extend(usable or [item])
        else:
            expanded.append(item)
    return [_reference_record(item, index + 1) for index, item in enumerate(expanded[:150])]


def _keywords(title: str, abstract: str, limit: int = 10) -> list[str]:
    title_tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", title.casefold())
    abstract_tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", abstract.casefold())
    scores = Counter(token for token in abstract_tokens if token not in _STOPWORDS)
    scores.update({token: 3 for token in title_tokens if token not in _STOPWORDS})
    return [token for token, _ in scores.most_common(limit)]


def extract_paper_context(pdf_path: Path, fallback_title: str = "") -> dict[str, Any]:
    """Return source metadata, locally extracted references, and search terms."""
    with pymupdf.open(pdf_path) as document:
        title = _document_title(document, fallback_title or pdf_path.stem)
        abstract = _abstract(document)
        references = _references(document)
        page_count = document.page_count
    keywords = _keywords(title, abstract)
    return {
        "title": title,
        "abstract": abstract,
        "page_count": page_count,
        "references": references,
        "keywords": keywords,
        "related_query": " ".join(keywords) or title,
    }


def explain_relatedness(source: dict[str, Any], papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach an inspectable lexical-overlap reason and rank related papers."""
    source_terms = set(source.get("keywords") or [])
    source_title_key = re.sub(r"\W+", "", source.get("title", "").casefold())
    enriched = []
    for paper in papers:
        candidate_key = re.sub(r"\W+", "", paper.get("title", "").casefold())
        if candidate_key and candidate_key == source_title_key:
            continue
        candidate_text = f"{paper.get('title', '')} {paper.get('abstract', '')}".casefold()
        matched = sorted(term for term in source_terms if term in candidate_text)
        item = dict(paper)
        item["matched_terms"] = matched
        item["related_score"] = round(len(matched) / max(len(source_terms), 1), 3)
        item["relation_reason"] = (
            f"与源论文共享主题词：{', '.join(matched[:6])}"
            if matched else "由多源学术检索根据源论文主题返回"
        )
        enriched.append(item)
    enriched.sort(key=lambda item: (item["related_score"], item.get("citation_count") or 0), reverse=True)
    return enriched
