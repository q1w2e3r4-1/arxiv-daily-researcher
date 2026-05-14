"""
Daily research SQLite 持久化存储。

为每日研究模式提供 paper-level first 的持久化层：
- 记录 daily run 元信息
- 记录每篇论文的评分 / 翻译 / 深度分析阶段结果
- 支持按 (source, paper_id) 恢复已完成阶段，避免中断后整篇重跑
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from agents.analysis_agent import WeightedScoreResponse
from sources.base_source import PaperMetadata

logger = logging.getLogger(__name__)


class DailyResearchStore:
    """SQLite-backed daily research 持久化存储。"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_tables(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    search_days INTEGER,
                    date_from TEXT,
                    date_to TEXT,
                    max_results INTEGER,
                    enabled_sources_json TEXT,
                    keywords_json TEXT,
                    report_paths_json TEXT,
                    token_usage_json TEXT,
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS daily_papers (
                    source TEXT NOT NULL,
                    paper_id TEXT NOT NULL,
                    title TEXT,
                    published_date TEXT,
                    url TEXT,
                    pdf_url TEXT,
                    doi TEXT,
                    journal TEXT,
                    is_qualified INTEGER,
                    total_score REAL,
                    passing_score REAL,
                    scoring_method TEXT,
                    first_run_id TEXT,
                    last_run_id TEXT,
                    completed_run_id TEXT,
                    score_completed_at TEXT,
                    translation_completed_at TEXT,
                    analysis_completed_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT,
                    authors_json TEXT,
                    categories_json TEXT,
                    abstract TEXT,
                    abstract_cn TEXT,
                    score_json TEXT,
                    analysis_json TEXT,
                    last_error TEXT,
                    PRIMARY KEY (source, paper_id)
                );

                CREATE INDEX IF NOT EXISTS idx_daily_papers_published_date
                ON daily_papers(published_date);

                CREATE INDEX IF NOT EXISTS idx_daily_papers_is_qualified
                ON daily_papers(is_qualified);

                CREATE INDEX IF NOT EXISTS idx_daily_papers_completed_at
                ON daily_papers(completed_at);

                CREATE INDEX IF NOT EXISTS idx_daily_papers_analysis_completed_at
                ON daily_papers(analysis_completed_at);
                """
            )

            run_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(daily_runs)").fetchall()
            }
            if "date_from" not in run_columns:
                conn.execute("ALTER TABLE daily_runs ADD COLUMN date_from TEXT")
            if "date_to" not in run_columns:
                conn.execute("ALTER TABLE daily_runs ADD COLUMN date_to TEXT")

            conn.commit()

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _json_loads(value: Optional[str], default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except Exception:
            return default

    def create_run(
        self,
        run_id: str,
        *,
        search_days: int,
        max_results: int,
        enabled_sources: Any,
        keywords: Dict[str, float],
        date_from: Optional[Any] = None,
        date_to: Optional[Any] = None,
    ) -> None:
        now = self._utcnow_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO daily_runs (
                    run_id, started_at, status, search_days, date_from, date_to, max_results,
                    enabled_sources_json, keywords_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    search_days = excluded.search_days,
                    date_from = excluded.date_from,
                    date_to = excluded.date_to,
                    max_results = excluded.max_results,
                    enabled_sources_json = excluded.enabled_sources_json,
                    keywords_json = excluded.keywords_json,
                    updated_at = excluded.updated_at
                """,
                (
                    run_id,
                    now,
                    "running",
                    search_days,
                    str(date_from) if date_from else None,
                    str(date_to) if date_to else None,
                    max_results,
                    self._json_dumps(list(enabled_sources)),
                    self._json_dumps(keywords),
                    now,
                    now,
                ),
            )
            conn.commit()

    def complete_run(
        self,
        run_id: str,
        *,
        status: str,
        report_paths: Optional[Dict[str, str]] = None,
        token_usage: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        now = self._utcnow_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_runs
                SET completed_at = ?,
                    status = ?,
                    report_paths_json = ?,
                    token_usage_json = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    now,
                    status,
                    self._json_dumps(report_paths or {}),
                    self._json_dumps(token_usage or {}),
                    error_message,
                    now,
                    run_id,
                ),
            )
            conn.commit()

    def get_paper_record(self, source: str, paper_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM daily_papers WHERE source = ? AND paper_id = ?",
                (source, paper_id),
            ).fetchone()
        return dict(row) if row else None

    # 尝试从数据库中恢复论文的评分、翻译、分析结果，避免重复计算。
    def hydrate_scored_paper(self, source: str, paper_id: str) -> Optional[Dict[str, Any]]:
        row = self.get_paper_record(source, paper_id)
        if not row or not row.get("score_json") or not row.get("metadata_json"):
            return None

        metadata_raw = self._json_loads(row.get("metadata_json"), {})
        if not metadata_raw:
            return None

        published_raw = metadata_raw.get("published_date")
        published_date = None
        if published_raw:
            try:
                published_date = datetime.fromisoformat(published_raw)
            except ValueError:
                published_date = None

        paper_meta = PaperMetadata(
            paper_id=metadata_raw.get("paper_id") or paper_id,
            title=metadata_raw.get("title", ""),
            authors=metadata_raw.get("authors") or [],
            abstract=metadata_raw.get("abstract", ""),
            published_date=published_date,
            url=metadata_raw.get("url", ""),
            source=metadata_raw.get("source") or source,
            pdf_url=metadata_raw.get("pdf_url"),
            doi=metadata_raw.get("doi"),
            journal=metadata_raw.get("journal"),
            categories=metadata_raw.get("categories") or [],
            semantic_scholar_tldr=metadata_raw.get("semantic_scholar_tldr"),
            arxiv_id=metadata_raw.get("arxiv_id"),
            arxiv_url=metadata_raw.get("arxiv_url"),
        )

        score_response = WeightedScoreResponse.model_validate(
            self._json_loads(row.get("score_json"), {})
        )

        return {
            "paper_metadata": paper_meta,
            "paper_id": paper_meta.paper_id,
            "title": paper_meta.title,
            "authors": paper_meta.get_authors_string(),
            "abstract": row.get("abstract") or paper_meta.abstract,
            "abstract_cn": row.get("abstract_cn") or "",
            "url": row.get("url") or paper_meta.url,
            "pdf_url": row.get("pdf_url") or paper_meta.pdf_url,
            "published": paper_meta.published_date.strftime("%Y-%m-%d") if paper_meta.published_date else "N/A",
            "score_response": score_response,
            "analysis": self._json_loads(row.get("analysis_json"), None),
        }

    def upsert_scored_paper(self, run_id: str, source: str, scored: Dict[str, Any]) -> None:
        now = self._utcnow_iso()
        paper_meta = scored.get("paper_metadata")
        score_response = scored["score_response"]
        metadata_json = paper_meta.to_dict() if paper_meta else {
            "paper_id": scored.get("paper_id"),
            "title": scored.get("title"),
            "authors": [a.strip() for a in (scored.get("authors") or "").split(",") if a.strip()],
            "abstract": scored.get("abstract") or "",
            "published_date": None,
            "url": scored.get("url") or "",
            "source": source,
            "pdf_url": scored.get("pdf_url"),
            "doi": scored.get("doi"),
            "journal": scored.get("journal"),
            "categories": scored.get("categories") or [],
            "semantic_scholar_tldr": None,
            "arxiv_id": None,
            "arxiv_url": None,
        }

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO daily_papers (
                    source, paper_id, title, published_date, url, pdf_url, doi, journal,
                    is_qualified, total_score, passing_score, scoring_method,
                    first_run_id, last_run_id, score_completed_at, updated_at,
                    metadata_json, authors_json, categories_json, abstract, abstract_cn,
                    score_json, analysis_json, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          COALESCE((SELECT abstract_cn FROM daily_papers WHERE source = ? AND paper_id = ?), ''),
                          ?, COALESCE((SELECT analysis_json FROM daily_papers WHERE source = ? AND paper_id = ?), NULL), NULL)
                ON CONFLICT(source, paper_id) DO UPDATE SET
                    title = excluded.title,
                    published_date = excluded.published_date,
                    url = excluded.url,
                    pdf_url = excluded.pdf_url,
                    doi = excluded.doi,
                    journal = excluded.journal,
                    is_qualified = excluded.is_qualified,
                    total_score = excluded.total_score,
                    passing_score = excluded.passing_score,
                    scoring_method = excluded.scoring_method,
                    last_run_id = excluded.last_run_id,
                    score_completed_at = excluded.score_completed_at,
                    updated_at = excluded.updated_at,
                    metadata_json = excluded.metadata_json,
                    authors_json = excluded.authors_json,
                    categories_json = excluded.categories_json,
                    abstract = excluded.abstract,
                    score_json = excluded.score_json,
                    last_error = NULL
                """,
                (
                    source,
                    scored["paper_id"],
                    scored.get("title"),
                    metadata_json.get("published_date"),
                    scored.get("url") or metadata_json.get("url"),
                    scored.get("pdf_url") or metadata_json.get("pdf_url"),
                    metadata_json.get("doi"),
                    metadata_json.get("journal"),
                    1 if score_response.is_qualified else 0,
                    float(score_response.total_score),
                    float(score_response.passing_score),
                    getattr(score_response, "scoring_method", "keyword_weighted"),
                    run_id,
                    run_id,
                    now,
                    now,
                    self._json_dumps(metadata_json),
                    self._json_dumps(metadata_json.get("authors") or []),
                    self._json_dumps(metadata_json.get("categories") or []),
                    scored.get("abstract") or metadata_json.get("abstract") or "",
                    source,
                    scored["paper_id"],
                    self._json_dumps(score_response.model_dump()),
                    source,
                    scored["paper_id"],
                ),
            )
            conn.commit()

    def update_translation(
        self,
        run_id: str,
        source: str,
        paper_id: str,
        abstract_cn: str,
    ) -> None:
        now = self._utcnow_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_papers
                SET abstract_cn = ?,
                    translation_completed_at = ?,
                    last_run_id = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE source = ? AND paper_id = ?
                """,
                (abstract_cn or "", now, run_id, now, source, paper_id),
            )
            conn.commit()

    def update_analysis(
        self,
        run_id: str,
        source: str,
        paper_id: str,
        analysis: Optional[Dict[str, Any]],
    ) -> None:
        now = self._utcnow_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_papers
                SET analysis_json = ?,
                    analysis_completed_at = ?,
                    last_run_id = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE source = ? AND paper_id = ?
                """,
                (
                    self._json_dumps(analysis or {}),
                    now,
                    run_id,
                    now,
                    source,
                    paper_id,
                ),
            )
            conn.commit()

    def mark_completed(self, run_id: str, source: str, paper_id: str) -> None:
        now = self._utcnow_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_papers
                SET completed_run_id = ?,
                    completed_at = ?,
                    last_run_id = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE source = ? AND paper_id = ?
                """,
                (run_id, now, run_id, now, source, paper_id),
            )
            conn.commit()

    def update_last_error(self, source: str, paper_id: str, message: str) -> None:
        now = self._utcnow_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_papers
                SET last_error = ?,
                    updated_at = ?
                WHERE source = ? AND paper_id = ?
                """,
                (message, now, source, paper_id),
            )
            conn.commit()
