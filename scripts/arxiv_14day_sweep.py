"""Resumable, isolated arXiv category sweep with single-model MLSys screening.

Run from the repository root. This experiment uses its own SQLite database and
does not deliver reports or notifications into the daily workflow.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import signal
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.analysis_agent import AnalysisAgent  # noqa: E402
from config import settings  # noqa: E402
from sources.arxiv_source import ArxivSource  # noqa: E402

CATEGORIES = ("cs.LG", "cs.AI", "cs.DC", "cs.AR", "cs.NI", "cs.SE")
DB = ROOT / "data" / "experiments" / "arxiv_14day_sweep.sqlite"
LOCK = DB.with_suffix(".lock")
REPORT = DB.with_suffix(".md")


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS job (
            id INTEGER PRIMARY KEY CHECK (id = 1), window_end TEXT NOT NULL,
            model TEXT NOT NULL, started_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS categories (
            category TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending',
            found INTEGER NOT NULL DEFAULT 0, receipt_json TEXT,
            error TEXT, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS papers (
            paper_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL,
            score_json TEXT, abstract_cn TEXT, score_status TEXT NOT NULL DEFAULT 'pending',
            translation_status TEXT NOT NULL DEFAULT 'pending',
            error TEXT, scored_at TEXT
        );
        CREATE TABLE IF NOT EXISTS paper_categories (
            paper_id TEXT NOT NULL REFERENCES papers(paper_id),
            category TEXT NOT NULL REFERENCES categories(category),
            PRIMARY KEY (paper_id, category)
        );
    """)
    return conn


def initialize(conn: sqlite3.Connection) -> datetime:
    from scoring_policy import MLSYS_SINGLE_MODEL_V1

    if settings.normalized_score_strategy() != MLSYS_SINGLE_MODEL_V1:
        raise RuntimeError("当前配置未启用 MLSys 单模型评分，停止以防混用评分策略")
    model = settings.CHEAP_LLM.model_name
    if model != "deepseek-reasoner":
        raise RuntimeError(f"当前评分模型为 {model}，预期 deepseek-reasoner")
    row = conn.execute("SELECT * FROM job WHERE id = 1").fetchone()
    if row is None:
        end = datetime.now(timezone.utc)
        with conn:
            conn.execute(
                "INSERT INTO job VALUES (1, ?, ?, ?)",
                (end.isoformat(), model, end.isoformat()),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO categories(category) VALUES (?)",
                ((category,) for category in CATEGORIES),
            )
        return end
    if row["model"] != model:
        raise RuntimeError(f"数据库使用模型 {row['model']}，当前配置为 {model}；请保持原模型续跑")
    return datetime.fromisoformat(row["window_end"])


def scan(conn: sqlite3.Connection, end: datetime) -> None:
    source = ArxivSource(
        history_dir=DB.parent / "arxiv_history",
        proxy_dict=settings.get_proxy_dict("arxiv"),
        announcement_lookback_grace_days=0,
        load_legacy_history=False,
    )
    source.set_history_filtering_enabled(False)
    for category in CATEGORIES:
        row = conn.execute(
            "SELECT status FROM categories WHERE category = ?", (category,)
        ).fetchone()
        if row["status"] == "completed":
            continue
        print(f"[scan] {category}: 开始完整分页", flush=True)
        with conn:
            conn.execute(
                "UPDATE categories SET status='running', error=NULL WHERE category=?",
                (category,),
            )

        def record_receipt(receipt: dict) -> None:
            with conn:
                conn.execute(
                    "UPDATE categories SET receipt_json=? WHERE category=?",
                    (json.dumps(receipt, ensure_ascii=False), category),
                )

        try:
            papers = source.fetch_papers(
                14, [category], fetched_at=end, scan_receipt_callback=record_receipt,
                progress_callback=lambda domain, pages, count: print(
                    f"[scan] {domain}: 当前查询已读 {pages} 页、{count} 条窗口内记录",
                    flush=True,
                ),
            )
        except Exception as exc:
            with conn:
                conn.execute(
                    "UPDATE categories SET status='failed', error=? WHERE category=?",
                    (str(exc)[:1000], category),
                )
            raise
        with conn:
            for paper in papers:
                conn.execute(
                    "INSERT INTO papers(paper_id, metadata_json) VALUES (?, ?) "
                    "ON CONFLICT(paper_id) DO UPDATE SET metadata_json=excluded.metadata_json",
                    (paper.paper_id, json.dumps(paper.to_dict(), ensure_ascii=False)),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO paper_categories VALUES (?, ?)",
                    (paper.paper_id, category),
                )
            conn.execute(
                "UPDATE categories SET status='completed', found=?, completed_at=?, error=NULL "
                "WHERE category=?",
                (len(papers), datetime.now(timezone.utc).isoformat(), category),
            )
        print(f"[scan] {category}: {len(papers)} 篇；已保存", flush=True)


def score(conn: sqlite3.Connection) -> None:
    from sources.base_source import PaperMetadata

    agent = AnalysisAgent()
    rows = conn.execute(
        "SELECT paper_id, metadata_json, score_json, abstract_cn, "
        "score_status, translation_status FROM papers "
        "WHERE score_status != 'succeeded' OR "
        "(score_json IS NOT NULL AND translation_status = 'pending') "
        "ORDER BY paper_id"
    ).fetchall()
    print(f"[score] 待处理 {len(rows)} 篇；单模型逐篇评分，仅入选论文翻译摘要", flush=True)
    for index, row in enumerate(rows, 1):
        paper = PaperMetadata.from_dict(json.loads(row["metadata_json"]))
        try:
            if row["score_status"] == "succeeded":
                result = json.loads(row["score_json"])
            else:
                response = agent.score_paper_with_keywords(
                    title=paper.title, authors=paper.authors, abstract=paper.abstract,
                    keywords_dict={},
                )
                result = response.model_dump()
                with conn:
                    conn.execute(
                        "UPDATE papers SET score_json=?, score_status='succeeded', "
                        "scored_at=?, error=NULL WHERE paper_id=?",
                        (json.dumps(result, ensure_ascii=False),
                         datetime.now(timezone.utc).isoformat(), paper.paper_id),
                    )
            if result.get("is_qualified") and (paper.abstract or "").strip():
                if row["translation_status"] != "succeeded":
                    translated = agent.translate_abstract(paper.abstract)
                    if not translated or not translated.strip():
                        raise ValueError("摘要翻译返回空结果")
                    with conn:
                        conn.execute(
                            "UPDATE papers SET abstract_cn=?, translation_status='succeeded', "
                            "error=NULL WHERE paper_id=?",
                            (translated, paper.paper_id),
                        )
            else:
                with conn:
                    conn.execute(
                        "UPDATE papers SET translation_status='not_required', error=NULL "
                        "WHERE paper_id=?", (paper.paper_id,)
                    )
        except Exception as exc:
            with conn:
                conn.execute("UPDATE papers SET error=? WHERE paper_id=?", (str(exc)[:1000], paper.paper_id))
            print(f"[score] {index}/{len(rows)} {paper.paper_id}: 失败，续跑时重试: {exc}", flush=True)
            continue
        if index % 10 == 0 or index == len(rows):
            print(f"[score] 本轮 {index}/{len(rows)}；最新 {paper.paper_id}", flush=True)


def status(conn: sqlite3.Connection, top: int) -> None:
    job = conn.execute("SELECT * FROM job WHERE id=1").fetchone()
    if job is None:
        print("尚未启动任务")
        return
    print(f"固定窗口：{job['window_end']} UTC 往前 14 天；模型：{job['model']}")
    for row in conn.execute("SELECT * FROM categories ORDER BY rowid"):
        note = f"；错误：{row['error']}" if row["error"] else ""
        target = (
            "达到 1000 篇目标" if row["found"] >= 1000 else "不足 1000 篇"
        ) if row["status"] == "completed" else "扫描尚未完成"
        print(f"  {row['category']}: {row['status']}，{row['found']} 篇（{target}）{note}")
    counts = conn.execute("""
        SELECT COUNT(*) total,
          SUM(CASE WHEN score_status='succeeded' THEN 1 ELSE 0 END) scored,
          SUM(CASE WHEN score_status='succeeded' AND json_extract(score_json, '$.is_qualified')=1 THEN 1 ELSE 0 END) qualified,
          SUM(CASE WHEN translation_status='succeeded' THEN 1 ELSE 0 END) translated,
          SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) errors
        FROM papers
    """).fetchone()
    print("去重总数：{total}；已评分：{scored}；入选：{qualified}；已翻译：{translated}；失败待重试：{errors}".format(
        **{key: counts[key] or 0 for key in counts.keys()}
    ))
    if top:
        for row in conn.execute("""
            SELECT paper_id, metadata_json, score_json FROM papers
            WHERE score_status='succeeded' AND json_extract(score_json, '$.is_qualified')=1
            ORDER BY json_extract(score_json, '$.total_score') DESC LIMIT ?
        """, (top,)):
            paper = json.loads(row["metadata_json"])
            result = json.loads(row["score_json"])
            print(f"  {result['total_score']:4.1f}  {row['paper_id']}  {paper['title']}")


def export_report(conn: sqlite3.Connection) -> None:
    """Write an inspectable snapshot; this makes no model or network calls."""
    job = conn.execute("SELECT * FROM job WHERE id=1").fetchone()
    if job is None:
        print("尚未启动任务")
        return
    lines = [
        "# arXiv 14 天 MLSys 筛选快照", "",
        f"窗口结束（UTC）：{job['window_end']}；模型：{job['model']}", "",
        "## 分类扫描", "",
    ]
    for row in conn.execute("SELECT * FROM categories ORDER BY rowid"):
        lines.append(f"- {row['category']}：{row['status']}，{row['found']} 篇")
    lines += ["", "## 已入选论文", ""]
    for row in conn.execute("""
        SELECT paper_id, metadata_json, score_json, abstract_cn FROM papers
        WHERE score_status='succeeded' AND json_extract(score_json, '$.is_qualified')=1
        ORDER BY json_extract(score_json, '$.total_score') DESC
    """):
        paper = json.loads(row["metadata_json"])
        result = json.loads(row["score_json"])
        categories = [item[0] for item in conn.execute(
            "SELECT category FROM paper_categories WHERE paper_id=? ORDER BY category",
            (row["paper_id"],),
        )]
        lines += [
            f"### {paper['title']}", "",
            f"- arXiv：{row['paper_id']}；[原文]({paper['url']})",
            f"- 分类：{', '.join(categories)}；评分：{result['total_score']}",
            f"- 评分理由：{result.get('reasoning') or result.get('qualification_reason') or ''}",
            "",
            row["abstract_cn"] or paper.get("abstract") or "",
            "",
        ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"快照已写入 {REPORT}")


def run(conn: sqlite3.Connection) -> None:
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("已有一次扫描任务运行中") from exc
        old_handler = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            end = initialize(conn)
            scan(conn, end)
            score(conn)
            status(conn, 10)
        finally:
            signal.signal(signal.SIGTERM, old_handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "export"))
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    with connect() as conn:
        if args.command == "status":
            status(conn, max(0, args.top))
            return 0
        if args.command == "export":
            export_report(conn)
            return 0
        try:
            run(conn)
            return 0
        except KeyboardInterrupt:
            print("任务已中断；再次运行 run 即可续跑", flush=True)
            return 130
        except Exception as exc:
            print(f"任务失败，可修复后运行 run 续跑：{exc}", file=sys.stderr, flush=True)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
