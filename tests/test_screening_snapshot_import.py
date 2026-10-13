"""Frozen review imports preserve history and become searchable without LLM calls."""
import importlib.util
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from utils.daily_research_store import DailyResearchStore

spec = importlib.util.spec_from_file_location("snapshot_import", Path(__file__).resolve().parents[1] / "scripts/import_screening_snapshot.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScreeningSnapshotImportTests(unittest.TestCase):
    def test_import_is_searchable_preserves_original_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "review.db"
            target = root / "history.db"
            with sqlite3.connect(source) as conn:
                conn.executescript("""
                    CREATE TABLE experiment(id INTEGER, prompt_sha256 TEXT, prompt_version TEXT, model TEXT);
                    INSERT INTO experiment VALUES (1, 'fixture-hash', '1.8', 'fixture-model');
                    CREATE TABLE papers(paper_id TEXT, metadata_json TEXT, new_score_json TEXT, status TEXT, completed_at TEXT);
                """)
                for paper_id, qualified in [("demo1", True), ("demo2", False)]:
                    conn.execute("INSERT INTO papers VALUES (?, ?, ?, 'succeeded', ?)",
                                 (paper_id, json.dumps({"paper_id": paper_id, "source": "arxiv", "title": paper_id}),
                                  json.dumps({"is_qualified": qualified, "total_score": 8 if qualified else 2, "tldr": "Demo summary"}),
                                  "2026-10-12T18:00:00+00:00"))
            store = DailyResearchStore(target)
            store.import_legacy_paper({"source": "arxiv", "paper_id": "demo1", "paper_json": {"title": "Original"},
                                      "score_json": json.dumps({"is_qualified": False}),
                                      "completed_at": "2026-05-01T00:00:00"}, delivered=False)
            store.set_paper_preference("arxiv", "demo1", preference="like", title="Original")
            preview = module.import_snapshot(source, target)
            self.assertFalse(preview["applied"])
            self.assertFalse(store.search_papers(qualified_only=True)["items"])
            result = module.import_snapshot(source, target, apply=True)
            self.assertEqual(result["imported"], 2)
            papers = store.search_papers(qualified_only=True, completed_from="2026-09-30", completed_to="2026-10-13")
            self.assertEqual(papers["total"], 1)
            self.assertEqual(papers["items"][0]["screening_prompt_version"], "1.8")
            self.assertEqual(papers["items"][0]["completed_at"], "2026-10-13T02:00:00")
            self.assertEqual(papers["items"][0]["preference"], "like")
            with store._connect() as conn:
                original = json.loads(conn.execute("SELECT original_record_json FROM screening_review_imports WHERE paper_id='demo1'").fetchone()[0])
                self.assertEqual(json.loads(original["score_json"])["is_qualified"], False)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM paper_deliveries").fetchone()[0], 0)
            repeat = module.import_snapshot(source, target, apply=True)
            self.assertEqual(repeat["skipped_existing_newer"], 2)
            with store._connect() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM screening_review_imports").fetchone()[0], 2)
            with sqlite3.connect(source) as conn:
                conn.execute("UPDATE papers SET status='pending' WHERE paper_id='demo2'")
            with self.assertRaises(ValueError):
                module.import_snapshot(source, target, apply=True)
