"""Render a frozen single-model screening snapshot with the normal HTML layout.

This only writes the requested artifact. Publishing it into a WebUI report
directory is a separate operation so the snapshot can be checked first.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.analysis_agent import WeightedScoreResponse  # noqa: E402
from config import settings  # noqa: E402
from report.daily.reporter import Reporter  # noqa: E402
from scoring_policy import MLSYS_SINGLE_MODEL_V1  # noqa: E402

PROMPT = ROOT / "configs/templates/reports/mlsys_screening_prompt.json"


def export(snapshot_db: Path, translations_json: Path, output: Path) -> None:
    if settings.normalized_score_strategy() != MLSYS_SINGLE_MODEL_V1:
        raise RuntimeError("当前配置不是 MLSys 单模型评分策略")
    with sqlite3.connect(f"file:{snapshot_db.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        experiment = conn.execute("SELECT * FROM experiment WHERE id=1").fetchone()
        if experiment is None:
            raise RuntimeError("缺少冻结样本元数据")
        if hashlib.sha256(PROMPT.read_bytes()).hexdigest() != experiment["prompt_sha256"]:
            raise RuntimeError("当前 prompt 与冻结样本版本不一致")
        rows = conn.execute("""
            SELECT paper_id, metadata_json, old_score_json, new_score_json, status
            FROM papers ORDER BY paper_id
        """).fetchall()
    if not rows or any(row["status"] != "succeeded" for row in rows):
        raise RuntimeError("冻结样本尚未全部评分成功")

    translations = json.loads(translations_json.read_text(encoding="utf-8"))
    papers = []
    for row in rows:
        metadata = json.loads(row["metadata_json"])
        score = WeightedScoreResponse.model_validate(json.loads(row["new_score_json"]))
        authors = metadata.get("authors") or []
        papers.append({
            "paper_id": row["paper_id"],
            "title": metadata["title"],
            "url": metadata.get("url") or metadata.get("arxiv_url") or "",
            "authors": ", ".join(authors) if isinstance(authors, list) else str(authors),
            "published": str(metadata.get("published_date") or "")[:10],
            "abstract": metadata.get("abstract") or "",
            "abstract_cn": translations.get(row["paper_id"], ""),
            "semantic_scholar_tldr": metadata.get("semantic_scholar_tldr") or "",
            "score_response": score,
        })

    qualified = sum(paper["score_response"].is_qualified for paper in papers)
    reporter = Reporter()
    reporter._generate_html_report(
        filepath=output,
        source="arxiv",
        display_name="ArXiv 14 天效率筛选预览",
        papers=papers,
        keywords_dict={},
        analyses=[],
        has_deep_analysis=False,
        all_paper_count=len(papers),
        qualified_count=qualified,
        qualified_only=False,
        generated_at=datetime.now().astimezone(),
    )
    content = output.read_text(encoding="utf-8")
    banner = (
        '<p class="meta">独立实验快照：仅复评旧 prompt 已入选的 '
        f'{len(papers)} 篇；新 prompt v{html.escape(experiment["prompt_version"])}；'
        f'模型 {html.escape(experiment["model"])}。'
        '此报告包含入选和剔除卡片，不代表全量抓取论文的新版召回率，'
        '也不是日常任务的一次运行。</p>'
    )
    marker = "</h1>"
    if content.count(marker) != 1:
        raise RuntimeError("报告标题结构异常")
    reporter._write_text_atomic(output, content.replace(marker, marker + "\n" + banner, 1))
    print(f"报告：{output}；复评 {len(papers)} 篇；入选 {qualified}；剔除 {len(papers)-qualified}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-db", type=Path, required=True)
    parser.add_argument("--translations-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.snapshot_db, args.translations_json, args.output)


if __name__ == "__main__":
    main()
