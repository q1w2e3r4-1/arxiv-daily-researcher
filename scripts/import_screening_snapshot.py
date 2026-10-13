"""Import completed screening results into searchable SQLite history.

Frozen experiment inputs stay read-only. Original archive records are retained
in an audit table before updating history; no delivery rows or preferences are
created. This does not run scoring, translation, or PDF analysis.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils.daily_research_store import DailyResearchStore


def import_snapshot(snapshot: Path, target: Path, translations: Path | None = None,
                    *, apply: bool = False) -> dict:
    with sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        experiment = dict(conn.execute("SELECT * FROM experiment WHERE id=1").fetchone())
        rows = [dict(row) for row in conn.execute("SELECT * FROM papers ORDER BY paper_id")]
    if not rows or any(row["status"] != "succeeded" or not row["new_score_json"]
                       or not row["completed_at"] for row in rows):
        raise ValueError("Snapshot must have successful results and completion times for every paper")
    decoded = [(row, json.loads(row["metadata_json"]), json.loads(row["new_score_json"])) for row in rows]
    for row, metadata, score in decoded:
        if metadata.get("paper_id") != row["paper_id"] or not isinstance(score.get("is_qualified"), bool):
            raise ValueError("Invalid paper identity or qualification in snapshot")
        datetime.fromisoformat(row["completed_at"])
    summary = {"papers": len(rows), "qualified": sum(score["is_qualified"] for _, _, score in decoded),
               "prompt_version": experiment["prompt_version"], "applied": apply}
    if not apply:
        return summary
    translated = json.loads(translations.read_text()) if translations else {}
    store = DailyResearchStore(target)
    with store._connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS screening_review_imports (
            prompt_sha256 TEXT NOT NULL, source TEXT NOT NULL, paper_id TEXT NOT NULL,
            experiment_json TEXT NOT NULL, review_score_json TEXT NOT NULL,
            original_record_json TEXT, reviewed_at TEXT NOT NULL,
            PRIMARY KEY (prompt_sha256, source, paper_id)
        )""")
    counts = Counter()
    for row, metadata, score in decoded:
        source = str(metadata.get("source") or "arxiv")
        paper_id = row["paper_id"]
        existing = store.get_paper_record(source, paper_id)
        completed = datetime.fromisoformat(row["completed_at"])
        if completed.tzinfo:
            completed = completed.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        completed_at = completed.isoformat()
        score.update(screening_prompt_version=experiment["prompt_version"],
                     screening_model=experiment["model"],
                     screening_prompt_sha256=experiment["prompt_sha256"],
                     screening_origin="frozen_review")
        with store._connect() as conn:
            conn.execute("""INSERT OR IGNORE INTO screening_review_imports VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (experiment["prompt_sha256"], source, paper_id,
                          json.dumps(experiment, ensure_ascii=False), row["new_score_json"],
                          json.dumps(dict(existing), ensure_ascii=False) if existing else None, completed_at))
        # Keep output from a newer daily run, including its stage fingerprints.
        existing_score_at = str(existing["scored_at"] or "") if existing else ""
        if existing and existing_score_at > completed_at:
            counts["skipped_newer_score"] += 1
            continue
        abstract_cn = (existing["abstract_cn"] if existing else None) or translated.get(paper_id, "")
        analysis_json = existing["analysis_json"] if existing else None
        payload = {
            "source": source, "paper_id": paper_id,
            "canonical_id": metadata.get("canonical_id") or paper_id,
            "version": metadata.get("version") or 0, "paper_json": metadata,
            "score_json": json.dumps(score, ensure_ascii=False), "abstract_cn": abstract_cn,
            "analysis_json": analysis_json, "score_status": "succeeded",
            "tldr_status": "succeeded" if score.get("tldr") else "pending",
            "translation_status": "succeeded" if abstract_cn else "pending",
            "analysis_status": "succeeded" if analysis_json else "pending",
            "completed_at": completed_at, "report_at": completed_at,
        }
        counts[store.import_legacy_paper(payload, delivered=False)] += 1
    summary.update(counts)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--translations", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply:
        from utils.run_lock import database_restore_activity_gate
        # Exclude every worker activity and prevent a concurrent database restore.
        with database_restore_activity_gate(exclusive=True, nonblocking=True):
            result = import_snapshot(args.snapshot, args.target, args.translations, apply=True)
    else:
        result = import_snapshot(args.snapshot, args.target, args.translations)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
