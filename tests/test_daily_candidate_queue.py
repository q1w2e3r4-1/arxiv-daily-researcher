"""每日候选论文完整抓取与分批处理的离线回归测试。"""

import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.analysis_agent import WeightedScoreResponse
from sources.arxiv_source import ArxivFetchError, ArxivSource
from sources.base_source import PaperMetadata
from sources.search_agent import SearchAgent
from utils.daily_research_store import DailyResearchStore


def make_paper(index: int) -> PaperMetadata:
    return PaperMetadata(
        paper_id=f"2610.{index:05d}",
        title=f"Paper {index}",
        authors=["Researcher"],
        abstract=f"Abstract {index}",
        published_date=datetime.now(timezone.utc),
        url=f"https://arxiv.org/abs/2610.{index:05d}",
        pdf_url=f"https://arxiv.org/pdf/2610.{index:05d}",
        source="arxiv",
        categories=["cs.DC"],
    )


class DailyCandidateQueueTests(unittest.TestCase):
    def test_all_candidates_are_saved_before_processing_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "daily.db"
            store = DailyResearchStore(db_path)
            papers = [make_paper(i) for i in range(300)]
            self.assertEqual(store.register_candidates("run-1", {"arxiv": papers}), 300)

            selected, counts = store.get_unfinished_papers(["arxiv"], 25)
            self.assertEqual(counts["arxiv"], 300)
            self.assertEqual(len(selected["arxiv"]), 25)

            for paper in selected["arxiv"]:
                score = WeightedScoreResponse(
                    total_score=3, keyword_scores={}, author_bonus=0,
                    expert_authors_found=[], passing_score=6, is_qualified=False,
                    reasoning="out of scope", tldr="", extracted_keywords=[],
                )
                store.upsert_scored_paper(
                    "run-1", "arxiv",
                    {"paper_id": paper.paper_id, "paper_metadata": paper,
                     "score_response": score, "abstract": paper.abstract},
                )
                store.mark_completed("run-1", "arxiv", paper.paper_id)

            reopened = DailyResearchStore(db_path)
            next_batch, counts = reopened.get_unfinished_papers(["arxiv"], 25)
            self.assertEqual(counts["arxiv"], 275)
            self.assertEqual(len(next_batch["arxiv"]), 25)
            self.assertTrue(set(p.paper_id for p in next_batch["arxiv"]).isdisjoint(
                set(p.paper_id for p in selected["arxiv"])
            ))
            self.assertEqual(reopened.register_candidates("run-2", {"arxiv": papers}), 0)
            self.assertEqual(reopened.get_paper_record("arxiv", papers[0].paper_id)["total_score"], 3)

    def test_partially_processed_paper_keeps_completed_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DailyResearchStore(Path(tmp) / "daily.db")
            paper = make_paper(1)
            store.register_candidates("run-1", {"arxiv": [paper]})
            score = WeightedScoreResponse(
                total_score=8, keyword_scores={}, author_bonus=0,
                expert_authors_found=[], passing_score=6, is_qualified=True,
                reasoning="relevant", tldr="", extracted_keywords=[],
            )
            store.upsert_scored_paper(
                "run-1", "arxiv",
                {"paper_id": paper.paper_id, "paper_metadata": paper,
                 "score_response": score, "abstract": paper.abstract},
            )
            store.update_translation("run-1", "arxiv", paper.paper_id, "中文摘要")

            selected, counts = store.get_unfinished_papers(["arxiv"], 25)
            restored = store.hydrate_scored_paper("arxiv", selected["arxiv"][0].paper_id)
            self.assertEqual(counts["arxiv"], 1)
            self.assertEqual(restored["score_response"].total_score, 8)
            self.assertEqual(restored["abstract_cn"], "中文摘要")
            self.assertIsNone(restored["analysis"])

    def test_manual_date_window_does_not_take_unrelated_backlog(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DailyResearchStore(Path(tmp) / "daily.db")
            old_paper = make_paper(1)
            old_paper.published_date = datetime(2026, 10, 10, tzinfo=timezone.utc)
            new_paper = make_paper(2)
            new_paper.published_date = datetime(2026, 10, 11, tzinfo=timezone.utc)
            store.register_candidates("run-1", {"arxiv": [old_paper, new_paper]})
            selected, counts = store.get_unfinished_papers(
                ["arxiv"], 25, date_from=date(2026, 10, 11), date_to=date(2026, 10, 11)
            )
            self.assertEqual(counts["arxiv"], 1)
            self.assertEqual([paper.paper_id for paper in selected["arxiv"]], [new_paper.paper_id])

    def test_arxiv_does_not_stop_after_legacy_fetch_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = ArxivSource(Path(tmp), max_results=25)
            papers = [make_paper(i) for i in range(300)]
            results = [
                SimpleNamespace(
                    get_short_id=lambda p=p: p.paper_id,
                    title=p.title, authors=[SimpleNamespace(name="Researcher")],
                    summary=p.abstract, published=p.published_date,
                    entry_id=p.url, pdf_url=p.pdf_url, doi=None,
                    categories=p.categories,
                )
                for p in papers
            ]
            source.client = SimpleNamespace(results=lambda search: iter(results))
            fetched = source.fetch_papers(days=14, domains=["cs.DC"])
            self.assertEqual(len(fetched), 300)

    def test_arxiv_scan_error_reaches_pipeline(self):
        agent = SearchAgent.__new__(SearchAgent)
        agent.sources = {"arxiv": SimpleNamespace(
            display_name="ArXiv",
            fetch_papers=lambda **kwargs: (_ for _ in ()).throw(ArxivFetchError("incomplete")),
        )}
        agent.arxiv_domains = ["cs.DC"]
        with self.assertRaisesRegex(ArxivFetchError, "incomplete"):
            agent.fetch_all_papers(days=14)

    def test_partial_arxiv_category_scan_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = ArxivSource(Path(tmp), max_results=25)
            paper = make_paper(1)
            result = SimpleNamespace(
                get_short_id=lambda: paper.paper_id,
                title=paper.title, authors=[SimpleNamespace(name="Researcher")],
                summary=paper.abstract, published=paper.published_date,
                entry_id=paper.url, pdf_url=paper.pdf_url, doi=None,
                categories=paper.categories,
            )

            def results(search):
                if "cat:cs.AI" in search.query:
                    raise RuntimeError("arXiv unavailable")
                return iter([result])

            source.client = SimpleNamespace(results=results)
            with patch("sources.arxiv_source.time.sleep"):
                with self.assertRaisesRegex(ArxivFetchError, "cs.AI"):
                    source.fetch_papers(days=14, domains=["cs.DC", "cs.AI"])


if __name__ == "__main__":
    unittest.main()
