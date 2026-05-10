from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import DATA_ROOT, copy_summary_to_report_dirs, read_jsonl, write_csv


def render_markdown(run_id: str, metrics: list[dict[str, Any]], labels_manifest: dict[str, Any], papers_manifest: dict[str, Any], per_model_details: dict[str, dict[str, list[dict[str, Any]]]]) -> str:
    lines = []
    lines.append(f"# EuroSys 2026 MLSys Evaluation ({run_id})")
    lines.append("")
    lines.append(f"- Scraped papers: {papers_manifest.get('paper_count', 0)}")
    lines.append(f"- Evaluated papers: {metrics[0].get('requested_papers', metrics[0].get('total', 0)) if metrics else 0}")
    lines.append(f"- Missing abstracts: {papers_manifest.get('missing_abstract_count', 0)}")
    lines.append(f"- Positives from Eurosys.md (effective): {labels_manifest.get('positive_count', 0)}")
    lines.append(f"- Excluded ML-for-Systems titles: {len(labels_manifest.get('excluded_positive_titles', []))}")
    lines.append(f"- Raw Eurosys.md positives: {labels_manifest.get('raw_eurosys_md_positive_count', labels_manifest.get('positive_count', 0))}")
    lines.append(f"- Unmatched Eurosys.md titles: {len(labels_manifest.get('unmatched_positive_titles', []))}")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Model | Acc | Prec | Recall | F1 | Pass rate | Valid JSON | Avg latency |")
    lines.append("|------|-----|------|--------|----|-----------|------------|-------------|")
    for row in metrics:
        lines.append(
            f"| {row['model']} | {row['accuracy']:.3f} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} | {row['pass_rate']:.3f} | {row['valid_json_rate']:.3f} | {row['avg_latency_seconds']:.2f}s |"
        )
    lines.append("")
    for model_name, details in per_model_details.items():
        fps = details['false_positives']
        fns = details['false_negatives']
        fallbacks = details['fallbacks']
        lines.append(f"## {model_name}")
        lines.append("")
        lines.append(f"- False positives: {len(fps)}")
        lines.append(f"- False negatives: {len(fns)}")
        lines.append(f"- Fallback score=5 due to repeated API failures: {len(fallbacks)}")
        lines.append("")
        if fps:
            lines.append("### False positives")
            for row in fps[:15]:
                lines.append(f"- {row['title']} (score={row['final_score']})")
            lines.append("")
        if fns:
            lines.append("### False negatives")
            for row in fns[:15]:
                lines.append(f"- {row['title']} (score={row['final_score']})")
            lines.append("")
        if fallbacks:
            lines.append("### Fallback score=5 due to repeated API failures")
            for row in fallbacks[:15]:
                lines.append(f"- {row['title']} ({row.get('fallback_error', row.get('reason', 'unknown error'))})")
            lines.append("")
    return "\n".join(lines) + "\n"


def markdown_to_html(md: str) -> str:
    html_lines = ["<html><head><meta charset='utf-8'><title>EuroSys 2026 MLSys Evaluation</title>", "<style>body{font-family:Arial,Helvetica,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;line-height:1.6}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px}th{background:#f5f5f5}code{background:#f3f3f3;padding:2px 4px}</style></head><body>"]
    in_table = False
    for line in md.splitlines():
        if line.startswith("# "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("| ") and line.endswith(" |"):
            cells = [c.strip() for c in line.strip('|').split('|')]
            if not in_table:
                html_lines.append("<table>")
                in_table = True
            if all(set(cell) <= {'-'} for cell in cells):
                continue
            tag = 'th' if 'Model' in line else 'td'
            html_lines.append('<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in cells) + '</tr>')
        elif line.startswith("- "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<p>{line}</p>")
        elif line.strip() == "":
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append("<br/>")
        else:
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<p>{line}</p>")
    if in_table:
        html_lines.append("</table>")
    html_lines.append("</body></html>")
    return '\n'.join(html_lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    run_dir = DATA_ROOT / args.run_id
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    labels_manifest = json.loads((run_dir / "label_manifest.json").read_text(encoding="utf-8"))
    papers_manifest = json.loads((run_dir / "scrape_manifest.json").read_text(encoding="utf-8"))

    per_model_details: dict[str, dict[str, list[dict[str, Any]]]] = {}
    fp_rows = []
    fn_rows = []
    for metric in metrics:
        model = metric["model"]
        judgments = read_jsonl(run_dir / "model_outputs" / model / "judgments.jsonl")
        fps = [row for row in judgments if row["pass"] and not row["gold"]]
        fns = [row for row in judgments if (not row["pass"]) and row["gold"]]
        fallbacks = [row for row in judgments if row.get("fallback_due_to_error")]
        per_model_details[model] = {"false_positives": fps, "false_negatives": fns, "fallbacks": fallbacks}
        for row in fps:
            fp_rows.append({"model": model, **row})
        for row in fns:
            fn_rows.append({"model": model, **row})

    write_csv(run_dir / "false_positives.csv", fp_rows)
    write_csv(run_dir / "false_negatives.csv", fn_rows)

    md = render_markdown(args.run_id, metrics, labels_manifest, papers_manifest, per_model_details)
    html = markdown_to_html(md)

    md_path = run_dir / "summary.md"
    html_path = run_dir / "summary.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    report_md, report_html = copy_summary_to_report_dirs(args.run_id, md_path, html_path)
    print(json.dumps({"run_id": args.run_id, "summary_md": str(md_path), "summary_html": str(html_path), "report_md": str(report_md), "report_html": str(report_html)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
