import tempfile
import unittest
from pathlib import Path

import pymupdf

from research_sources.paper_context import extract_paper_context, explain_relatedness


class PaperContextTests(unittest.TestCase):
    def test_extracts_original_title_references_and_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.pdf"
            document = pymupdf.open()
            first = document.new_page()
            first.insert_textbox(
                pymupdf.Rect(60, 50, 540, 90),
                "Explainable Research Agent",
                fontsize=15,
            )
            first.insert_textbox(
                pymupdf.Rect(60, 92, 540, 132),
                "with Verified Retrieval",
                fontsize=15,
            )
            first.insert_textbox(
                pymupdf.Rect(60, 145, 540, 280),
                "Abstract\nWe introduce an explainable agentic retrieval system with evidence verification.\n"
                "1 INTRODUCTION\nThe system retrieves research papers.",
                fontsize=10,
            )
            refs = document.new_page()
            refs.insert_text((60, 60), "References", fontsize=13)
            refs.insert_textbox(
                pymupdf.Rect(60, 85, 540, 145),
                "Ada Author.",
                fontsize=10,
            )
            refs.insert_textbox(
                pymupdf.Rect(60, 120, 540, 160),
                "Verified Retrieval Systems, 2024. arXiv:2401.12345.",
                fontsize=10,
            )
            refs.insert_textbox(
                pymupdf.Rect(60, 175, 540, 205),
                "Bob Scholar.",
                fontsize=10,
            )
            refs.insert_textbox(
                pymupdf.Rect(60, 210, 540, 255),
                "Evidence Graphs, 2023. doi: 10.1234/example.\n7.",
                fontsize=10,
            )
            refs.insert_text((60, 285), "APPENDIX A DETAILS", fontsize=13)
            document.save(path)
            document.close()

            result = extract_paper_context(path)
            self.assertEqual(result["title"], "Explainable Research Agent with Verified Retrieval")
            self.assertEqual(result["page_count"], 2)
            self.assertEqual(len(result["references"]), 2)
            self.assertEqual(result["references"][0]["arxiv_id"], "2401.12345")
            self.assertEqual(result["references"][1]["doi"], "10.1234/example.7")

    def test_related_results_explain_matched_terms_and_exclude_source(self):
        source = {"title": "Explainable Agent RAG", "keywords": ["explainable", "agent-rag", "retrieval"]}
        result = explain_relatedness(source, [
            {"title": "Explainable Retrieval for Agents", "abstract": "retrieval evidence", "citation_count": 2},
            {"title": "Explainable Agent RAG", "abstract": "source paper"},
        ])
        self.assertEqual(len(result), 1)
        self.assertIn("explainable", result[0]["matched_terms"])
        self.assertGreater(result[0]["related_score"], 0)


if __name__ == "__main__":
    unittest.main()
