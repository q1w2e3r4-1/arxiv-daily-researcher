from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from common import (
    EUROSYS_PAPERS_URL,
    ensure_run_dirs,
    get_run_id,
    normalize_title,
    requests_get,
    write_csv,
    write_json,
    write_jsonl,
)

DOI_RE = re.compile(r"10\.1145/[0-9.]+")


class PapersTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_papers_table = False
        self.table_depth = 0
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.current_cell_index = -1
        self.current_text_parts: list[str] = []
        self.current_link = ""
        self.current_row: dict[str, str] | None = None
        self.rows: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = set((attrs_dict.get("class") or "").split())
        if tag == "table" and "papers" in classes:
            self.in_papers_table = True
            self.table_depth = 1
            return
        if not self.in_papers_table:
            return
        if tag == "table":
            self.table_depth += 1
        elif tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_row = True
            self.current_cell_index = -1
            self.current_row = {"title": "", "authors": "", "link": ""}
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.current_cell_index += 1
            self.current_text_parts = []
        elif tag == "br" and self.in_cell:
            self.current_text_parts.append(", ")
        elif tag == "a" and self.in_cell and self.current_cell_index == 0:
            self.current_link = attrs_dict.get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if not self.in_papers_table:
            return
        if tag == "td" and self.in_row and self.in_cell:
            text = clean_text("".join(self.current_text_parts))
            if self.current_row is not None:
                if self.current_cell_index == 0:
                    self.current_row["title"] = text
                    self.current_row["link"] = self.current_link
                elif self.current_cell_index == 1:
                    self.current_row["authors"] = text
            self.in_cell = False
            self.current_text_parts = []
            self.current_link = ""
        elif tag == "tr" and self.in_row:
            if self.current_row and self.current_row.get("title"):
                self.rows.append(self.current_row)
            self.in_row = False
            self.current_row = None
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_papers_table = False
                self.table_depth = 0

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_text_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self.in_cell:
            self.current_text_parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.in_cell:
            self.current_text_parts.append(f"&#{name};")


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text


def parse_listing(html_text: str) -> list[dict[str, Any]]:
    parser = PapersTableParser()
    parser.feed(html_text)
    papers: list[dict[str, Any]] = []
    for idx, row in enumerate(parser.rows, start=1):
        link = row["link"].strip()
        title = row["title"]
        authors = row["authors"]
        doi_match = DOI_RE.search(link)
        doi = doi_match.group(0) if doi_match else ""
        papers.append(
            {
                "paper_id": f"eurosys2026_{idx:03d}",
                "title": title,
                "normalized_title": normalize_title(title),
                "authors": authors,
                "detail_url": urljoin(EUROSYS_PAPERS_URL, link),
                "doi": doi,
                "source_page": EUROSYS_PAPERS_URL,
            }
        )
    return papers


def invert_abstract_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    size = max((max(pos_list) for pos_list in index.values() if pos_list), default=-1) + 1
    if size <= 0:
        return ""
    words = [""] * size
    for word, positions in index.items():
        for pos in positions:
            if 0 <= pos < size:
                words[pos] = word
    return re.sub(r"\s+", " ", " ".join(words)).strip()


def fetch_openalex_record(doi: str) -> dict[str, Any]:
    if not doi:
        return {}
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    resp = requests_get(url)
    resp.raise_for_status()
    return resp.json()


def fetch_semantic_scholar_record(doi: str) -> dict[str, Any]:
    if not doi:
        return {}
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/DOI:"
        f"{doi}?fields=title,abstract,authors,tldr,externalIds,url,venue,year"
    )
    resp = requests_get(url)
    resp.raise_for_status()
    return resp.json()


def enrich_paper(paper: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    openalex = {}
    s2 = {}
    if paper.get("doi"):
        try:
            openalex = fetch_openalex_record(paper["doi"])
        except Exception as exc:
            openalex = {"_error": str(exc)}
        try:
            s2 = fetch_semantic_scholar_record(paper["doi"])
        except Exception as exc:
            s2 = {"_error": str(exc)}

    if paper.get("doi"):
        safe_doi = paper["doi"].replace("/", "_")
        write_json(raw_dir / f"openalex_{safe_doi}.json", openalex)
        write_json(raw_dir / f"s2_{safe_doi}.json", s2)

    openalex_abstract = invert_abstract_index(openalex.get("abstract_inverted_index")) if openalex else ""
    s2_abstract = (s2.get("abstract") or "").strip() if s2 else ""
    abstract = openalex_abstract or s2_abstract

    enriched = dict(paper)
    primary_location = openalex.get("primary_location") or {} if isinstance(openalex, dict) else {}
    primary_source = primary_location.get("source") or {} if isinstance(primary_location, dict) else {}

    enriched.update(
        {
            "abstract": abstract,
            "abstract_source": "openalex" if openalex_abstract else ("semantic_scholar" if s2_abstract else "missing"),
            "abstract_missing": not bool(abstract),
            "openalex_id": openalex.get("id", "") if isinstance(openalex, dict) else "",
            "semantic_scholar_paper_id": s2.get("paperId", "") if isinstance(s2, dict) else "",
            "arxiv_id": (s2.get("externalIds") or {}).get("ArXiv", "") if isinstance(s2, dict) else "",
            "venue": (s2.get("venue") if isinstance(s2, dict) else "") or primary_source.get("display_name", ""),
            "year": (s2.get("year") if isinstance(s2, dict) else None) or (openalex.get("publication_year") if isinstance(openalex, dict) else None),
            "tldr": ((s2.get("tldr") or {}).get("text", "") if isinstance(s2, dict) else ""),
        }
    )
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_id = args.run_id or get_run_id()
    dirs = ensure_run_dirs(run_id)
    run_dir = dirs["run_dir"]
    raw_dir = dirs["raw_dir"]

    resp = requests_get(EUROSYS_PAPERS_URL)
    resp.raise_for_status()
    html_text = resp.text
    raw_html_path = raw_dir / "eurosys_2026_papers.html"
    raw_html_path.write_text(html_text, encoding="utf-8")

    listing_hash = hashlib.sha256(html_text.encode("utf-8")).hexdigest()
    papers = parse_listing(html_text)
    enriched = [enrich_paper(p, raw_dir) for p in papers]

    write_jsonl(run_dir / "papers.jsonl", enriched)
    write_csv(run_dir / "papers.csv", enriched)
    write_json(
        run_dir / "scrape_manifest.json",
        {
            "run_id": run_id,
            "source_url": EUROSYS_PAPERS_URL,
            "paper_count": len(enriched),
            "listing_sha256": listing_hash,
            "missing_abstract_count": sum(1 for p in enriched if p["abstract_missing"]),
            "titles_unique": len({p["normalized_title"] for p in enriched}) == len(enriched),
        },
    )
    print(json.dumps({"run_id": run_id, "paper_count": len(enriched), "path": str(run_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
