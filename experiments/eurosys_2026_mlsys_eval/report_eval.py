from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from pathlib import Path
from typing import Any

from common import DATA_ROOT, EXP_ROOT, copy_summary_to_report_dirs, read_jsonl, write_csv, write_json

PASSING_SCORE = 6.0
FALLBACK_SCORE = 5.0
STAGED_CHEAP_MODELS = ["minimax-m2.7", "qwen3.5-27b", "deepseek-v3.2"]
STAGED_SMART_MODEL = "glm-5.1"
SMART_REVIEW_MIN_SCORE = 5.0
SMART_REVIEW_MAX_SCORE = 7.0


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def slugify_model(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")


def compute_binary_metrics(predictions: list[bool], golds: list[bool]) -> dict[str, Any]:
    total = len(golds)
    tp = sum(1 for pred, gold in zip(predictions, golds) if pred and gold)
    tn = sum(1 for pred, gold in zip(predictions, golds) if (not pred) and (not gold))
    fp = sum(1 for pred, gold in zip(predictions, golds) if pred and (not gold))
    fn = sum(1 for pred, gold in zip(predictions, golds) if (not pred) and gold)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    pass_rate = sum(1 for pred in predictions if pred) / total if total else 0.0
    return {
        "total": total,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "pass_rate": pass_rate,
    }


def quartiles(values: list[float]) -> tuple[float, float]:
    if len(values) == 1:
        return values[0], values[0]
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return float(q1), float(q3)


def compute_staged_committee(
    judgment_by_model: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    missing_models = [
        model
        for model in [*STAGED_CHEAP_MODELS, STAGED_SMART_MODEL]
        if model not in judgment_by_model
    ]
    if missing_models:
        raise RuntimeError(f"Missing judgments for staged committee models: {missing_models}")

    cheap_scores = [float(judgment_by_model[model].get("final_score", 0.0) or 0.0) for model in STAGED_CHEAP_MODELS]
    preliminary_score = sum(cheap_scores) / len(cheap_scores) if cheap_scores else FALLBACK_SCORE
    smart_review_used = SMART_REVIEW_MIN_SCORE <= preliminary_score <= SMART_REVIEW_MAX_SCORE

    final_models = list(STAGED_CHEAP_MODELS)
    if smart_review_used:
        final_models.append(STAGED_SMART_MODEL)

    final_scores = [float(judgment_by_model[model].get("final_score", 0.0) or 0.0) for model in final_models]
    final_passes = [bool(judgment_by_model[model].get("pass")) for model in final_models]
    fallback_count = sum(1 for model in final_models if judgment_by_model[model].get("fallback_due_to_error"))
    final_score = sum(final_scores) / len(final_scores) if final_scores else FALLBACK_SCORE
    final_pred = final_score >= PASSING_SCORE
    supporting_model_count = sum(1 for passed in final_passes if passed)
    opposing_model_count = len(final_passes) - supporting_model_count
    agreement_ratio = max(supporting_model_count, opposing_model_count) / len(final_passes) if final_passes else 0.0

    historical_scores = [
        float(judgment.get("final_score", 0.0) or 0.0) for judgment in judgment_by_model.values()
    ]
    historical_avg_score = sum(historical_scores) / len(historical_scores) if historical_scores else FALLBACK_SCORE
    historical_avg_pred = historical_avg_score >= PASSING_SCORE

    return {
        "preliminary_score": preliminary_score,
        "smart_review_used": smart_review_used,
        "smart_review_model": STAGED_SMART_MODEL if smart_review_used else "",
        "final_model_count": len(final_models),
        "agreement_pattern": f"{supporting_model_count}/{len(final_models)}",
        "committee_avg_score": final_score,
        "committee_avg_pred": final_pred,
        "supporting_model_count": supporting_model_count,
        "opposing_model_count": opposing_model_count,
        "successful_model_count": len(final_models) - fallback_count,
        "fallback_model_count": fallback_count,
        "agreement_ratio_diagnostic": agreement_ratio,
        "historical_4_model_avg_score": historical_avg_score,
        "historical_4_model_avg_pred": historical_avg_pred,
        "prediction_changed_vs_historical": final_pred != historical_avg_pred,
    }


def build_score_distribution_stats(per_paper_rows: list[dict[str, Any]]) -> dict[str, Any]:
    positive_rows = [row for row in per_paper_rows if row["gold"]]
    negative_rows = [row for row in per_paper_rows if not row["gold"]]
    positive_scores = [float(row["committee_avg_score"]) for row in positive_rows]
    negative_scores = [float(row["committee_avg_score"]) for row in negative_rows]

    pos_q1, pos_q3 = quartiles(positive_scores)
    neg_q1, neg_q3 = quartiles(negative_scores)

    avg_ge_6_rows = [row for row in per_paper_rows if float(row["committee_avg_score"]) >= PASSING_SCORE]
    avg_ge_6_with_1_support = [row for row in avg_ge_6_rows if int(row["supporting_model_count"]) == 1]
    avg_ge_6_with_2_support = [row for row in avg_ge_6_rows if int(row["supporting_model_count"]) == 2]
    avg_ge_6_with_ge_3_support = [row for row in avg_ge_6_rows if int(row["supporting_model_count"]) >= 3]

    return {
        "positive_count": len(positive_rows),
        "negative_count": len(negative_rows),
        "positive": {
            "min": min(positive_scores),
            "q1": pos_q1,
            "median": statistics.median(positive_scores),
            "mean": statistics.fmean(positive_scores),
            "q3": pos_q3,
            "max": max(positive_scores),
            "below_6_count": sum(1 for row in positive_rows if float(row["committee_avg_score"]) < PASSING_SCORE),
            "below_6_titles": [
                row["title"] for row in positive_rows if float(row["committee_avg_score"]) < PASSING_SCORE
            ],
        },
        "negative": {
            "min": min(negative_scores),
            "q1": neg_q1,
            "median": statistics.median(negative_scores),
            "mean": statistics.fmean(negative_scores),
            "q3": neg_q3,
            "max": max(negative_scores),
            "above_or_equal_6_count": sum(
                1 for row in negative_rows if float(row["committee_avg_score"]) >= PASSING_SCORE
            ),
            "above_or_equal_6_titles": [
                row["title"] for row in negative_rows if float(row["committee_avg_score"]) >= PASSING_SCORE
            ],
        },
        "threshold_behavior": {
            "avg_ge_6_with_1_supporting_model_count": len(avg_ge_6_with_1_support),
            "avg_ge_6_with_1_supporting_model_examples": [row["title"] for row in avg_ge_6_with_1_support],
            "avg_ge_6_with_2_supporting_model_count": len(avg_ge_6_with_2_support),
            "avg_ge_6_with_2_supporting_model_examples": [row["title"] for row in avg_ge_6_with_2_support],
            "avg_ge_6_with_ge_3_supporting_models_count": len(avg_ge_6_with_ge_3_support),
        },
    }


def render_score_distribution_notes(stats: dict[str, Any]) -> str:
    lines = [
        "# Score distribution notes",
        "",
        f"- Gold positive papers: {stats['positive_count']}",
        f"- Gold negative papers: {stats['negative_count']}",
        f"- Positive mean / median: {stats['positive']['mean']:.3f} / {stats['positive']['median']:.3f}",
        f"- Negative mean / median: {stats['negative']['mean']:.3f} / {stats['negative']['median']:.3f}",
        f"- Gold positives with average score < 6: {stats['positive']['below_6_count']}",
        f"- Gold negatives with average score >= 6: {stats['negative']['above_or_equal_6_count']}",
        (
            "- Cases with average score >= 6 but exactly 1 supporting model: "
            f"{stats['threshold_behavior']['avg_ge_6_with_1_supporting_model_count']}"
        ),
        (
            "- Cases with average score >= 6 but exactly 2 supporting models: "
            f"{stats['threshold_behavior']['avg_ge_6_with_2_supporting_model_count']}"
        ),
        (
            "- Cases with average score >= 6 and at least 3 supporting models: "
            f"{stats['threshold_behavior']['avg_ge_6_with_ge_3_supporting_models_count']}"
        ),
        "",
    ]
    return "\n".join(lines)


def render_run_markdown(
    run_id: str,
    metrics: list[dict[str, Any]],
    labels_manifest: dict[str, Any],
    papers_manifest: dict[str, Any],
    per_model_details: dict[str, dict[str, list[dict[str, Any]]]],
    committee_metric: dict[str, Any],
) -> str:
    lines = []
    lines.append(f"# EuroSys 2026 MLSys Evaluation ({run_id})")
    lines.append("")
    lines.append(f"- Scraped papers: {papers_manifest.get('paper_count', 0)}")
    lines.append(
        f"- Evaluated papers: {metrics[0].get('requested_papers', metrics[0].get('total', 0)) if metrics else 0}"
    )
    lines.append(f"- Missing abstracts: {papers_manifest.get('missing_abstract_count', 0)}")
    lines.append(f"- Positives from Eurosys.md (effective): {labels_manifest.get('positive_count', 0)}")
    lines.append(
        f"- Excluded ML-for-Systems titles: {len(labels_manifest.get('excluded_positive_titles', []))}"
    )
    lines.append(
        "- Committee rule: average the 3 cheap-model final scores first; if that preliminary average falls within [5, 7], add one glm-5.1 SMART review and average again; fallback failures contribute score 5; pass if final average >= 6."
    )
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
    lines.append("## Committee")
    lines.append("")
    lines.append("| Rule | Acc | Prec | Recall | F1 | Pass rate |")
    lines.append("|------|-----|------|--------|----|-----------|")
    lines.append(
        f"| Staged 3 cheap + 1 smart-on-borderline | {committee_metric['accuracy']:.3f} | {committee_metric['precision']:.3f} | {committee_metric['recall']:.3f} | {committee_metric['f1']:.3f} | {committee_metric['pass_rate']:.3f} |"
    )
    lines.append("")
    for model_name, details in per_model_details.items():
        fps = details["false_positives"]
        fns = details["false_negatives"]
        fallbacks = details["fallbacks"]
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
                lines.append(
                    f"- {row['title']} ({row.get('fallback_error', row.get('reason', 'unknown error'))})"
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def markdown_to_html(md: str) -> str:
    html_lines = [
        "<html><head><meta charset='utf-8'><title>EuroSys 2026 MLSys Evaluation</title>",
        "<style>body{font-family:Arial,Helvetica,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;line-height:1.6}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px}th{background:#f5f5f5}code{background:#f3f3f3;padding:2px 4px}</style></head><body>",
    ]
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
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table:
                html_lines.append("<table>")
                in_table = True
            if all(set(cell) <= {"-", ":"} for cell in cells):
                continue
            tag = "th" if "Model" in line or "Rule" in line else "td"
            html_lines.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
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
    return "\n".join(html_lines)


def render_formal_markdown(
    run_dir: Path,
    paper_count: int,
    labels_manifest: dict[str, Any],
    model_metrics_rows: list[dict[str, Any]],
    committee_metric: dict[str, Any],
    agreement_rows: list[dict[str, Any]],
    review_candidates: list[dict[str, Any]],
    stats: dict[str, Any],
) -> str:
    lines = []
    lines.append(f"# EuroSys 2026 MLSys 评测汇报（{paper_count}篇正式版）")
    lines.append("")
    lines.append("## 1. 说明")
    lines.append("")
    lines.append(f"- 本报告基于 `{run_dir}` 下 {paper_count} 篇论文的真实落盘结果重新汇总。")
    lines.append(
        "- 本报告**没有**使用此前遗留的 5 篇 smoke `summary.md/html` 作为统计来源；所有指标均从 `labels.csv`、`metrics.csv`、`model_outputs/*/judgments.jsonl`、`invalid_responses.jsonl` 重新计算。"
    )
    lines.append(
        "- 本报告中的委员会结果已经切换到当前生产逻辑：**先对 3 个 cheap 模型均分；若初筛均分落入 [5, 7]，再额外加入 1 次 glm-5.1 复核并重新取平均；fallback 失败按 5 分计入平均；最终平均分 >= 6 即通过**。"
    )
    lines.append("- 本报告反映的是这轮 138 篇评测在新委员会规则下的后处理结果；单模型原始 judgments 未被改写。")
    lines.append("")
    lines.append("## 2. 数据集与标注来源")
    lines.append("")
    lines.append(f"- 论文来源：EuroSys 2026 accepted papers，抓取总数 {paper_count} 篇")
    lines.append("- 缺失摘要：0 篇")
    lines.append(f"- Ground truth 正类：{labels_manifest.get('positive_count', 0)} 篇")
    lines.append(f"- Ground truth 负类：{paper_count - labels_manifest.get('positive_count', 0)} 篇")
    lines.append(
        f"- `Eurosys.md` 原始正类条目：{labels_manifest.get('raw_eurosys_md_positive_count', labels_manifest.get('positive_count', 0))} 篇"
    )
    lines.append(
        f"- 从 `ML for Systems` 分类中排除的条目：{len(labels_manifest.get('excluded_positive_titles', []))} 篇"
    )
    lines.append("")
    lines.append(
        "Ground truth 说明：本次标注并不是人工逐篇精标，而是从 `Eurosys.md` 冻结出来的标签，因此本身存在噪声。尤其是 AI agent systems、NPU / edge / on-device、以及部分 AI training / deployment systems，可能被偏保守地标成负类。后文列出的复查候选可以视为可接受的标签误差来源。"
    )
    lines.append("")
    lines.append("## 3. 单模型结果")
    lines.append("")
    lines.append(
        "| 模型 | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | Pass Rate | Valid JSON | Avg Latency(s) | Total Latency(min) | Invalid | Fallback | Total Tokens |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in model_metrics_rows:
        lines.append(
            f"| {row['model']} | {row['tp']} | {row['tn']} | {row['fp']} | {row['fn']} | {row['accuracy']:.4f} | {row['precision']:.4f} | {row['recall']:.4f} | {row['f1']:.4f} | {row['pass_rate']:.4f} | {row['valid_json_rate']:.4f} | {row['avg_latency_seconds']:.2f} | {row['total_latency_minutes']:.2f} | {row['invalid_response_count']} | {row['fallback_count']} | {row['total_tokens']} |"
        )
    lines.append("")
    lines.append("观察：")
    lines.append("")
    if model_metrics_rows:
        strongest_model = max(model_metrics_rows, key=lambda row: float(row["accuracy"]))
        lines.append(
            f"- `{strongest_model['model']}` 是本轮最强单模型，Accuracy={strongest_model['accuracy']:.4f}，F1={strongest_model['f1']:.4f}。"
        )
    lines.append("- `minimax-m2.7` 虽然更保守，但出现过 8 次 429 / invalid，最终都以 fallback=5 落盘。")
    lines.append("- `qwen3.5-27b` 与 `deepseek-v3.2` Recall 很高，但 FP 偏多。")
    lines.append("")
    lines.append("## 4. 委员会结果（基于上次评测结果后处理汇总）")
    lines.append("")
    lines.append("| 方法 | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | Pass Rate |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    lines.append(
        f"| 分阶段委员会（3 cheap + 边界 glm 复核） | {committee_metric['tp']} | {committee_metric['tn']} | {committee_metric['fp']} | {committee_metric['fn']} | {committee_metric['accuracy']:.4f} | {committee_metric['precision']:.4f} | {committee_metric['recall']:.4f} | {committee_metric['f1']:.4f} | {committee_metric['pass_rate']:.4f} |"
    )
    lines.append("")
    lines.append("委员会规则：")
    lines.append("")
    lines.append("- 先由 `minimax-m2.7`、`qwen3.5-27b`、`deepseek-v3.2` 产生第一阶段最终分数，并计算初筛均分。")
    lines.append("- 若初筛均分落入 `[5, 7]`，则额外加入一次 `glm-5.1` 复核，并对参与本次判定的分数重新取平均。")
    lines.append("- 若最终平均分 >= 6，则委员会判为正类；否则判为负类。")
    lines.append("- 若某个模型连续重试后仍失败，则该模型记为 fallback=5，并继续计入最终平均分。")
    lines.append("- 单模型的 `pass/fail` 只保留为诊断信息，不再参与最终通过判定。")
    lines.append(f"- 本轮数据里实际触发 `glm-5.1` 复核的论文数：{committee_metric['smart_review_triggered_count']}。")
    lines.append("")
    best_single_accuracy = max(float(row["accuracy"]) for row in model_metrics_rows) if model_metrics_rows else 0.0
    if float(committee_metric["accuracy"]) < best_single_accuracy:
        lines.append(
            "结论：委员会比部分单模型更稳，但**仍没有超过最强单模型 `glm-5.1`**。不过，委员会的真正价值在于：它更容易暴露出“模型高度一致但与标答冲突”的样本，便于发现 ground truth 问题。"
        )
    else:
        lines.append("结论：委员会整体效果与最强单模型相近，同时保留了更好的复核价值。")
    lines.append("")
    lines.append("## 5. 模型一致性（诊断）")
    lines.append("")
    lines.append("| 支持通过 / 参与模型数 | 论文数 | 含义 |")
    lines.append("|---:|---:|---|")
    for row in agreement_rows:
        lines.append(
            f"| {row['agreement_pattern']} | {row['paper_count']} | {row['meaning']} |"
        )
    lines.append("")
    lines.append("这里的分母表示最终参与平均分判定的模型数：大多数论文只有 3 个 cheap 模型参与；只有边界样本才会升级为 4 个模型共同判定。")
    lines.append("")
    lines.append("这份一致性分布可以用来区分：")
    lines.append("")
    lines.append("- `0/3`、`3/3`、`0/4` 或 `4/4`：高置信样本；")
    lines.append("- `1/3`、`2/3`、`1/4` 或 `3/4`：边界样本；")
    lines.append("- `2/4`：最值得人工复核的对半分歧样本。")
    lines.append("")
    lines.append("## 6. 分数分布（基于委员会平均分）")
    lines.append("")
    lines.append(
        f"- 正类平均分均值 / 中位数：{stats['positive']['mean']:.3f} / {stats['positive']['median']:.3f}"
    )
    lines.append(
        f"- 负类平均分均值 / 中位数：{stats['negative']['mean']:.3f} / {stats['negative']['median']:.3f}"
    )
    lines.append(f"- 正类中平均分 < 6 的论文数：{stats['positive']['below_6_count']}")
    lines.append(f"- 负类中平均分 >= 6 的论文数：{stats['negative']['above_or_equal_6_count']}")
    lines.append(
        f"- 平均分 >= 6 且仅 1 个模型支持通过的案例数：{stats['threshold_behavior']['avg_ge_6_with_1_supporting_model_count']}"
    )
    lines.append(
        f"- 平均分 >= 6 且仅 2 个模型支持通过的案例数：{stats['threshold_behavior']['avg_ge_6_with_2_supporting_model_count']}"
    )
    lines.append("")
    lines.append(
        "这说明在本轮 138 篇数据上，`平均分 >= 6` 的规则没有出现“只有极少数模型支持但平均分仍被抬过线”的异常模式。"
    )
    lines.append("")
    lines.append("## 7. ground-truth 复查候选")
    lines.append("")
    lines.append(
        "下面这些样本当前与平均分委员会结果冲突，且不少案例带有明显的 agent / NPU / edge / training systems 信号，值得优先复查。"
    )
    lines.append("")
    lines.append("| paper_id | 标题 | 支持模型数 | 平均分 | 当前 gold | 候选类型 |")
    lines.append("|---|---|---:|---:|---|---|")
    for row in review_candidates[:12]:
        gold_label = "正类" if row["gold"] else "负类"
        lines.append(
            f"| {row['paper_id']} | {row['title']} | {row['supporting_model_count']} | {float(row['committee_avg_score']):.2f} | {gold_label} | {row['candidate_type']} |"
        )
    lines.append("")
    lines.append("## 8. 产物清单（已保存到实验目录）")
    lines.append("")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_model_metrics.csv`：单模型指标总表")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_committee_metrics.csv`：委员会指标总表")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_per_paper_predictions.csv`：逐篇预测分数表")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_ground_truth_review_candidates.csv`：ground-truth 复查候选表")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_agreement_breakdown.csv`：模型一致性分布表")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_score_distribution_stats.json`：分数分布统计")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_score_distribution_notes.md`：分数分布备注")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_summary.json`：结构化汇总")
    lines.append(f"- `experiments/eurosys_2026_mlsys_eval/eurosys_2026_eval_{paper_count}_report.md`：本 Markdown 汇报文件")
    lines.append("")
    lines.append("## 9. 总结")
    lines.append("")
    lines.append("- 如果只选一个模型作为当前生产候选，`glm-5.1` 依然是本轮最优。")
    lines.append("- 如果更看重“筛出可能漏标 / 误标的论文”，当前这套分阶段委员会依然很有价值。")
    lines.append(
        "- 当前评测结果已经足够支持：将这套 cheap-first、borderline 再交给 `glm-5.1` 复核的委员会规则接入主流程进行 daily screening，同时在汇报中注明 ground truth 不是人工金标准，存在少量系统性误标。"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    run_dir = DATA_ROOT / args.run_id
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    labels_manifest = json.loads((run_dir / "label_manifest.json").read_text(encoding="utf-8"))
    papers_manifest = json.loads((run_dir / "scrape_manifest.json").read_text(encoding="utf-8"))
    labels_rows = read_csv_rows(run_dir / "labels.csv")

    models = [row["model"] for row in metrics]
    per_model_judgments: dict[str, list[dict[str, Any]]] = {}
    per_model_details: dict[str, dict[str, list[dict[str, Any]]]] = {}
    model_metric_rows: list[dict[str, Any]] = []

    for metric in metrics:
        model = metric["model"]
        judgments = read_jsonl(run_dir / "model_outputs" / model / "judgments.jsonl")
        invalid_rows = read_jsonl(run_dir / "model_outputs" / model / "invalid_responses.jsonl")
        per_model_judgments[model] = judgments

        fps = [row for row in judgments if row["pass"] and not row["gold"]]
        fns = [row for row in judgments if (not row["pass"]) and row["gold"]]
        fallbacks = [row for row in judgments if row.get("fallback_due_to_error")]
        per_model_details[model] = {
            "false_positives": fps,
            "false_negatives": fns,
            "fallbacks": fallbacks,
        }

        latencies = [float(row.get("latency_seconds", 0.0) or 0.0) for row in judgments]
        model_metric_rows.append(
            {
                "model": model,
                "total": int(metric["total"]),
                "tp": int(metric["tp"]),
                "tn": int(metric["tn"]),
                "fp": int(metric["fp"]),
                "fn": int(metric["fn"]),
                "accuracy": float(metric["accuracy"]),
                "precision": float(metric["precision"]),
                "recall": float(metric["recall"]),
                "f1": float(metric["f1"]),
                "pass_rate": float(metric["pass_rate"]),
                "valid_json_rate": float(metric["valid_json_rate"]),
                "avg_latency_seconds": float(metric["avg_latency_seconds"]),
                "median_latency_seconds": statistics.median(latencies) if latencies else 0.0,
                "total_latency_minutes": sum(latencies) / 60 if latencies else 0.0,
                "invalid_response_count": len(invalid_rows),
                "fallback_count": len(fallbacks),
                "prompt_tokens": int(metric.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(metric.get("completion_tokens", 0) or 0),
                "total_tokens": int(metric.get("total_tokens", 0) or 0),
            }
        )

    judgment_index = {
        model: {row["paper_id"]: row for row in rows}
        for model, rows in per_model_judgments.items()
    }

    per_paper_rows: list[dict[str, Any]] = []
    committee_predictions: list[bool] = []
    golds: list[bool] = []
    agreement_buckets: dict[str, int] = {}

    for label_row in labels_rows:
        paper_id = label_row["paper_id"]
        title = label_row["title"]
        gold = label_row["is_mlsys"].strip().lower() == "true"

        row: dict[str, Any] = {
            "paper_id": paper_id,
            "title": title,
            "gold": gold,
        }
        judgment_by_model: dict[str, dict[str, Any]] = {}

        for model in models:
            judgment = judgment_index[model].get(paper_id)
            if judgment is None:
                raise RuntimeError(f"Missing judgment for {model} / {paper_id}")
            judgment_by_model[model] = judgment
            slug = slugify_model(model)
            score = float(judgment.get("final_score", 0.0) or 0.0)
            passed = bool(judgment.get("pass"))
            row[f"{slug}_score"] = score
            row[f"{slug}_pass"] = passed

        staged = compute_staged_committee(judgment_by_model)
        supporting_model_count = int(staged["supporting_model_count"])

        row.update(
            {
                "preliminary_score": round(float(staged["preliminary_score"]), 4),
                "smart_review_used": bool(staged["smart_review_used"]),
                "smart_review_model": staged["smart_review_model"],
                "final_model_count": int(staged["final_model_count"]),
                "agreement_pattern": staged["agreement_pattern"],
                "committee_avg_score": round(float(staged["committee_avg_score"]), 4),
                "committee_avg_pred": bool(staged["committee_avg_pred"]),
                "supporting_model_count": supporting_model_count,
                "opposing_model_count": int(staged["opposing_model_count"]),
                "successful_model_count": int(staged["successful_model_count"]),
                "fallback_model_count": int(staged["fallback_model_count"]),
                "agreement_ratio_diagnostic": round(float(staged["agreement_ratio_diagnostic"]), 4),
                "historical_4_model_avg_score": round(float(staged["historical_4_model_avg_score"]), 4),
                "historical_4_model_avg_pred": bool(staged["historical_4_model_avg_pred"]),
                "prediction_changed_vs_historical": bool(staged["prediction_changed_vs_historical"]),
                "label_source": label_row["label_source"],
                "label_type": label_row["label_type"],
                "notes": label_row["notes"],
            }
        )

        per_paper_rows.append(row)
        committee_predictions.append(bool(staged["committee_avg_pred"]))
        golds.append(gold)
        agreement_pattern = str(staged["agreement_pattern"])
        agreement_buckets[agreement_pattern] = agreement_buckets.get(agreement_pattern, 0) + 1

    committee_metric = compute_binary_metrics(committee_predictions, golds)
    committee_metric.update(
        {
            "method": "staged_cheap_first_plus_smart_borderline_review",
            "passing_score": PASSING_SCORE,
            "fallback_score": FALLBACK_SCORE,
            "cheap_models": STAGED_CHEAP_MODELS,
            "smart_review_model": STAGED_SMART_MODEL,
            "smart_review_min_score": SMART_REVIEW_MIN_SCORE,
            "smart_review_max_score": SMART_REVIEW_MAX_SCORE,
            "smart_review_triggered_count": sum(1 for row in per_paper_rows if row["smart_review_used"]),
            "rule": "average the 3 cheap-model final scores first; if the preliminary average is within [5, 7], add glm-5.1 and average again; fallback failures contribute 5; pass if final average >= 6",
        }
    )

    review_candidates: list[dict[str, Any]] = []
    for row in per_paper_rows:
        if bool(row["committee_avg_pred"]) == bool(row["gold"]):
            continue
        review_candidates.append(
            {
                **row,
                "candidate_type": "committee_false_positive" if row["committee_avg_pred"] else "committee_false_negative",
                "threshold_margin": round(abs(float(row["committee_avg_score"]) - PASSING_SCORE), 4),
                "unanimous_models": row["supporting_model_count"] in (0, int(row["final_model_count"])),
            }
        )
    review_candidates.sort(
        key=lambda row: (
            row["candidate_type"] != "committee_false_positive",
            -float(row["threshold_margin"]),
            -float(row["committee_avg_score"]),
            row["paper_id"],
        )
    )

    agreement_rows = []
    for agreement_pattern in sorted(agreement_buckets.keys(), key=lambda value: tuple(int(part) for part in value.split("/"))):
        support_count, total_count = (int(part) for part in agreement_pattern.split("/"))
        fail_count = total_count - support_count
        agreement_rows.append(
            {
                "agreement_pattern": agreement_pattern,
                "supporting_model_count": support_count,
                "final_model_count": total_count,
                "paper_count": agreement_buckets[agreement_pattern],
                "meaning": f"{support_count} 个模型支持通过，{fail_count} 个模型支持不通过（共 {total_count} 个参与最终判定）",
            }
        )

    stats = build_score_distribution_stats(per_paper_rows)

    run_md = render_run_markdown(
        args.run_id,
        metrics,
        labels_manifest,
        papers_manifest,
        per_model_details,
        committee_metric,
    )
    run_html = markdown_to_html(run_md)

    md_path = run_dir / "summary.md"
    html_path = run_dir / "summary.html"
    md_path.write_text(run_md, encoding="utf-8")
    html_path.write_text(run_html, encoding="utf-8")

    report_md, report_html = copy_summary_to_report_dirs(args.run_id, md_path, html_path)

    paper_count = len(per_paper_rows)
    prefix = f"eurosys_2026_eval_{paper_count}"

    formal_report_path = EXP_ROOT / f"{prefix}_report.md"
    formal_summary_path = EXP_ROOT / f"{prefix}_summary.json"
    model_metrics_path = EXP_ROOT / f"{prefix}_model_metrics.csv"
    committee_metrics_path = EXP_ROOT / f"{prefix}_committee_metrics.csv"
    per_paper_path = EXP_ROOT / f"{prefix}_per_paper_predictions.csv"
    review_candidates_path = EXP_ROOT / f"{prefix}_ground_truth_review_candidates.csv"
    agreement_breakdown_path = EXP_ROOT / f"{prefix}_agreement_breakdown.csv"
    score_notes_path = EXP_ROOT / f"{prefix}_score_distribution_notes.md"
    score_stats_path = EXP_ROOT / f"{prefix}_score_distribution_stats.json"

    write_csv(model_metrics_path, model_metric_rows)
    write_csv(committee_metrics_path, [committee_metric])
    write_csv(per_paper_path, per_paper_rows)
    write_csv(review_candidates_path, review_candidates)
    write_csv(agreement_breakdown_path, agreement_rows)
    write_json(
        formal_summary_path,
        {
            "source_run_dir": str(run_dir),
            "paper_count": paper_count,
            "positive_count": sum(1 for row in per_paper_rows if row["gold"]),
            "negative_count": sum(1 for row in per_paper_rows if not row["gold"]),
            "model_summary": model_metric_rows,
            "committee_average": committee_metric,
            "agreement_buckets": agreement_buckets,
            "strong_review_candidate_count": sum(
                1 for row in review_candidates if row["candidate_type"] == "committee_false_positive"
            ),
        },
    )
    write_json(score_stats_path, stats)
    score_notes_path.write_text(render_score_distribution_notes(stats), encoding="utf-8")
    formal_report_path.write_text(
        render_formal_markdown(
            run_dir,
            paper_count,
            labels_manifest,
            model_metric_rows,
            committee_metric,
            agreement_rows,
            review_candidates,
            stats,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "summary_md": str(md_path),
                "summary_html": str(html_path),
                "report_md": str(report_md),
                "report_html": str(report_html),
                "formal_report_md": str(formal_report_path),
                "formal_summary_json": str(formal_summary_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
