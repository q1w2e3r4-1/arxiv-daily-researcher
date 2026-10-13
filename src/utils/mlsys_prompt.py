"""Shared validation and built-in defaults for the single-model prompt editor."""
from pathlib import Path
import json5


def validate_prompt_overrides(system: str, user: str) -> None:
    if not isinstance(system, str) or not isinstance(user, str):
        raise ValueError("MLSys prompt fields must be text.")
    if len(system) > 100_000 or len(user) > 100_000:
        raise ValueError("MLSys prompt fields must contain at most 100000 characters.")
    if bool(system.strip()) != bool(user.strip()):
        raise ValueError("Provide both MLSys prompt fields, or leave both empty to use the default.")
    if user.strip() and not all(token in user for token in ("{title}", "{abstract}")):
        raise ValueError("The paper prompt must include {title} and {abstract}.")


def builtin_prompt(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        template = json5.load(stream)
    return {"version": template["version"], **template["prompts"]}
