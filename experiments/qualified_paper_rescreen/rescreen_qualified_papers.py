# 本文件由 AI 生成，主要是由于修改了论文评分prompt, 导致之前通过的某些论文不合标准，用这个脚本对其进行筛查。

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def _detect_root() -> Path:
    candidates = []
    try:
        candidates.append(Path(__file__).resolve().parents[2])
    except Exception:
        pass
    candidates.extend([Path("/app"), Path.cwd()])
    for candidate in candidates:
        if (candidate / "src").exists():
            return candidate
    raise RuntimeError("Could not locate project root containing src/")


ROOT = _detect_root()
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agents.analysis_agent import AnalysisAgent

APPLY_RUN_ID_PREFIX = "rescreen_apply"

DB_PATH = ROOT / "data" / "daily_research" / "daily_research.db"
OUTPUT_DIR = ROOT / "data" / "reports" / "daily_research" / "markdown" / "rescreen"


@dataclass
class RescreenRecord:
    title: str
    source: str
    paper_id: str
    old_score: float
    old_pass: bool
    new_score: float
    new_pass: bool
    passing_score: float
    delta: float
    categories: list[str]
    abstract_cn: str
    abstract: str
    reasoning: str
    model_judgments: list[dict[str, Any]]
    scoring_method: str


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _query_target_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                source,
                paper_id,
                title,
                abstract,
                abstract_cn,
                total_score,
                passing_score,
                is_qualified,
                scoring_method,
                categories_json,
                score_json
            FROM daily_papers
            WHERE completed_at IS NOT NULL AND is_qualified = 1
            ORDER BY published_date DESC, source, paper_id
            """
        ).fetchall()
        return list(rows)
    finally:
        conn.close()


def _build_record(agent: AnalysisAgent, row: sqlite3.Row) -> RescreenRecord:
    source = row["source"] or ""
    paper_id = row["paper_id"] or ""
    title = row["title"] or ""
    abstract = row["abstract"] or ""
    abstract_cn = row["abstract_cn"] or ""
    categories = _json_loads(row["categories_json"], [])
    old_score_json = _json_loads(row["score_json"], {})
    old_score = float(old_score_json.get("total_score", row["total_score"] or 0.0) or 0.0)
    old_pass = bool(old_score_json.get("is_qualified", row["is_qualified"] or 0))

    result = agent.score_paper(
        title=title,
        authors="",
        abstract=abstract,
        keywords_dict={},
        paper_id=paper_id,
        source=source,
        categories=categories,
    )

    return RescreenRecord(
        title=title,
        source=source,
        paper_id=paper_id,
        old_score=old_score,
        old_pass=old_pass,
        new_score=float(result.total_score),
        new_pass=bool(result.is_qualified),
        passing_score=float(result.passing_score),
        delta=float(result.total_score) - old_score,
        categories=categories,
        abstract_cn=abstract_cn,
        abstract=abstract,
        reasoning=result.reasoning,
        model_judgments=result.model_judgments,
        scoring_method=result.scoring_method,
    )


def _render_markdown(records: list[RescreenRecord], generated_at: str, db_path: Path) -> str:
    low_score_records = [r for r in records if r.new_score < 4]
    lines = [
        "# Qualified paper rescreen review",
        "",
        "This is an experiment-only dry-run artifact. It does not modify the database.",
        "",
        f"- Generated at: {generated_at}",
        f"- Database: `{db_path}`",
        f"- Rescored papers: {len(records)}",
        f"- Low-score candidates (`new_score < 4`): {len(low_score_records)}",
        "",
        "## Low-score candidates",
        "",
    ]

    if not low_score_records:
        lines.append("No papers scored below 4.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Title | Source | Paper ID | Old score | New score | Δ | New pass | Categories | 中文摘要 |",
            "|---|---|---|---:|---:|---:|---|---|---|",
        ]
    )
    for record in low_score_records:
        title = record.title.replace("|", "\\|")
        categories = ", ".join(record.categories).replace("|", "\\|") if record.categories else ""
        abstract_cn = (record.abstract_cn or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {title} | {record.source} | {record.paper_id} | {record.old_score:.2f} | {record.new_score:.2f} | {record.delta:.2f} | {'yes' if record.new_pass else 'no'} | {categories} | {abstract_cn} |"
        )

    return "\n".join(lines) + "\n"


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _build_score_json(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_score": float(record["new_score"]),
        "keyword_scores": {},
        "author_bonus": 0,
        "expert_authors_found": [],
        "passing_score": float(record["passing_score"]),
        "is_qualified": bool(record["new_pass"]),
        "reasoning": record.get("reasoning", ""),
        "tldr": "",
        "extracted_keywords": [],
        "scoring_method": record.get("scoring_method", "mlsys_multi_model"),
        "model_judgments": record.get("model_judgments", []),
        "successful_model_count": sum(
            1 for item in record.get("model_judgments", []) if not item.get("fallback_due_to_error")
        ),
        "fallback_model_count": sum(
            1 for item in record.get("model_judgments", []) if item.get("fallback_due_to_error")
        ),
        "agreement_ratio": 0.0,
        "aggregate_paper_type": "",
        "preliminary_score": None,
        "smart_review_used": False,
        "smart_review_model": "",
        "final_model_count": len(record.get("model_judgments", [])),
    }


def _apply_snapshot(db_path: Path, snapshot_path: Path) -> tuple[int, str]:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    now = datetime.now().isoformat()
    run_id = f"{APPLY_RUN_ID_PREFIX}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

    conn = sqlite3.connect(db_path)
    try:
        updated = 0
        for record in records:
            score_json = _build_score_json(record)
            cur = conn.execute(
                """
                UPDATE daily_papers
                SET is_qualified = ?,
                    total_score = ?,
                    passing_score = ?,
                    scoring_method = ?,
                    score_json = ?,
                    score_completed_at = ?,
                    last_run_id = ?,
                    updated_at = ?,
                    last_error = NULL
                WHERE source = ? AND paper_id = ?
                """,
                (
                    1 if record.get("new_pass") else 0,
                    float(record.get("new_score", 0.0)),
                    float(record.get("passing_score", 0.0)),
                    record.get("scoring_method", "mlsys_multi_model"),
                    json.dumps(score_json, ensure_ascii=False),
                    now,
                    run_id,
                    now,
                    record["source"],
                    record["paper_id"],
                ),
            )
            updated += cur.rowcount
        conn.commit()
        return updated, run_id
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experiment-only rescreen script for currently qualified papers."
    )
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--apply-json", type=Path, default=None)
    return parser.parse_args()


def _run_rescreen(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = _query_target_rows(args.db_path)
    if args.limit > 0:
        rows = rows[: args.limit]

    generated_at = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    total = len(rows)
    started = time.perf_counter()
    records: list[RescreenRecord] = []
    max_workers = max(1, args.workers)

    print(f"Starting rescreen for {total} papers with workers={max_workers}", flush=True)

    def _score_row(row: sqlite3.Row) -> RescreenRecord:
        agent = AnalysisAgent()
        return _build_record(agent, row)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_score_row, row) for row in rows]
        for idx, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            records.append(record)
            elapsed = time.perf_counter() - started
            avg = elapsed / idx if idx else 0.0
            eta = avg * (total - idx)
            print(
                f"[{idx}/{total}] {record.source}:{record.paper_id} score={record.new_score:.2f} "
                f"pass={'yes' if record.new_pass else 'no'} | {record.title[:80]}",
                flush=True,
            )
            if idx == total or idx % 5 == 0:
                print(
                    f"progress {idx}/{total} | elapsed={_format_duration(elapsed)} | "
                    f"avg={avg:.1f}s/paper | eta={_format_duration(eta)}",
                    flush=True,
                )

    records.sort(key=lambda r: (r.source, r.paper_id))

    full_payload = {
        "generated_at": generated_at,
        "db_path": str(args.db_path),
        "paper_count": len(records),
        "low_score_threshold": 4,
        "records": [asdict(record) for record in records],
    }

    json_path = args.output_dir / f"rescreen_full_{generated_at}.json"
    md_path = args.output_dir / f"rescreen_review_{generated_at}.md"
    json_path.write_text(json.dumps(full_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(records, generated_at, args.db_path), encoding="utf-8")

    print(f"Rescored papers: {len(records)}")
    print(f"Full snapshot: {json_path}")
    print(f"Review markdown: {md_path}")


def main() -> None:
    args = parse_args()
    if args.apply_json:
        updated, run_id = _apply_snapshot(args.db_path, args.apply_json)
        print(f"Applied snapshot: {args.apply_json}")
        print(f"Updated papers: {updated}")
        print(f"Apply run_id: {run_id}")
        return
    _run_rescreen(args)


if __name__ == "__main__":
    main()
