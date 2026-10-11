"""Offline checks for the isolated long-running arXiv sweep."""

import importlib.util
import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sources.base_source import PaperMetadata


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "arxiv_14day_sweep.py"
SPEC = importlib.util.spec_from_file_location("arxiv_14day_sweep", SCRIPT)
sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep)


def paper(identifier: str) -> PaperMetadata:
    return PaperMetadata(
        paper_id=identifier, title=f"Title {identifier}", authors=["A"],
        abstract=f"Abstract {identifier}", published_date=datetime.now(timezone.utc),
        url=f"https://arxiv.org/abs/{identifier}", source="arxiv",
    )


class SweepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_patch = patch.object(sweep, "DB", Path(self.tmp.name) / "sweep.sqlite")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.conn = sweep.connect()
        self.addCleanup(self.conn.close)
        self.end = sweep.initialize(self.conn)

    def test_category_counts_and_cross_category_dedup_survive_restart(self):
        responses = {category: [paper("2601.00001v1")] for category in sweep.CATEGORIES}
        responses["cs.LG"].append(paper("2601.00002v1"))

        class FakeSource:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def set_history_filtering_enabled(self, enabled):
                self.enabled = enabled

            def fetch_papers(self, days, domains, **kwargs):
                self_outer.assertEqual(days, 14)
                self_outer.assertEqual(kwargs["fetched_at"], self_outer.end)
                kwargs["scan_receipt_callback"]({"status": "succeeded"})
                return responses[domains[0]]

        self_outer = self
        with patch.object(sweep, "ArxivSource", FakeSource):
            with contextlib.redirect_stdout(io.StringIO()):
                sweep.scan(self.conn, self.end)
                sweep.scan(self.conn, self.end)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM paper_categories").fetchone()[0], 7)
        self.assertEqual(self.conn.execute("SELECT found FROM categories WHERE category='cs.LG'").fetchone()[0], 2)

    def test_score_resume_translates_qualified_only(self):
        with self.conn:
            for identifier in ("2601.00001v1", "2601.00002v1"):
                self.conn.execute("INSERT INTO papers(paper_id, metadata_json) VALUES (?, ?)",
                                  (identifier, json.dumps(paper(identifier).to_dict())))

        calls = []

        class FakeResponse:
            def __init__(self, passed):
                self.passed = passed

            def model_dump(self):
                return {"total_score": 8 if self.passed else 2,
                        "is_qualified": self.passed, "reasoning": "test"}

        class FakeAgent:
            def score_paper_with_keywords(self, **kwargs):
                calls.append(("score", kwargs["title"]))
                return FakeResponse("00001" in kwargs["title"])

            def translate_abstract(self, abstract):
                calls.append(("translate", abstract))
                return "中文摘要"

        with patch.object(sweep, "AnalysisAgent", FakeAgent):
            with contextlib.redirect_stdout(io.StringIO()):
                sweep.score(self.conn)
                sweep.score(self.conn)
        self.assertEqual(sum(kind == "score" for kind, _ in calls), 2)
        self.assertEqual(sum(kind == "translate" for kind, _ in calls), 1)
        statuses = [row[0] for row in self.conn.execute(
            "SELECT translation_status FROM papers ORDER BY paper_id")]
        self.assertEqual(statuses, ["succeeded", "not_required"])

    def test_failed_category_retries_without_repeating_completed_categories(self):
        calls = []

        class FlakySource:
            def __init__(self, **kwargs):
                pass

            def set_history_filtering_enabled(self, enabled):
                pass

            def fetch_papers(self, days, domains, **kwargs):
                category = domains[0]
                calls.append(category)
                if category == "cs.DC" and calls.count(category) == 1:
                    raise RuntimeError("temporary source failure")
                kwargs["scan_receipt_callback"]({"status": "succeeded"})
                return [paper("2601.00001v1")]

        with patch.object(sweep, "ArxivSource", FlakySource):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "temporary source failure"):
                    sweep.scan(self.conn, self.end)
                sweep.scan(self.conn, self.end)
        self.assertEqual(calls.count("cs.LG"), 1)
        self.assertEqual(calls.count("cs.AI"), 1)
        self.assertEqual(calls.count("cs.DC"), 2)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM categories WHERE status='completed'"
        ).fetchone()[0], 6)


if __name__ == "__main__":
    unittest.main()
