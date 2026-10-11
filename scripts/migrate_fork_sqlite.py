"""Import the q1w2e3r4-1 fork's SQLite ledger into an empty upstream ledger.

Use a consistent SQLite backup of the old database as the source.  This tool
opens that source read-only and refuses to overwrite an existing target.
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from agents.analysis_agent import Stage2Response, WeightedScoreResponse
from sources.base_source import PaperMetadata
from utils.daily_research_store import DailyResearchStore


def textify(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(f'- {textify(item)}' for item in value)
    if isinstance(value, dict):
        return '\n'.join(f'{key}: {textify(item)}' for key, item in value.items())
    return '' if value is None else str(value)


def normalize_analysis(raw):
    if not raw:
        return None
    payload = json.loads(raw)
    for key in ('methodology', 'relevance_to_keywords'):
        payload[key] = textify(payload.get(key))
    Stage2Response.model_validate(payload)
    return json.dumps(payload, ensure_ascii=False)


def rewrite_report_path(value, source_data_root, target_data_root):
    if not isinstance(value, str) or target_data_root is None:
        return value
    normalized = value.replace('\\', '/')
    prefixes = ['/app/data/']
    if source_data_root is not None:
        prefixes.insert(0, str(source_data_root.resolve()).rstrip('/') + '/')
    for prefix in prefixes:
        if normalized.startswith(prefix):
            return str(target_data_root.resolve() / normalized[len(prefix):])
    return value


def _run_into(source_path, target_path, source_data_root=None, target_data_root=None):
    source_path = source_path.resolve()
    target_path = target_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if target_path.exists():
        raise RuntimeError('target exists; refusing to overwrite')
    source = sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    source_columns = {r['name'] for r in source.execute('PRAGMA table_info(daily_papers)')}
    if 'metadata_json' not in source_columns or 'paper_json' in source_columns:
        raise RuntimeError('source does not match old fork schema')
    store = DailyResearchStore(target_path)
    counts = Counter()
    delivered_identities = set()
    run_reports = {}
    run_finished_at = {}
    with store._connect() as dest:
        for row in source.execute('SELECT * FROM daily_runs ORDER BY started_at'):
            status = row['status'] if row['status'] in ('completed', 'failed') else 'failed'
            original_paths = json.loads(row['report_paths_json'] or '{}')
            run_reports[row['run_id']] = {
                key: rewrite_report_path(value, source_data_root, target_data_root)
                for key, value in original_paths.items()
            }
            run_finished_at[row['run_id']] = row['completed_at']
            dest.execute('''INSERT INTO daily_runs
                (run_id, started_at, scan_started_at, scan_days, scanned_sources_json,
                 completed_at, status, total_papers, error, report_paths_json, run_kind)
                VALUES (?, ?, NULL, ?, ?, ?, ?, 0, ?, ?, 'daily')''',
                (row['run_id'], row['started_at'], row['search_days'], row['enabled_sources_json'],
                 row['completed_at'], status,
                 row['error_message'] or ('Imported stale running run' if row['status'] == 'running' else None),
                 json.dumps(run_reports[row['run_id']], ensure_ascii=False)
                 if row['report_paths_json'] else None))
            counts['runs'] += 1
        for row in source.execute('SELECT * FROM daily_papers ORDER BY source,paper_id'):
            paper = PaperMetadata.from_dict(json.loads(row['metadata_json']))
            if paper.source != row['source'] or paper.paper_id != row['paper_id']:
                raise RuntimeError(f'identity mismatch: {row["paper_id"]}')
            raw_score = json.loads(row['score_json']) if row['score_json'] else None
            if raw_score is not None and raw_score.get('scoring_method') == 'mlsys_multi_model':
                # Preserve the historical committee identity. The upstream
                # model's default strategy would otherwise call it keyword V1.
                raw_score['strategy_id'] = 'mlsys_multi_model'
            score_json = json.dumps(raw_score, ensure_ascii=False) if raw_score else None
            score = WeightedScoreResponse.model_validate_json(score_json) if score_json else None
            analysis = normalize_analysis(row['analysis_json'])
            delivered = bool(row['completed_at'])
            is_qualified = bool(score and score.is_qualified)
            tldr = bool(score and score.tldr and score.tldr.strip())
            translated = bool(row['abstract_cn'] and row['abstract_cn'].strip())
            scored_at = row['score_completed_at'] or (row['updated_at'] if score else None)
            first_seen_at = scored_at or row['updated_at'] or '1970-01-01T00:00:00'
            last_seen_at = row['updated_at'] or first_seen_at
            canonical_id = paper.canonical_id or paper.paper_id
            version = paper.version or 0
            dest.execute('''INSERT INTO daily_papers
                (source,paper_id,canonical_id,version,first_seen_at,last_seen_at,
                 run_id,paper_json,score_json,abstract_cn,analysis_json,
                 scored_at,translated_at,analyzed_at,completed_at,last_error,
                 score_status,tldr_status,translation_status,analysis_status,
                 retry_count,queue_scope,legacy_report_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'daily',?)''',
                (row['source'],row['paper_id'],canonical_id,version,first_seen_at,last_seen_at,
                 row['last_run_id'],json.dumps(paper.to_dict(),ensure_ascii=False),score_json,
                 row['abstract_cn'],analysis,scored_at,row['translation_completed_at'],
                 row['analysis_completed_at'],row['completed_at'],row['last_error'],
                 'succeeded' if score else 'pending', 'succeeded' if tldr else 'pending',
                 'succeeded' if translated else ('not_required' if delivered or not is_qualified else 'pending'),
                 'succeeded' if analysis else ('not_required' if delivered or not is_qualified else 'pending'),
                 row['completed_at']))
            if delivered:
                delivered_identities.add((row['source'], canonical_id, version))
                delivery_run = row['completed_run_id'] or row['last_run_id'] or 'fork_import'
                report_paths = run_reports.get(delivery_run) or {}
                report_path = report_paths.get(row['source'] + '_html') or report_paths.get(row['source'])
                report_at = run_finished_at.get(delivery_run) or row['completed_at']
                dest.execute('''INSERT OR IGNORE INTO paper_deliveries
                    (run_id,source,paper_id,canonical_id,version,report_path,report_at,delivered_at)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (delivery_run,row['source'],row['paper_id'],canonical_id,version,
                     report_path,report_at,row['completed_at']))
                counts['delivered'] += 1
                if report_path:
                    counts['delivery_with_report_path'] += 1
            else:
                counts['pending'] += 1
            if analysis:
                counts['analysis'] += 1
            if translated:
                counts['translation'] += 1
            store._sync_paper_entity_for_record(dest, row['source'], row['paper_id'])
            counts['papers'] += 1
        # The old ledger stores only each paper's latest run, not complete
        # per-run membership. Do not fabricate historical run totals.
    source.close()
    with store._connect() as dest:
        actual = dest.execute('SELECT COUNT(*) FROM daily_papers').fetchone()[0]
        pending = dest.execute('SELECT COUNT(*) FROM daily_papers WHERE completed_at IS NULL').fetchone()[0]
        delivery = dest.execute('SELECT COUNT(*) FROM paper_deliveries').fetchone()[0]
        integrity = dest.execute('PRAGMA integrity_check').fetchone()[0]
    print(json.dumps({'source_counts':dict(counts),'target_papers':actual,'target_pending':pending,'target_deliveries':delivery,'integrity':integrity}))
    if integrity != 'ok' or actual != counts['papers'] or pending != counts['pending'] or delivery != len(delivered_identities):
        raise RuntimeError('migration count/integrity mismatch')
    connection = store._connect()
    connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    connection.close()
    store._local.connection = None


def run(source_path, target_path, source_data_root=None, target_data_root=None):
    source_path = source_path.resolve()
    target_path = target_path.resolve()
    if target_path.exists():
        raise RuntimeError('target exists; refusing to overwrite')
    temporary = target_path.with_name('.' + target_path.name + '.migrating-' + uuid.uuid4().hex)
    try:
        _run_into(source_path, temporary, source_data_root, target_data_root)
        # An exclusive hard link keeps the no-overwrite guarantee even if
        # another process creates the target after the initial existence check.
        os.link(temporary, target_path)
    finally:
        # Only paths created by this invocation are eligible for cleanup.
        for path in (temporary, Path(str(temporary) + '-wal'), Path(str(temporary) + '-shm')):
            if path.exists():
                path.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_snapshot', type=Path, help='consistent backup of the old fork database')
    parser.add_argument('new_database', type=Path, help='new path; must not already exist')
    parser.add_argument('--source-data-root', type=Path, help='old data/ directory for report path remapping')
    parser.add_argument('--target-data-root', type=Path, help='new data/ directory for report path remapping')
    args = parser.parse_args()
    if bool(args.source_data_root) != bool(args.target_data_root):
        parser.error('both report data roots must be supplied together')
    run(args.source_snapshot,args.new_database,args.source_data_root,args.target_data_root)
