"""Frozen offline evaluations must not silently use a WebUI prompt override."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("rescreen_contract", Path(__file__).resolve().parents[1] / "scripts/rescreen_selected.py")
rescreen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rescreen)


class PromptRescreenContractTests(unittest.TestCase):
    def test_accepts_builtin_prompt_and_rejects_a_runtime_override(self):
        template = json.loads(rescreen.PROMPT.read_bytes())
        settings = SimpleNamespace(load_report_template=lambda _: template)
        rescreen.ensure_frozen_prompt(settings)
        changed = {**template, "prompts": {**template["prompts"], "system": "different policy"}}
        settings.load_report_template = lambda _: changed
        with self.assertRaisesRegex(RuntimeError, "冻结"):
            rescreen.ensure_frozen_prompt(settings)
