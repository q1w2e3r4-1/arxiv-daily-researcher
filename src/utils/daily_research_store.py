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
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.analysis_agent import WeightedScoreResponse
from sources.base_source import PaperMetadata

logger = logging.getLogger(__name__)

_REPORT_INCLUDE_MANUAL_FILTERED_KEY = "report_include_manually_filtered"


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

                CREATE TABLE IF NOT EXISTS daily_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

            run_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(daily_runs)").fetchall()
            }
            if "date_from" not in run_columns:
                conn.execute("ALTER TABLE daily_runs ADD COLUMN date_from TEXT")
            if "date_to" not in run_columns:
                conn.execute("ALTER TABLE daily_runs ADD COLUMN date_to TEXT")

            paper_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(daily_papers)").fetchall()
            }
            if "manually_filtered" not in paper_columns:
                conn.execute(
                    "ALTER TABLE daily_papers ADD COLUMN manually_filtered INTEGER NOT NULL DEFAULT 0"
                )
            if "manually_filtered_at" not in paper_columns:
                conn.execute("ALTER TABLE daily_papers ADD COLUMN manually_filtered_at TEXT")

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

    def register_candidates(
        self, run_id: str, papers_by_source: Dict[str, List[PaperMetadata]]
    ) -> int:
        """在应用本轮处理上限前，持久化本次发现的全部候选论文。"""
        now = self._utcnow_iso()
        rows = []
        for source, papers in papers_by_source.items():
            for paper in papers:
                metadata = paper.to_dict()
                rows.append(
                    (
                        source, paper.paper_id, paper.title,
                        metadata.get("published_date"), paper.url, paper.pdf_url,
                        paper.doi, paper.journal, run_id, run_id, now,
                        self._json_dumps(metadata), self._json_dumps(paper.authors),
                        self._json_dumps(paper.categories), paper.abstract,
                    )
                )
        if not rows:
            return 0
        with self._get_connection() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO daily_papers (
                    source, paper_id, title, published_date, url, pdf_url, doi, journal,
                    first_run_id, last_run_id, updated_at, metadata_json,
                    authors_json, categories_json, abstract
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            inserted = conn.total_changes - before
            conn.commit()
        return inserted

    @staticmethod
    def _paper_from_metadata(metadata: Dict[str, Any], source: str, paper_id: str) -> PaperMetadata:
        published_raw = metadata.get("published_date")
        published_date = datetime.fromisoformat(published_raw) if published_raw else None
        return PaperMetadata(
            paper_id=metadata.get("paper_id") or paper_id,
            title=metadata.get("title", ""),
            authors=metadata.get("authors") or [],
            abstract=metadata.get("abstract", ""),
            published_date=published_date,
            url=metadata.get("url", ""),
            source=metadata.get("source") or source,
            pdf_url=metadata.get("pdf_url"),
            doi=metadata.get("doi"),
            journal=metadata.get("journal"),
            categories=metadata.get("categories") or [],
            semantic_scholar_tldr=metadata.get("semantic_scholar_tldr"),
            arxiv_id=metadata.get("arxiv_id"),
            arxiv_url=metadata.get("arxiv_url"),
        )

    def get_unfinished_papers(
        self,
        enabled_sources: List[str],
        default_limit: int,
        limits_by_source: Optional[Dict[str, int]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> tuple[Dict[str, List[PaperMetadata]], Dict[str, int]]:
        """优先恢复未完成阶段，再处理较早登记的候选；上限按来源计算。"""
        if default_limit < 0:
            raise ValueError("max_results 不能为负数")
        selected: Dict[str, List[PaperMetadata]] = {}
        pending_counts: Dict[str, int] = {}
        limits_by_source = limits_by_source or {}
        with self._get_connection() as conn:
            for source in enabled_sources:
                limit = int(limits_by_source.get(source, default_limit))
                if limit < 0:
                    raise ValueError(f"{source} 的 max_results 不能为负数")
                where = "source = ? AND completed_at IS NULL AND metadata_json IS NOT NULL"
                params: list[Any] = [source]
                if date_from and date_to:
                    where += " AND substr(published_date, 1, 10) BETWEEN ? AND ?"
                    params.extend([date_from.isoformat(), date_to.isoformat()])
                pending_counts[source] = conn.execute(
                    f"SELECT COUNT(*) FROM daily_papers WHERE {where}", params
                ).fetchone()[0]
                rows = conn.execute(
                    f"""
                    SELECT paper_id, metadata_json FROM daily_papers
                    WHERE {where}
                    ORDER BY CASE WHEN score_json IS NOT NULL THEN 0 ELSE 1 END,
                             updated_at ASC, published_date ASC, paper_id ASC
                    LIMIT ?
                    """,
                    [*params, limit if limit > 0 else -1],
                ).fetchall()
                selected[source] = [
                    self._paper_from_metadata(
                        self._json_loads(row["metadata_json"], {}), source, row["paper_id"]
                    )
                    for row in rows
                ]
        return selected, pending_counts

    # 尝试从数据库中恢复论文的评分、翻译、分析结果，避免重复计算。
    def hydrate_scored_paper(self, source: str, paper_id: str) -> Optional[Dict[str, Any]]:
        row = self.get_paper_record(source, paper_id)
        if not row or not row.get("score_json") or not row.get("metadata_json"):
            return None

        metadata_raw = self._json_loads(row.get("metadata_json"), {})
        if not metadata_raw:
            return None

        try:
            paper_meta = self._paper_from_metadata(metadata_raw, source, paper_id)
        except ValueError:
            return None

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
            "manually_filtered": bool(row.get("manually_filtered") or 0),
            "manually_filtered_at": row.get("manually_filtered_at"),
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

    def get_manual_filter_states(
        self, source: str, paper_ids: list[str]
    ) -> Dict[str, Dict[str, Any]]:
        if not paper_ids:
            return {}
        placeholders = ", ".join("?" for _ in paper_ids)
        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT paper_id, manually_filtered, manually_filtered_at
                FROM daily_papers
                WHERE source = ? AND paper_id IN ({placeholders})
                """,
                (source, *paper_ids),
            ).fetchall()
        return {
            row["paper_id"]: {
                "manually_filtered": bool(row["manually_filtered"] or 0),
                "manually_filtered_at": row["manually_filtered_at"],
            }
            for row in rows
        }

    def set_manual_filter(self, source: str, paper_id: str, enabled: bool) -> None:
        now = self._utcnow_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE daily_papers
                SET manually_filtered = ?,
                    manually_filtered_at = CASE
                        WHEN ? THEN ?
                        ELSE manually_filtered_at
                    END,
                    updated_at = ?
                WHERE source = ? AND paper_id = ?
                """,
                (1 if enabled else 0, 1 if enabled else 0, now, now, source, paper_id),
            )
            conn.commit()

    def get_report_include_manually_filtered(self) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM daily_settings WHERE key = ?",
                (_REPORT_INCLUDE_MANUAL_FILTERED_KEY,),
            ).fetchone()
        if not row:
            return False
        return bool(self._json_loads(row["value_json"], False))

    def set_report_include_manually_filtered(self, enabled: bool) -> None:
        now = self._utcnow_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO daily_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _REPORT_INCLUDE_MANUAL_FILTERED_KEY,
                    self._json_dumps(bool(enabled)),
                    now,
                ),
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
