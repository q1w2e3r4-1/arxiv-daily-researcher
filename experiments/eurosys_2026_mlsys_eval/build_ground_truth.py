from __future__ import annotations

import argparse
import json
import re
from typing import Any

from common import EUROSYS_MD_PATH, DATA_ROOT, normalize_title, read_jsonl, write_csv, write_json, write_jsonl

SECTION_RE = re.compile(r"^##\s+(?P<section>.+)$")
TITLE_RE = re.compile(r"^###\s+\d+\.\s+(?P<title>.+)$")
TRAILING_ALIAS_RE = re.compile(r"\s*\((?P<alias>[^()]*)\)\s*$")
EXCLUDED_SECTION_KEYWORDS = ("ml for systems",)


def extract_positive_titles(md_text: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    positives: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    current_section = ""
    for line in md_text.splitlines():
        stripped = line.strip()
        section_match = SECTION_RE.match(stripped)
        if section_match:
            current_section = section_match.group("section").strip()
            continue
        title_match = TITLE_RE.match(stripped)
        if not title_match:
            continue
        row = {"title": title_match.group("title").strip(), "section": current_section}
        if any(keyword in current_section.lower() for keyword in EXCLUDED_SECTION_KEYWORDS):
            excluded.append(row)
        else:
            positives.append(row)
    return positives, excluded


def build_title_variants(title: str) -> set[str]:
    variants = {normalize_title(title)}
    current = title.strip()
    while True:
        match = TRAILING_ALIAS_RE.search(current)
        if not match:
            break
        alias = match.group("alias").strip()
        if alias:
            variants.add(normalize_title(alias))
        current = current[: match.start()].strip()
        if current:
            variants.add(normalize_title(current))
    if ":" in current:
        prefix, suffix = current.split(":", 1)
        if prefix.strip():
            variants.add(normalize_title(prefix.strip()))
        if suffix.strip():
            variants.add(normalize_title(suffix.strip()))
    return {variant for variant in variants if variant}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    run_dir = DATA_ROOT / args.run_id
    papers = read_jsonl(run_dir / "papers.jsonl")
    md_text = EUROSYS_MD_PATH.read_text(encoding="utf-8")
    positive_entries, excluded_entries = extract_positive_titles(md_text)
    positive_titles = [entry["title"] for entry in positive_entries]
    variant_to_title: dict[str, str] = {}
    canonical_to_variants: dict[str, set[str]] = {}
    for title in positive_titles:
        canonical = normalize_title(title)
        variants = build_title_variants(title)
        canonical_to_variants[canonical] = variants
        for variant in variants:
            variant_to_title.setdefault(variant, title)

    labels: list[dict[str, Any]] = []
    matched_titles: set[str] = set()
    for paper in papers:
        norm = paper["normalized_title"]
        matched_title = variant_to_title.get(norm)
        is_positive = matched_title is not None
        if matched_title:
            matched_titles.add(normalize_title(matched_title))
        labels.append(
            {
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "normalized_title": norm,
                "is_mlsys": is_positive,
                "label_source": "Eurosys.md",
                "label_type": "positive" if is_positive else "negative",
                "notes": f"matched Eurosys.md: {matched_title}" if matched_title else "not listed in Eurosys.md",
            }
        )

    unmatched = [
        {
            "title": title,
            "normalized_title": canonical,
            "variants": sorted(canonical_to_variants.get(canonical, set())),
        }
        for title in positive_titles
        for canonical in [normalize_title(title)]
        if canonical not in matched_titles
    ]

    write_jsonl(run_dir / "labels.jsonl", labels)
    write_csv(run_dir / "labels.csv", labels)
    write_json(
        run_dir / "label_manifest.json",
        {
            "run_id": args.run_id,
            "positive_count": sum(1 for row in labels if row["is_mlsys"]),
            "negative_count": sum(1 for row in labels if not row["is_mlsys"]),
            "effective_positive_count": len(positive_titles),
            "raw_eurosys_md_positive_count": len(positive_titles) + len(excluded_entries),
            "excluded_positive_titles": excluded_entries,
            "unmatched_positive_titles": unmatched,
        },
    )
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "positives": sum(1 for row in labels if row['is_mlsys']),
                "excluded": len(excluded_entries),
                "unmatched": len(unmatched),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
