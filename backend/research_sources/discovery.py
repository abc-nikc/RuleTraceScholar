"""Keyless arXiv and optional Semantic Scholar discovery."""

from __future__ import annotations

import asyncio
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

import httpx

from config import Config


ARXIV_ID_RE = re.compile(r"^(?:[a-z\-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?$", re.I)
USER_AGENT = "RuleTrace-Scholar/1.0 (local academic research assistant)"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _year(value: str) -> int | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).year
    except (TypeError, ValueError):
        return None


def parse_arxiv_feed(xml_text: str) -> list[dict[str, Any]]:
    """Normalize an Atom response without trusting its markup as instructions."""
    root = ET.fromstring(xml_text)
    atom = "{http://www.w3.org/2005/Atom}"
    arxiv = "{http://arxiv.org/schemas/atom}"
    papers = []
    for entry in root.findall(f"{atom}entry"):
        raw_id = _clean(entry.findtext(f"{atom}id")).rsplit("/", 1)[-1]
        pdf_url = ""
        for link in entry.findall(f"{atom}link"):
            if link.attrib.get("type") == "application/pdf" or link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")
                break
        published = _clean(entry.findtext(f"{atom}published"))
        papers.append({
            "source": "arxiv",
            "source_id": raw_id,
            "title": _clean(entry.findtext(f"{atom}title")),
            "authors": [_clean(a.findtext(f"{atom}name")) for a in entry.findall(f"{atom}author")],
            "abstract": _clean(entry.findtext(f"{atom}summary")),
            "published": published,
            "year": _year(published),
            "doi": _clean(entry.findtext(f"{arxiv}doi")),
            "url": _clean(entry.findtext(f"{atom}id")),
            "pdf_url": pdf_url or f"https://arxiv.org/pdf/{raw_id}",
            "citation_count": None,
            "open_access": True,
        })
    return papers


def parse_semantic_scholar(data: dict[str, Any]) -> list[dict[str, Any]]:
    papers = []
    for item in data.get("data", []):
        external = item.get("externalIds") or {}
        open_pdf = item.get("openAccessPdf") or {}
        arxiv_id = _clean(external.get("ArXiv"))
        papers.append({
            "source": "semantic_scholar",
            "source_id": arxiv_id or _clean(item.get("paperId")),
            "title": _clean(item.get("title")),
            "authors": [_clean(author.get("name")) for author in item.get("authors") or []],
            "abstract": _clean(item.get("abstract")),
            "published": _clean(item.get("publicationDate")),
            "year": item.get("year"),
            "doi": _clean(external.get("DOI")),
            "url": _clean(item.get("url")),
            "pdf_url": _clean(open_pdf.get("url")),
            "citation_count": item.get("citationCount"),
            "open_access": bool(open_pdf.get("url")),
            "arxiv_id": arxiv_id,
        })
    return papers


def parse_crossref(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Crossref works metadata into the shared discovery schema."""
    papers = []
    for item in (data.get("message") or {}).get("items", []):
        date_parts = ((item.get("published") or {}).get("date-parts") or [[]])[0]
        year = date_parts[0] if date_parts and isinstance(date_parts[0], int) else None
        abstract = html.unescape(re.sub(r"<[^>]+>", " ", str(item.get("abstract") or "")))
        pdf_url = ""
        for link in item.get("link") or []:
            if link.get("content-type") == "application/pdf":
                pdf_url = _clean(link.get("URL"))
                break
        authors = [
            _clean(" ".join(filter(None, (author.get("given"), author.get("family")))))
            for author in item.get("author") or []
        ]
        papers.append({
            "source": "crossref",
            "source_id": _clean(item.get("DOI")),
            "title": _clean((item.get("title") or [""])[0]),
            "authors": authors,
            "abstract": _clean(abstract),
            "published": "-".join(str(part) for part in date_parts) if date_parts else "",
            "year": year,
            "doi": _clean(item.get("DOI")),
            "url": _clean(item.get("URL")),
            "pdf_url": pdf_url,
            "citation_count": item.get("is-referenced-by-count"),
            "open_access": bool(pdf_url),
            "arxiv_id": "",
        })
    return papers


async def _search_arxiv(client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, Any]]:
    terms = re.findall(r"[\w-]+", query, flags=re.UNICODE)[:12]
    search_expression = " AND ".join(f"all:{term}" for term in terms) or f"all:{query}"
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query={quote_plus(search_expression)}&start=0&max_results={limit}"
        "&sortBy=submittedDate&sortOrder=descending"
    )
    response = await client.get(url)
    response.raise_for_status()
    return parse_arxiv_feed(response.text)


async def _search_semantic_scholar(
    client: httpx.AsyncClient, query: str, limit: int
) -> list[dict[str, Any]]:
    headers = {}
    if Config.SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = Config.SEMANTIC_SCHOLAR_API_KEY
    response = await client.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": query,
            "limit": limit,
            "fields": "title,abstract,authors,year,publicationDate,url,externalIds,citationCount,openAccessPdf",
        },
        headers=headers,
    )
    response.raise_for_status()
    return parse_semantic_scholar(response.json())


async def _search_crossref(client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "rows": limit,
        "select": "DOI,title,author,abstract,URL,published,is-referenced-by-count,link",
    }
    if Config.CROSSREF_MAILTO:
        params["mailto"] = Config.CROSSREF_MAILTO
    response = await client.get("https://api.crossref.org/works", params=params)
    response.raise_for_status()
    return parse_crossref(response.json())


def _deduplicate(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for paper in papers:
        title_key = re.sub(r"\W+", "", paper.get("title", "").casefold())
        key = (paper.get("doi") or paper.get("arxiv_id") or title_key).casefold()
        if not key:
            continue
        if key not in merged:
            merged[key] = paper
            merged[key]["providers"] = [paper["source"]]
            continue
        current = merged[key]
        current["providers"] = sorted(set(current.get("providers", [])) | {paper["source"]})
        for field in ("doi", "pdf_url", "abstract", "citation_count", "arxiv_id"):
            if not current.get(field) and paper.get(field):
                current[field] = paper[field]
    return list(merged.values())


async def discover_papers(query: str, limit: int = 10) -> dict[str, Any]:
    limit = max(1, min(limit, Config.DISCOVERY_MAX_RESULTS))
    timeout = httpx.Timeout(Config.DISCOVERY_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        results = await asyncio.gather(
            _search_arxiv(client, query, limit),
            _search_semantic_scholar(client, query, limit),
            _search_crossref(client, query, limit),
            return_exceptions=True,
        )

    provider_papers: list[list[dict[str, Any]]] = []
    providers = []
    for name, result in zip(("arxiv", "semantic_scholar", "crossref"), results):
        if isinstance(result, Exception):
            providers.append({"provider": name, "ok": False, "detail": str(result)})
            provider_papers.append([])
        else:
            providers.append({"provider": name, "ok": True, "count": len(result)})
            provider_papers.append(result)
    # Interleave provider-ranked lists so a single source cannot crowd every
    # other catalogue out of the visible result window.
    papers = [
        source_results[index]
        for index in range(max((len(items) for items in provider_papers), default=0))
        for source_results in provider_papers
        if index < len(source_results)
    ]
    return {"query": query, "papers": _deduplicate(papers)[:limit], "providers": providers}


async def download_arxiv_pdf(arxiv_id: str) -> bytes:
    """Download only from the fixed arXiv host to avoid an SSRF-style URL importer."""
    arxiv_id = arxiv_id.strip()
    if not ARXIV_ID_RE.fullmatch(arxiv_id):
        raise ValueError("Invalid arXiv identifier")
    max_bytes = Config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(Config.DISCOVERY_DOWNLOAD_TIMEOUT_SECONDS),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        async with client.stream("GET", f"https://arxiv.org/pdf/{arxiv_id}") as response:
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError(f"PDF exceeds {Config.MAX_UPLOAD_SIZE_MB}MB limit")
    if not bytes(content).startswith(b"%PDF-"):
        raise ValueError("arXiv did not return a PDF")
    return bytes(content)
