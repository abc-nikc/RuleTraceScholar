"""Unit tests for academic discovery normalization and safe importing."""

import unittest

from research_sources.discovery import (
    download_arxiv_pdf,
    parse_arxiv_feed,
    parse_crossref,
    parse_semantic_scholar,
)


ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2603.09192v1</id>
    <published>2026-03-10T12:00:00Z</published>
    <title>  Explainable\nAgentic RAG  </title>
    <summary> A grounded research assistant. </summary>
    <author><name>Alice Researcher</name></author>
    <arxiv:doi>10.0000/example</arxiv:doi>
    <link title="pdf" href="https://arxiv.org/pdf/2603.09192v1" type="application/pdf" />
  </entry>
</feed>"""


class DiscoveryParserTests(unittest.IsolatedAsyncioTestCase):
    def test_arxiv_atom_is_normalized(self):
        papers = parse_arxiv_feed(ARXIV_XML)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["source_id"], "2603.09192v1")
        self.assertEqual(papers[0]["title"], "Explainable Agentic RAG")
        self.assertEqual(papers[0]["year"], 2026)
        self.assertEqual(papers[0]["authors"], ["Alice Researcher"])

    def test_semantic_scholar_is_normalized(self):
        papers = parse_semantic_scholar({"data": [{
            "paperId": "abc",
            "title": "Evidence Agent",
            "authors": [{"name": "Bob"}],
            "year": 2025,
            "externalIds": {"ArXiv": "2501.00001", "DOI": "10.1/x"},
            "openAccessPdf": {"url": "https://example.invalid/paper.pdf"},
            "citationCount": 7,
        }]})
        self.assertEqual(papers[0]["arxiv_id"], "2501.00001")
        self.assertTrue(papers[0]["open_access"])
        self.assertEqual(papers[0]["citation_count"], 7)

    def test_crossref_is_normalized_and_markup_is_removed(self):
        papers = parse_crossref({"message": {"items": [{
            "DOI": "10.1234/example",
            "title": ["Agentic Evidence Repair"],
            "author": [{"given": "Ada", "family": "Lovelace"}],
            "published": {"date-parts": [[2026, 4, 2]]},
            "abstract": "<jats:p>Grounded &amp; auditable.</jats:p>",
            "URL": "https://doi.org/10.1234/example",
            "is-referenced-by-count": 5,
            "link": [{"content-type": "application/pdf", "URL": "https://example.org/p.pdf"}],
        }]}})
        self.assertEqual(papers[0]["authors"], ["Ada Lovelace"])
        self.assertEqual(papers[0]["abstract"], "Grounded & auditable.")
        self.assertEqual(papers[0]["year"], 2026)
        self.assertTrue(papers[0]["open_access"])

    async def test_invalid_arxiv_id_is_rejected_before_network_access(self):
        with self.assertRaisesRegex(ValueError, "Invalid arXiv identifier"):
            await download_arxiv_pdf("https://evil.invalid/file.pdf")


if __name__ == "__main__":
    unittest.main()
