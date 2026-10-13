# EuroSys 2026 MLSys Evaluation

This historical experiment scrapes the full EuroSys 2026 accepted paper list, builds a frozen ground-truth label set from [Eurosys.md](Eurosys.md), evaluates four OpenAI-compatible chat models with the earlier MLSys screening prompt, and writes reproducible artifacts to `data/experiments/eurosys_2026_mlsys_eval/<run_id>/`. The current daily screening runtime uses one `deepseek-reasoner` model and a narrower prompt; the saved metrics are not a direct comparison with that runtime.

## Models
The default model list is stored in `models.json`:
- glm-5.1
- minimax-m2.7
- qwen3.5-27b
- deepseek-v3.2

## Required environment variables
Do not hardcode secrets in files. For the main project runtime, prefer storing them in the repo-root `.env` file (gitignored and also consumed by `docker-compose`).

For this experiment or one-off scripts, you can also export them before running:

```bash
export SJTU_API_BASE_URL="https://models.sjtu.edu.cn/api/v1"
export SJTU_API_KEY="<your-key>"
```

The four-model list above describes only this archived benchmark. Do not use it as the daily runtime configuration.

Optional:

```bash
export EUROSYS_USER_AGENT="ArxivDailyResearcher/exp (mailto:you@example.com)"
export EUROSYS_RUN_ID="manual-test"
```

## Run
From the repo root:

```bash
python experiments/eurosys_2026_mlsys_eval/run_all.py
```

Or step by step:

```bash
python experiments/eurosys_2026_mlsys_eval/fetch_eurosys.py
python experiments/eurosys_2026_mlsys_eval/build_ground_truth.py --run-id <run_id>
python experiments/eurosys_2026_mlsys_eval/run_eval.py --run-id <run_id>
python experiments/eurosys_2026_mlsys_eval/report_eval.py --run-id <run_id>
```

## Outputs
Per run:
- `raw/` — raw HTML snapshots and API payloads
- `papers.jsonl`, `papers.csv` — normalized scraped paper table
- `labels.jsonl`, `labels.csv` — frozen labels derived from `Eurosys.md`
- `model_outputs/<model>/raw_responses.jsonl`
- `model_outputs/<model>/judgments.jsonl`
- `model_outputs/<model>/invalid_responses.jsonl`
- `metrics.json`, `metrics.csv`
- `summary.md`, `summary.html`

The final summary is also copied into:
- `data/reports/daily_research/markdown/eurosys_2026_eval/`
- `data/reports/daily_research/html/eurosys_2026_eval/`

So it can be opened from the existing WebUI report viewer.
