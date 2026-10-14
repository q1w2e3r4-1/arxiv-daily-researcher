import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from utils.paper_body import select_paper_body, check_input_budget, PaperInputTooLargeError
from agents.analysis_agent import AnalysisAgent
from config import settings


class PaperBodyTests(unittest.TestCase):
    def test_removes_reference_and_appendix_tail_without_losing_results(self):
        main = "Introduction\n" + "Our design and results.\n" * 100
        for heading in ("References", "9 REFERENCES", "Bibliography", "Appendix A: Extra Results"):
            body, meta = select_paper_body(main + heading + "\nReferences to other work\nAppendix\n")
            self.assertEqual(body, main.strip())
            self.assertEqual(meta["input_scope"], "main_body")

    def test_keeps_ambiguous_mentions_and_early_table_of_contents(self):
        text = "Contents\nReferences\n" + "Discussion\nWe discuss references and appendices here.\n" * 50
        body, meta = select_paper_body(text)
        self.assertEqual(body, text.strip())
        self.assertIsNone(meta["removed_tail_section"])

    def test_wrapped_appendix_reference_in_a_sentence_does_not_cut_results(self):
        main = "Introduction\n" + "Background and methodology.\n" * 100
        text = main + "Appendix D.1) as its p90 latency when run in isolation\nResults are here.\nReferences\nCitation"
        body, _ = select_paper_body(text)
        self.assertIn("Results are here.", body)
        self.assertNotIn("Citation", body)

    def test_input_budget_counts_chinese_and_never_silently_clips(self):
        self.assertEqual(check_input_budget("规则", "正文", 100), 76)
        with self.assertRaises(PaperInputTooLargeError):
            check_input_budget("规则", "正文" * 100, 100)

    def test_long_appendix_does_not_hide_an_early_real_reference_heading(self):
        main = "Introduction\n" + "Design and results.\n" * 100
        text = main + "References\n[1] Author. Paper.\n[2] Author. Paper.\nAppendix\n" + "Details.\n" * 5000
        body, _ = select_paper_body(text)
        self.assertEqual(body, main.strip())

    def test_pdf_parser_reads_results_after_page_twenty(self):
        with fitz.open() as doc:
            for i in range(22):
                page = doc.new_page()
                page.insert_text((72, 72), f"Page {i + 1}: Results marker {i + 1}")
            pdf = doc.tobytes()
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent._download_pdf_bytes = lambda _: pdf
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "DOWNLOAD_DIR", Path(directory)):
            text = agent._parse_pdf_with_pymupdf("https://example.test/paper.pdf")
            self.assertIn("Results marker 22", text)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_deep_analysis_keeps_late_design_and_records_sent_scope(self):
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent.deep_template = {"modules": [{"id": "summary", "prompt": "总结", "enabled": True}]}
        prompts = []
        def call(prompt, **kwargs):
            prompts.append(prompt)
            return '{"summary":"测试内容"}'
        agent._call_smart_llm = call
        text = "Introduction\n" + "Background.\n" * 1500 + "Design and final results\nReferences\nUnused bibliography"
        result = agent.deep_analyze("Test", "", "Abstract", pdf_text=text)
        self.assertIn("Design and final results", prompts[0])
        self.assertNotIn("Unused bibliography", prompts[0])
        self.assertEqual(result["__meta"]["input_scope"], "main_body")
        with patch.object(settings, "LLM_ANALYSIS_INPUT_TOKEN_BUDGET", 100):
            with self.assertRaises(PaperInputTooLargeError):
                agent.deep_analyze("Test", "", "Abstract", pdf_text=text)
        self.assertEqual(len(prompts), 1)
