from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import (
    DATA_ROOT,
    ensure_run_dirs,
    llm_json_call,
    load_models,
    load_prompt_template,
    make_client,
    read_jsonl,
    write_csv,
    write_json,
    write_jsonl,
)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def build_prompts(template: dict[str, Any], paper: dict[str, Any]) -> tuple[str, str]:
    system_prompt = template["prompts"]["system"]
    categories = paper.get("venue", "EuroSys 2026")
    user_prompt = template["prompts"]["user_template"]
    replacements = {
        "{title}": paper["title"],
        "{abstract}": paper.get("abstract", "") or "",
        "{source}": "EuroSys 2026",
        "{categories}": categories,
    }
    for old, new in replacements.items():
        user_prompt = user_prompt.replace(old, str(new))
    return system_prompt, user_prompt


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    tp = sum(1 for r in rows if r["gold"] and r["pred"])
    tn = sum(1 for r in rows if (not r["gold"]) and (not r["pred"]))
    fp = sum(1 for r in rows if (not r["gold"]) and r["pred"])
    fn = sum(1 for r in rows if r["gold"] and (not r["pred"]))
    total = len(rows)
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    pass_rate = sum(1 for r in rows if r["pred"]) / total if total else 0.0
    return {
        "total": total,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy": round(accuracy, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "pass_rate": round(pass_rate, 6),
    }


def parse_model_json(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise json.JSONDecodeError("empty response", raw_text or "", 0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S)
    if fenced:
        return json.loads(fenced.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("no json object found", raw_text or "", 0)


def write_agreement_csv(path: Path, rows: list[dict[str, Any]], models: list[str]) -> None:
    normalized_rows = []
    for row in rows:
        normalized = {
            "paper_id": row.get("paper_id", ""),
            "title": row.get("title", ""),
            "gold": row.get("gold", False),
        }
        for model in models:
            normalized[model] = row.get(model, "")
        normalized_rows.append(normalized)
    write_csv(path, normalized_rows)


def make_fallback_judgment(paper: dict[str, Any], model_name: str, error: str, latency: float, usage: dict[str, int], gold: bool) -> dict[str, Any]:
    return {
        "paper_id": paper["paper_id"],
        "title": paper["title"],
        "abstract": paper.get("abstract", "") or "",
        "model": model_name,
        "paper_type": "fallback_error",
        "base_score": 5,
        "preference_bonus": 0,
        "final_score": 5,
        "pass": False,
        "gold": gold,
        "reason": f"Fallback score after repeated API failure: {error}",
        "latency_seconds": round(latency, 4),
        "fallback_due_to_error": True,
        "fallback_error": error,
        **usage,
    }


def write_model_state(
    model_dir: Path,
    papers: list[dict[str, Any]],
    model_name: str,
    raw_rows: list[dict[str, Any]],
    judgment_rows: list[dict[str, Any]],
    invalid_rows: list[dict[str, Any]],
    eval_rows: list[dict[str, Any]],
    latencies: list[float],
    token_totals: dict[str, int],
) -> dict[str, Any]:
    metrics = compute_metrics(eval_rows)
    metrics.update(
        {
            "model": model_name,
            "requested_papers": len(papers),
            "completed_papers": len(raw_rows),
            "valid_json_rate": round(len(judgment_rows) / len(raw_rows), 6) if raw_rows else 0.0,
            "avg_latency_seconds": round(sum(latencies) / len(latencies), 4) if latencies else 0.0,
            **token_totals,
        }
    )
    write_jsonl(model_dir / "raw_responses.jsonl", raw_rows)
    write_jsonl(model_dir / "judgments.jsonl", judgment_rows)
    write_jsonl(model_dir / "invalid_responses.jsonl", invalid_rows)
    write_json(model_dir / "metrics.json", metrics)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    ensure_run_dirs(args.run_id)
    run_dir = DATA_ROOT / args.run_id
    papers = read_jsonl(run_dir / "papers.jsonl")
    labels = {row["paper_id"]: row for row in read_jsonl(run_dir / "labels.jsonl")}
    template = load_prompt_template()
    models_cfg = load_models()
    models = models_cfg["models"]
    client = make_client()

    if args.limit > 0:
        papers = papers[: args.limit]

    metrics_rows = []
    agreement_rows: dict[str, dict[str, Any]] = {
        paper["paper_id"]: {
            "paper_id": paper["paper_id"],
            "title": paper["title"],
            "gold": labels[paper["paper_id"]]["is_mlsys"],
        }
        for paper in papers
    }

    for model_idx, model_name in enumerate(models, start=1):
        model_dir = run_dir / "model_outputs" / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        raw_rows: list[dict[str, Any]] = []
        judgment_rows: list[dict[str, Any]] = []
        invalid_rows: list[dict[str, Any]] = []
        eval_rows: list[dict[str, Any]] = []
        token_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        latencies: list[float] = []
        print(
            json.dumps(
                {
                    "event": "model_start",
                    "model": model_name,
                    "model_index": model_idx,
                    "model_count": len(models),
                    "papers": len(papers),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        for index, paper in enumerate(papers, start=1):
            system_prompt, user_prompt = build_prompts(template, paper)
            raw_text = ""
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            latency = 0.0
            parsed: dict[str, Any] | None = None
            error = ""
            try:
                raw_text, latency, usage = llm_json_call(client, model_name, system_prompt, user_prompt)
                parsed = parse_model_json(raw_text)
            except Exception as exc:
                error = str(exc)

            for key in token_totals:
                token_totals[key] += int(usage.get(key, 0) or 0)
            latencies.append(latency)

            raw_rows.append(
                {
                    "paper_id": paper["paper_id"],
                    "title": paper["title"],
                    "abstract": paper.get("abstract", "") or "",
                    "model": model_name,
                    "raw_response": raw_text,
                    "latency_seconds": round(latency, 4),
                    **usage,
                    "error": error,
                }
            )

            if parsed is None:
                gold = bool(labels[paper["paper_id"]]["is_mlsys"])
                fallback = make_fallback_judgment(
                    paper,
                    model_name,
                    error or "invalid_json",
                    latency,
                    usage,
                    gold,
                )
                invalid_rows.append(
                    {
                        "paper_id": paper["paper_id"],
                        "title": paper["title"],
                        "abstract": paper.get("abstract", "") or "",
                        "model": model_name,
                        "raw_response": raw_text,
                        "error": error or "invalid_json",
                        "fallback_applied": True,
                        "fallback_final_score": 5,
                    }
                )
                judgment_rows.append(fallback)
                eval_rows.append({"gold": gold, "pred": False})
                agreement_rows[paper["paper_id"]][model_name] = False
                metrics = write_model_state(
                    model_dir,
                    papers,
                    model_name,
                    raw_rows,
                    judgment_rows,
                    invalid_rows,
                    eval_rows,
                    latencies,
                    token_totals,
                )
                print(
                    json.dumps(
                        {
                            "model": model_name,
                            "paper_index": index,
                            "paper_id": paper["paper_id"],
                            "status": "fallback",
                            "error": error or "invalid_json",
                            "fallback_final_score": 5,
                            "valid_json_rate": metrics["valid_json_rate"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                if index % 10 == 0 or index == len(papers):
                    print(
                        json.dumps(
                            {
                                "event": "progress",
                                "model": model_name,
                                "paper_index": index,
                                "papers": len(papers),
                                "completed": len(raw_rows),
                                "fallbacks": len(invalid_rows),
                                "valid_json_rate": metrics["valid_json_rate"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                continue

            base_score = safe_int(parsed.get("base_score"), 0)
            preference_bonus = safe_int(parsed.get("preference_bonus"), 0)
            final_score = base_score + preference_bonus
            pred = final_score >= 6
            gold = bool(labels[paper["paper_id"]]["is_mlsys"])
            row = {
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "abstract": paper.get("abstract", "") or "",
                "model": model_name,
                "paper_type": parsed.get("paper_type", ""),
                "base_score": base_score,
                "preference_bonus": preference_bonus,
                "final_score": final_score,
                "pass": pred,
                "gold": gold,
                "reason": parsed.get("reason", ""),
                "latency_seconds": round(latency, 4),
                **usage,
            }
            judgment_rows.append(row)
            eval_rows.append({"gold": gold, "pred": pred})
            agreement_rows[paper["paper_id"]][model_name] = pred
            metrics = write_model_state(
                model_dir,
                papers,
                model_name,
                raw_rows,
                judgment_rows,
                invalid_rows,
                eval_rows,
                latencies,
                token_totals,
            )
            print(
                json.dumps(
                    {
                        "model": model_name,
                        "paper_index": index,
                        "paper_id": paper["paper_id"],
                        "status": "ok",
                        "final_score": final_score,
                        "pass": pred,
                        "valid_json_rate": metrics["valid_json_rate"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if index % 10 == 0 or index == len(papers):
                print(
                    json.dumps(
                        {
                            "event": "progress",
                            "model": model_name,
                            "paper_index": index,
                            "papers": len(papers),
                            "completed": len(raw_rows),
                            "fallbacks": len(invalid_rows),
                            "valid_json_rate": metrics["valid_json_rate"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

        final_metrics = write_model_state(
            model_dir,
            papers,
            model_name,
            raw_rows,
            judgment_rows,
            invalid_rows,
            eval_rows,
            latencies,
            token_totals,
        )
        metrics_rows.append(final_metrics)
        print(
            json.dumps(
                {
                    "event": "model_done",
                    "model": model_name,
                    "model_index": model_idx,
                    "model_count": len(models),
                    "completed": len(raw_rows),
                    "fallbacks": len(invalid_rows),
                    "accuracy": final_metrics["accuracy"],
                    "valid_json_rate": final_metrics["valid_json_rate"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    write_csv(run_dir / "metrics.csv", metrics_rows)
    write_json(run_dir / "metrics.json", metrics_rows)

    agreement_list = list(agreement_rows.values())
    write_agreement_csv(run_dir / "model_agreement.csv", agreement_list, models)
    write_json(run_dir / "model_agreement.json", agreement_list)
    print(json.dumps({"run_id": args.run_id, "models": len(models), "papers": len(papers)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
