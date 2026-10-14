"""Conservative PDF body selection; never silently analyse a fixed prefix."""

import re


BODY_SELECTION_VERSION = "body-v1"

# Match entire section headings, not citations or sentences mentioning them.
_TAIL_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s+)?"
    r"(?P<section>references|bibliography|参考文献|appendix|appendices|附录)"
    r"(?:\s+[A-Z](?::\s*[^\n]{0,100})?)?\s*[:.]?\s*$",
    re.IGNORECASE,
)
_CITATION_START = re.compile(r"(?m)^\s*\[\d{1,4}\]\s+\S")


class PaperInputTooLargeError(ValueError):
    """The main body exceeds the configured conservative input budget."""


def select_paper_body(text: str) -> tuple[str, dict]:
    """Drop a confidently identified reference/appendix tail, keep conclusions.

    Ignore early headings (including short tables of contents). If a heading
    cannot be identified, keep the text. Discussion/limitations are retained
    because PDF extraction cannot reliably delimit them in arbitrary layouts.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    offset = 0
    cutoff = len(normalized)
    removed_section = None
    for line in normalized.splitlines(keepends=True):
        match = _TAIL_HEADING.fullmatch(line.strip())
        reference_evidence = bool(match and match.group("section").lower() in {
            "references", "bibliography", "参考文献"
        } and len(_CITATION_START.findall(normalized[offset + len(line):offset + len(line) + 4000])) >= 2)
        # A very long appendix can make the real reference section occur early
        # as a fraction of total text. Require citation evidence in that case.
        if match and offset >= 500 and (offset >= len(normalized) * 0.35 or reference_evidence):
            cutoff = offset
            removed_section = match.group("section").lower()
            break
        offset += len(line)
    body = normalized[:cutoff].strip()
    return body, {
        "body_selection_version": BODY_SELECTION_VERSION,
        "original_chars": len(text),
        "sent_chars": len(body),
        "removed_tail_section": removed_section,
        "input_scope": "main_body" if removed_section else "parsed_pdf",
    }


def check_input_budget(system_prompt: str, prompt: str, budget: int) -> int:
    """UTF-8 bytes are a conservative token estimate for byte BPE providers.

    This is deliberately more conservative than chars / 4, especially for
    Chinese. It is not a provider context-capacity assertion. The configured
    input budget must leave room for reasoning and output in the actual model.
    """
    estimate = len((system_prompt + prompt).encode("utf-8")) + 64
    if estimate > budget:
        raise PaperInputTooLargeError(
            f"正文与提示词超过输入预算（保守估算 {estimate}，预算 {budget}）；"
            "未发送截断正文，请调整预算或检查 PDF 提取结果"
        )
    return estimate
