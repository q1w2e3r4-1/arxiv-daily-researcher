"""Durably rescreen a frozen set of previously selected papers.

The source sweep database is read only. The new prompt and results live in this
worktree, so an active sweep can continue using its original prompt unchanged.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "configs/templates/reports/mlsys_screening_prompt.json"
OUTPUT = ROOT / "data/experiments/efficiency_prompt_rescreen"
DB = OUTPUT / "rescreen.sqlite"
REPORT = OUTPUT / "comparison.md"
LOCK = OUTPUT / "rescreen.lock"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS experiment (
            id INTEGER PRIMARY KEY CHECK (id=1), prompt_sha256 TEXT NOT NULL,
            prompt_version TEXT NOT NULL, model TEXT NOT NULL,
            source_window_end TEXT NOT NULL, frozen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS papers (
            paper_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL,
            old_score_json TEXT NOT NULL, new_score_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending', error TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, latency_seconds REAL,
            completed_at TEXT
        );
    """)


def freeze(source_db: Path) -> None:
    if DB.exists():
        with connect(DB) as existing:
            initialize(existing)
            if existing.execute("SELECT 1 FROM experiment WHERE id=1").fetchone():
                raise RuntimeError("复评样本已冻结；不会重新选取后来入选的论文")
    prompt_bytes = PROMPT.read_bytes()
    prompt = json.loads(prompt_bytes)
    source = sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)
    try:
        job = source.execute("SELECT window_end, model FROM job WHERE id=1").fetchone()
        if job is None:
            raise RuntimeError("原扫描数据库没有任务元数据")
        rows = source.execute("""
            SELECT paper_id, metadata_json, score_json FROM papers
            WHERE score_status='succeeded'
              AND json_extract(score_json, '$.is_qualified')=1
            ORDER BY paper_id
        """).fetchall()
    finally:
        source.close()
    if not rows:
        raise RuntimeError("原扫描数据库当前没有入选论文")
    with connect(DB) as conn:
        initialize(conn)
        with conn:
            conn.execute("INSERT INTO experiment VALUES (1, ?, ?, ?, ?, ?)", (
                hashlib.sha256(prompt_bytes).hexdigest(), prompt["version"],
                job[1], job[0], utc_now(),
            ))
            conn.executemany(
                "INSERT INTO papers(paper_id, metadata_json, old_score_json) VALUES (?, ?, ?)",
                rows,
            )
    print(f"已冻结 {len(rows)} 篇；旧评分保持只读；输出：{DB}", flush=True)


def freeze_preview(source_db: Path) -> None:
    """Freeze the exact candidates in a prior preview without changing it."""
    if DB.exists():
        with connect(DB) as existing:
            initialize(existing)
            if existing.execute("SELECT 1 FROM experiment WHERE id=1").fetchone():
                raise RuntimeError("复评样本已冻结；不会覆盖已有结果")
    prompt_bytes = PROMPT.read_bytes()
    prompt = json.loads(prompt_bytes)
    source = sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)
    try:
        job = source.execute("SELECT model, source_window_end FROM experiment WHERE id=1").fetchone()
        if job is None:
            raise RuntimeError("预览数据库没有任务元数据")
        rows = source.execute("""
            SELECT paper_id, metadata_json, old_score_json FROM papers
            ORDER BY paper_id
        """).fetchall()
    finally:
        source.close()
    if not rows:
        raise RuntimeError("预览数据库没有论文")
    with connect(DB) as conn:
        initialize(conn)
        with conn:
            conn.execute("INSERT INTO experiment VALUES (1, ?, ?, ?, ?, ?)", (
                hashlib.sha256(prompt_bytes).hexdigest(), prompt["version"],
                job[0], job[1], utc_now(),
            ))
            conn.executemany(
                "INSERT INTO papers(paper_id, metadata_json, old_score_json) VALUES (?, ?, ?)", rows
            )
    print(f"已冻结预览候选 {len(rows)} 篇；输出：{DB}", flush=True)


def check_experiment(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM experiment WHERE id=1").fetchone()
    if row is None:
        raise RuntimeError("请先 freeze 入选论文样本")
    current_sha = hashlib.sha256(PROMPT.read_bytes()).hexdigest()
    if row["prompt_sha256"] != current_sha:
        raise RuntimeError("prompt 已变化；停止以避免在同一复评中混用版本")
    return row


def run(limit: int) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from agents.analysis_agent import AnalysisAgent
    from config import settings
    from scoring_policy import MLSYS_SINGLE_MODEL_V1

    if settings.normalized_score_strategy() != MLSYS_SINGLE_MODEL_V1:
        raise RuntimeError("配置未启用 MLSys 单模型评分")
    if settings.CHEAP_LLM.model_name != "deepseek-reasoner":
        raise RuntimeError("评分模型必须是 deepseek-reasoner")
    settings.LLM_REQUEST_POOL_ENABLED = True
    settings.LLM_REQUESTS_PER_MINUTE = 3
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("已有复评进程运行中") from exc
        run_locked(limit, AnalysisAgent, settings)


def ensure_frozen_prompt(settings) -> None:
    frozen_prompts = json.loads(PROMPT.read_bytes())["prompts"]
    effective = settings.load_report_template("mlsys_screening_prompt.json")["prompts"]
    if effective != frozen_prompts:
        raise RuntimeError("网页自定义 Prompt 与冻结复评文件不同；停止以避免混用评分规则")


def run_locked(limit: int, agent_type, settings) -> None:
    ensure_frozen_prompt(settings)
    with connect(DB) as conn:
        initialize(conn)
        experiment = check_experiment(conn)
        if experiment["model"] != settings.CHEAP_LLM.model_name:
            raise RuntimeError("复评模型与冻结样本中的旧模型不一致")
        rows = conn.execute("""
            SELECT paper_id, metadata_json FROM papers
            WHERE status IN ('pending','failed') ORDER BY paper_id LIMIT ?
        """, (limit if limit > 0 else 1_000_000,)).fetchall()
        agent = agent_type()
        print(f"本轮待评 {len(rows)} 篇；模型 {settings.CHEAP_LLM.model_name}；复评上限 3 请求/分钟", flush=True)
        for index, row in enumerate(rows, 1):
            metadata = json.loads(row["metadata_json"])
            started = time.monotonic()
            try:
                result = agent.score_paper_with_keywords(
                    title=metadata["title"], authors=metadata["authors"],
                    abstract=metadata["abstract"], keywords_dict={},
                )
                payload = result.model_dump()
                with conn:
                    conn.execute("""
                        UPDATE papers SET new_score_json=?, status='succeeded',
                            error=NULL, attempts=attempts+1, latency_seconds=?,
                            completed_at=? WHERE paper_id=?
                    """, (json.dumps(payload, ensure_ascii=False),
                          time.monotonic()-started, utc_now(), row["paper_id"]))
                print(f"[{index}/{len(rows)}] {row['paper_id']} -> "
                      f"{'入选' if payload['is_qualified'] else '剔除'} "
                      f"({payload['total_score']})", flush=True)
            except Exception as exc:
                with conn:
                    conn.execute("""
                        UPDATE papers SET status='failed', error=?,
                            attempts=attempts+1, latency_seconds=?
                        WHERE paper_id=?
                    """, (str(exc)[:1000], time.monotonic()-started, row["paper_id"]))
                print(f"[{index}/{len(rows)}] {row['paper_id']} 失败，续跑时重试：{exc}", flush=True)


def status(conn: sqlite3.Connection) -> None:
    initialize(conn)
    exp = conn.execute("SELECT * FROM experiment WHERE id=1").fetchone()
    if exp is None:
        print("尚未冻结样本")
        return
    row = conn.execute("""
        SELECT COUNT(*) total,
          SUM(CASE WHEN status='succeeded' THEN 1 ELSE 0 END) done,
          SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) pending,
          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
          SUM(CASE WHEN status='succeeded' AND json_extract(new_score_json,'$.is_qualified')=1 THEN 1 ELSE 0 END) retained,
          SUM(CASE WHEN status='succeeded' AND json_extract(new_score_json,'$.is_qualified')=0 THEN 1 ELSE 0 END) removed
        FROM papers
    """).fetchone()
    print(f"冻结样本：{row['total']} 篇；prompt v{exp['prompt_version']}；模型：{exp['model']}")
    print("已重评 {done}；保留 {retained}；剔除 {removed}；待评 {pending}；失败待重试 {failed}".format(
        **{key: row[key] or 0 for key in row.keys()}
    ))


def report(conn: sqlite3.Connection) -> None:
    exp = check_experiment(conn)
    lines = ["# 效率导向 prompt 复评", "",
             f"旧样本窗口结束：{exp['source_window_end']} UTC；新 prompt v{exp['prompt_version']}；模型：{exp['model']}", ""]
    status_row = conn.execute("SELECT COUNT(*) FROM papers WHERE status='succeeded'").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    lines += [f"已重评 {status_row}/{total} 篇。", ""]
    for label, passed in (("仍入选", 1), ("被剔除", 0)):
        lines += [f"## {label}", ""]
        for row in conn.execute("""
            SELECT paper_id, metadata_json, old_score_json, new_score_json
            FROM papers WHERE status='succeeded'
              AND json_extract(new_score_json,'$.is_qualified')=?
            ORDER BY json_extract(new_score_json,'$.total_score') DESC, paper_id
        """, (passed,)):
            metadata = json.loads(row["metadata_json"])
            old = json.loads(row["old_score_json"])
            new = json.loads(row["new_score_json"])
            lines += [f"### {metadata['title']}", "",
                      f"- arXiv：{row['paper_id']}；[原文]({metadata['url']})",
                      f"- 旧分数 {old['total_score']} → 新分数 {new['total_score']}",
                      f"- 新理由：{new.get('reasoning') or ''}", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"比较报告：{REPORT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "freeze-preview", "run", "status", "report"))
    parser.add_argument("--source-db", type=Path)
    parser.add_argument("--output-dir", type=Path, help="独立存放本轮复评结果的目录")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.output_dir is not None:
        global OUTPUT, DB, REPORT, LOCK
        OUTPUT = args.output_dir.resolve()
        DB = OUTPUT / "rescreen.sqlite"
        REPORT = OUTPUT / "comparison.md"
        LOCK = OUTPUT / "rescreen.lock"
    if args.command == "freeze":
        if args.source_db is None:
            parser.error("freeze 需要 --source-db")
        freeze(args.source_db)
        return 0
    if args.command == "freeze-preview":
        if args.source_db is None:
            parser.error("freeze-preview 需要 --source-db")
        freeze_preview(args.source_db)
        return 0
    with connect(DB) as conn:
        if args.command == "run":
            run(args.limit)
        elif args.command == "status":
            status(conn)
        else:
            report(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
