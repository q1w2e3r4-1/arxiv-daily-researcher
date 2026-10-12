from __future__ import annotations

import csv
import html
import json
import os
import random
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
EXP_ROOT = REPO_ROOT / "experiments" / "eurosys_2026_mlsys_eval"
DATA_ROOT = REPO_ROOT / "data" / "experiments" / "eurosys_2026_mlsys_eval"
REPORT_MD_DIR = REPO_ROOT / "data" / "reports" / "daily_research" / "markdown" / "eurosys_2026_eval"
REPORT_HTML_DIR = REPO_ROOT / "data" / "reports" / "daily_research" / "html" / "eurosys_2026_eval"
PROMPT_PATH = REPO_ROOT / "configs" / "templates" / "reports" / "mlsys_screening_prompt.json"
EUROSYS_MD_PATH = REPO_ROOT / "Eurosys.md"
MODELS_PATH = EXP_ROOT / "models.json"
EUROSYS_PAPERS_URL = "https://2026.eurosys.org/papers.html"


def get_run_id() -> str:
    env_id = os.getenv("EUROSYS_RUN_ID", "").strip()
    if env_id:
        return env_id
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def ensure_run_dirs(run_id: str) -> dict[str, Path]:
    run_dir = DATA_ROOT / run_id
    raw_dir = run_dir / "raw"
    model_outputs = run_dir / "model_outputs"
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    model_outputs.mkdir(parents=True, exist_ok=True)
    REPORT_MD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_HTML_DIR.mkdir(parents=True, exist_ok=True)
    return {"run_dir": run_dir, "raw_dir": raw_dir, "model_outputs": model_outputs}


def load_prompt_template() -> dict[str, Any]:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_models() -> dict[str, Any]:
    with open(MODELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_title(title: str) -> str:
    text = html.unescape(title or "")
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[“”‘’'\"`´]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            pass
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_user_agent() -> str:
    return os.getenv("EUROSYS_USER_AGENT", "ArxivDailyResearcher/exp (mailto:test@example.com)")


def requests_get(url: str, **kwargs: Any) -> requests.Response:
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("User-Agent", get_user_agent())
    return requests.get(url, headers=headers, timeout=kwargs.pop("timeout", 60), **kwargs)


def llm_json_call(client: requests.Session, model_name: str, system_prompt: str, user_prompt: str) -> tuple[str, float, dict[str, int]]:
    last_error: Exception | None = None
    for attempt in range(3):
        started = time.perf_counter()
        try:
            resp = client.post(
                "/chat/completions",
                json={
                    "model": model_name,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=180,
            )
            resp.raise_for_status()
            payload = resp.json()
            elapsed = time.perf_counter() - started
            usage_payload = payload.get("usage") or {}
            usage = {
                "prompt_tokens": int(usage_payload.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage_payload.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage_payload.get("total_tokens", 0) or 0),
            }
            content = payload["choices"][0]["message"]["content"]
            return content or "", elapsed, usage
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(min(8, (2**attempt) + random.random()))
    raise RuntimeError(str(last_error) if last_error else "unknown llm call error")


def make_client() -> requests.Session:
    models_cfg = load_models()
    base_url = os.getenv(models_cfg.get("base_url_env", "SJTU_API_BASE_URL"), "").strip().rstrip("/")
    api_key = os.getenv(models_cfg.get("api_key_env", "SJTU_API_KEY"), "").strip()
    if not base_url or not api_key:
        raise RuntimeError("Missing SJTU_API_BASE_URL or SJTU_API_KEY in environment")
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": get_user_agent(),
        }
    )
    original_post = session.post

    def _post(path: str, *args: Any, **kwargs: Any):
        url = path if path.startswith("http") else f"{base_url}{path}"
        return original_post(url, *args, **kwargs)

    session.post = _post  # type: ignore[method-assign]
    return session


def copy_summary_to_report_dirs(run_id: str, md_path: Path, html_path: Path) -> tuple[Path, Path]:
    md_target = REPORT_MD_DIR / f"EUROSYS_2026_EVAL_Report_{run_id}.md"
    html_target = REPORT_HTML_DIR / f"EUROSYS_2026_EVAL_Report_{run_id}.html"
    shutil.copyfile(md_path, md_target)
    shutil.copyfile(html_path, html_target)
    return md_target, html_target
