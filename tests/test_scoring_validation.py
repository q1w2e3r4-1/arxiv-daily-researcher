import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.analysis_agent import (  # noqa: E402
    AnalysisAgent,
    ScoreValidationError,
    WeightedScoreResponse,
)
from config import settings  # noqa: E402
from scoring_policy import (  # noqa: E402
    CORE_RELEVANCE_V2,
    MLSYS_SINGLE_MODEL_V1,
    WEIGHTED_KEYWORD_WITH_PENALTIES_V1,
)
from report.daily.modules.base_module import FormatHelper  # noqa: E402
from report.daily.modules.renderers import ScoringRenderer  # noqa: E402


def _score_payload(**overrides):
    payload = {
        "keyword_scores": {"quantum sensing": 8, "noise": 2.5},
        "reasoning": "The paper directly studies quantum sensing under noise.",
        "tldr": "该论文改进了真实噪声条件下的量子传感方案。",
        "extracted_keywords": ["quantum sensing", "noise", "metrology"],
    }
    payload.update(overrides)
    return json.dumps(payload)


class ScoringValidationTests(unittest.TestCase):
    def setUp(self):
        self._default_strategy = patch.object(settings, "SCORE_STRATEGY", CORE_RELEVANCE_V2)
        self._default_strategy.start()
        self.addCleanup(self._default_strategy.stop)

    def _agent_with_response(self, payload):
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent._call_cheap_llm = lambda _prompt, **_kwargs: payload
        return agent

    def test_rejects_missing_extra_and_out_of_range_keyword_scores(self):
        keywords = {"quantum sensing": 1.0, "noise": 0.5}

        cases = [
            _score_payload(keyword_scores={"quantum sensing": 8}),
            _score_payload(keyword_scores={"quantum sensing": 8, "noise": 2, "fake": 10}),
            _score_payload(keyword_scores={"quantum sensing": 11, "noise": 2}),
            _score_payload(keyword_scores={"quantum sensing": float("nan"), "noise": 2}),
        ]
        for payload in cases:
            with self.subTest(payload=payload), patch.object(settings, "MAX_SCORE_PER_KEYWORD", 10):
                with self.assertRaisesRegex(RuntimeError, "论文评分失败"):
                    self._agent_with_response(payload).score_paper_with_keywords(
                        "title", ["Alice"], "abstract", keywords
                    )

    def test_rejects_missing_tldr_instead_of_persisting_a_placeholder(self):
        payload = _score_payload(tldr="")
        with self.assertRaisesRegex(RuntimeError, "tldr 必须是非空字符串"):
            self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice"], "abstract", {"quantum sensing": 1, "noise": 1}
            )

    def test_translates_english_tldr_without_repeating_scoring(self):
        agent = self._agent_with_response(
            _score_payload(tldr="It improves quantum sensing under realistic noise.")
        )
        calls = []

        def translate(tldr):
            calls.append(tldr)
            return "该论文改进了真实噪声条件下的量子传感方案。"

        agent.translate_tldr = translate
        result = agent.score_paper_with_keywords(
            "title", ["Alice"], "abstract", {"quantum sensing": 1, "noise": 1}
        )
        self.assertEqual(result.tldr, "该论文改进了真实噪声条件下的量子传感方案。")
        self.assertEqual(calls, ["It improves quantum sensing under realistic noise."])

    def test_rejects_untranslated_english_tldr(self):
        agent = self._agent_with_response(_score_payload(tldr="English summary."))
        agent._call_cheap_llm_plain = lambda *_args, **_kwargs: "Still English."
        with self.assertRaisesRegex(RuntimeError, "TL;DR 翻译未返回中文"):
            agent.score_paper_with_keywords(
                "title", ["Alice"], "abstract", {"quantum sensing": 1, "noise": 1}
            )

    def test_history_tldr_translation_fallback_returns_chinese(self):
        agent = AnalysisAgent.__new__(AnalysisAgent)
        responses = iter(["The method improves precision.", "该方法提高了精度。"])
        agent._call_cheap_llm_plain = lambda *_args, **_kwargs: next(responses)
        self.assertEqual(agent.generate_tldr("title", "abstract"), "该方法提高了精度。")

    def test_expert_bonus_uses_only_real_configured_authors_once(self):
        payload = _score_payload(
            expert_authors_found=["Imaginary Person", "Alice Smith", "Alice Smith"]
        )
        with patch.object(settings, "MAX_SCORE_PER_KEYWORD", 10), patch.object(
            settings, "ENABLE_AUTHOR_BONUS", True
        ), patch.object(settings, "EXPERT_AUTHORS", ["alice-smith", "Bob Jones"]), patch.object(
            settings, "AUTHOR_BONUS_POINTS", 3.0
        ), patch.object(
            settings, "SCORE_STRATEGY", "legacy_weighted_keyword_v1"
        ):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title",
                ["Alice Smith", "Alice Smith", "Unrelated Author"],
                "abstract",
                {"quantum sensing": 1.0, "noise": 0.5},
            )

        self.assertEqual(result.expert_authors_found, ["Alice Smith"])
        self.assertEqual(result.author_bonus, 3.0)
        self.assertEqual(result.total_score, 12.25)

    def test_expert_bonus_uses_each_authors_configured_points(self):
        payload = _score_payload(expert_authors_found=["Alice Smith", "Bob Jones"])
        with patch.object(settings, "MAX_SCORE_PER_KEYWORD", 10), patch.object(
            settings, "ENABLE_AUTHOR_BONUS", True
        ), patch.object(
            settings, "EXPERT_AUTHORS", ["Alice Smith", "Bob Jones"]
        ), patch.object(
            settings, "AUTHOR_BONUS_POINTS", 3.0
        ), patch.object(
            settings, "AUTHOR_BONUS_BY_AUTHOR", {"Alice Smith": 1.5, "Bob Jones": 4.0}
        ), patch.object(
            settings, "SCORE_STRATEGY", "legacy_weighted_keyword_v1"
        ):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title",
                ["Alice Smith", "Bob Jones"],
                "abstract",
                {"quantum sensing": 1.0, "noise": 0.5},
            )

        self.assertEqual(result.expert_authors_found, ["Alice Smith", "Bob Jones"])
        self.assertEqual(result.author_bonus, 5.5)
        self.assertEqual(result.total_score, 14.75)

    def test_invalid_score_configuration_fails_before_an_llm_call(self):
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent._call_cheap_llm = lambda _prompt, **_kwargs: self.fail("LLM must not be called")
        with patch.object(settings, "MAX_SCORE_PER_KEYWORD", 0):
            with self.assertRaises(ScoreValidationError):
                agent.score_paper_with_keywords("title", ["Alice"], "abstract", {"kw": 1})

    def test_penalty_strategy_subtracts_weighted_relevance_without_lowering_threshold(self):
        payload = _score_payload(
            keyword_scores={
                "quantum sensing": 8,
                "noise": 4,
                "quantum communication": 9,
                "photonic networks": 2,
            },
        )
        with patch.multiple(
            settings,
            SCORE_STRATEGY=WEIGHTED_KEYWORD_WITH_PENALTIES_V1,
            NEGATIVE_KEYWORDS=["quantum communication", "photonic networks"],
            NEGATIVE_KEYWORD_WEIGHTS={
                "quantum communication": 0.5,
                "photonic networks": 0.25,
            },
            ENABLE_AUTHOR_BONUS=False,
            PASSING_SCORE_BASE=5.0,
            PASSING_SCORE_WEIGHT_COEFFICIENT=3.0,
        ):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice"], "abstract",
                {"quantum sensing": 1.0, "noise": 0.5},
            )

        self.assertEqual(result.strategy_id, WEIGHTED_KEYWORD_WITH_PENALTIES_V1)
        self.assertEqual(result.keyword_scores, {"quantum sensing": 8.0, "noise": 4.0})
        self.assertEqual(
            result.negative_keyword_scores,
            {"quantum communication": 9.0, "photonic networks": 2.0},
        )
        self.assertEqual(result.negative_keyword_penalty, 5.0)
        self.assertEqual(result.total_score, 5.0)
        self.assertEqual(result.passing_score, 9.5)
        self.assertFalse(result.is_qualified)
        self.assertIn("扣分 5.0", result.qualification_reason)

    def test_penalty_strategy_requires_every_negative_relevance_score(self):
        with patch.multiple(
            settings,
            SCORE_STRATEGY=WEIGHTED_KEYWORD_WITH_PENALTIES_V1,
            NEGATIVE_KEYWORDS=["quantum communication"],
            NEGATIVE_KEYWORD_WEIGHTS={"quantum communication": 0.5},
        ):
            with self.assertRaisesRegex(RuntimeError, "缺少关键词"):
                self._agent_with_response(_score_payload()).score_paper_with_keywords(
                    "title", ["Alice"], "abstract",
                    {"quantum sensing": 1.0, "noise": 0.5},
                )

    def test_penalty_strategy_rejects_overlap_before_llm_request(self):
        agent = AnalysisAgent.__new__(AnalysisAgent)
        agent._call_cheap_llm = lambda _prompt, **_kwargs: self.fail("LLM must not be called")
        with patch.multiple(
            settings,
            SCORE_STRATEGY=WEIGHTED_KEYWORD_WITH_PENALTIES_V1,
            NEGATIVE_KEYWORDS=["Noise"],
            NEGATIVE_KEYWORD_WEIGHTS={"Noise": 0.5},
        ):
            with self.assertRaisesRegex(ScoreValidationError, "不能同时作为加分关键词"):
                agent.score_paper_with_keywords(
                    "title", ["Alice"], "abstract", {"noise": 0.5}
                )

    def test_penalty_details_are_visible_in_markdown_scoring_module(self):
        renderer = ScoringRenderer(FormatHelper("mkdocs"))
        payload = _score_payload(
            keyword_scores={
                "quantum sensing": 8,
                "noise": 2.5,
                "quantum communication": 9,
            },
        )
        with patch.multiple(
            settings,
            SCORE_STRATEGY=WEIGHTED_KEYWORD_WITH_PENALTIES_V1,
            NEGATIVE_KEYWORDS=["quantum communication"],
            NEGATIVE_KEYWORD_WEIGHTS={"quantum communication": 0.5},
            ENABLE_AUTHOR_BONUS=False,
        ):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice"], "abstract",
                {"quantum sensing": 1.0, "noise": 0.5},
            )
            lines = renderer.render(
                {"score_response": result, "keywords_dict": {"quantum sensing": 1.0, "noise": 0.5}},
                {"format": "list", "show_details": True, "show_reasoning": False},
            )
        self.assertIn("不关注：quantum communication", "\n".join(lines))
        self.assertIn("→ -4.5", "\n".join(lines))

    def test_mlsys_single_model_renderer_uses_its_own_scale(self):
        renderer = ScoringRenderer(FormatHelper("mkdocs"))
        response = SimpleNamespace(
            strategy_id="mlsys_single_model_v1",
            total_score=8.0,
            passing_score=6.0,
            is_qualified=True,
            relevance_score=7.0,
            keyword_scores={"base_score": 7.0, "preference_bonus": 1.0},
            author_bonus=0.0,
            expert_authors_found=[],
            reasoning="Reusable LLM inference infrastructure.",
        )
        lines = renderer.render(
            {"score_response": response, "keywords_dict": {}},
            {"format": "list", "show_details": True, "show_reasoning": True},
        )
        rendered = "\n".join(lines)
        self.assertIn("MLSys 评分", rendered)
        self.assertIn("7.0 + 偏好加分 +1.0 = 8.0 / 6.0", rendered)
        self.assertIn("Reusable LLM inference infrastructure.", rendered)
        self.assertNotIn("base_score**", rendered)

    def test_v2_reference_keywords_cannot_lower_core_qualification(self):
        payload = _score_payload(
            keyword_scores={"core": 5.9, "reference": 10},
        )
        with patch.object(settings, "SCORE_STRATEGY", CORE_RELEVANCE_V2), patch.object(
            settings, "PRIMARY_KEYWORDS", ["core"]
        ), patch.object(settings, "CORE_RELEVANCE_THRESHOLD", 6.0), patch.object(
            settings, "CORE_KEYWORD_MIN_SCORE", 5.0
        ), patch.object(settings, "REFERENCE_RANKING_WEIGHT", 1.0):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice"], "abstract", {"core": 1.0, "reference": 0.01}
            )

        self.assertFalse(result.is_qualified)
        self.assertEqual(result.relevance_score, 5.9)
        self.assertEqual(result.qualification_threshold, 6.0)
        self.assertEqual(result.core_keywords_used, ["core"])

    def test_v2_expert_author_cannot_qualify_zero_core_relevance(self):
        payload = _score_payload(keyword_scores={"core": 0, "reference": 10})
        with patch.object(settings, "SCORE_STRATEGY", CORE_RELEVANCE_V2), patch.object(
            settings, "PRIMARY_KEYWORDS", ["core"]
        ), patch.object(settings, "CORE_RELEVANCE_THRESHOLD", 6.0), patch.object(
            settings, "CORE_KEYWORD_MIN_SCORE", 7.0), patch.object(
            settings, "REFERENCE_RANKING_WEIGHT", 1.0
        ), patch.object(settings, "ENABLE_AUTHOR_BONUS", True), patch.object(
            settings, "EXPERT_AUTHORS", ["Alice Smith"]
        ), patch.object(settings, "AUTHOR_BONUS_POINTS", 50.0):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice Smith"], "abstract", {"core": 1.0, "reference": 1.0}
            )

        self.assertFalse(result.is_qualified)
        self.assertEqual(result.author_bonus, 0.0)
        self.assertEqual(result.author_preference_bonus, 0.0)
        self.assertEqual(result.ranking_score, 10.0)

    def test_v2_strong_primary_match_qualifies_and_author_only_changes_ranking(self):
        payload = _score_payload(keyword_scores={"core": 8, "reference": 2})
        common = dict(
            SCORE_STRATEGY=CORE_RELEVANCE_V2,
            PRIMARY_KEYWORDS=["core"],
            CORE_RELEVANCE_THRESHOLD=6.0,
            CORE_KEYWORD_MIN_SCORE=7.0,
            REFERENCE_RANKING_WEIGHT=0.5,
            ENABLE_AUTHOR_BONUS=True,
            EXPERT_AUTHORS=["Alice Smith"],
            AUTHOR_BONUS_POINTS=3.0,
        )
        with patch.multiple(settings, **common):
            expert = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice Smith"], "abstract", {"core": 1.0, "reference": 1.0}
            )
            nonexpert = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Other Author"], "abstract", {"core": 1.0, "reference": 1.0}
            )

        self.assertTrue(expert.is_qualified)
        self.assertTrue(nonexpert.is_qualified)
        self.assertEqual(expert.relevance_score, nonexpert.relevance_score)
        self.assertEqual(expert.ranking_score, nonexpert.ranking_score + 3.0)

    def test_v2_without_primary_keywords_has_explicit_safe_fallback(self):
        payload = _score_payload(keyword_scores={"reference": 8, "other": 1})
        with patch.object(settings, "SCORE_STRATEGY", CORE_RELEVANCE_V2), patch.object(
            settings, "PRIMARY_KEYWORDS", []
        ), patch.object(settings, "CORE_RELEVANCE_THRESHOLD", 4.0), patch.object(
            settings, "CORE_KEYWORD_MIN_SCORE", 7.0), patch.object(
            settings, "REFERENCE_RANKING_WEIGHT", 0.25):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice"], "abstract", {"reference": 1.0, "other": 1.0}
            )

        self.assertTrue(result.is_qualified)
        self.assertEqual(result.core_keywords_used, ["reference", "other"])
        self.assertIn("未配置主要关键词", result.qualification_reason)

    def test_scoring_renderer_uses_configured_maximum_not_hardcoded_ten(self):
        renderer = ScoringRenderer(FormatHelper("mkdocs"))
        response = type(
            "Score", (),
            {
                "total_score": 4.0,
                "passing_score": 3.0,
                "is_qualified": True,
                "keyword_scores": {"kw": 4.0},
                "author_bonus": 0.0,
                "expert_authors_found": [],
                "reasoning": "test",
            },
        )()
        with patch.object(settings, "MAX_SCORE_PER_KEYWORD", 5):
            lines = renderer.render(
                {"score_response": response, "keywords_dict": {"kw": 1.0}},
                {"format": "list", "show_details": True, "show_reasoning": False},
            )
        self.assertIn("4.0/5", "\n".join(lines))

    def test_mlsys_prompt_strategy_maps_one_valid_response_to_weighted_score(self):
        payload = json.dumps(
            {
                "paper_type": "mlsys",
                "base_score": 8,
                "preference_bonus": 2,
                "final_score": 10,
                "pass": True,
                "reason": "The paper improves reusable LLM inference infrastructure.",
            }
        )
        agent = self._agent_with_response(payload)
        with patch.object(settings, "SCORE_STRATEGY", MLSYS_SINGLE_MODEL_V1), patch.object(
            settings, "MLSYS_SINGLE_MODEL_PASSING_SCORE", 6.0
        ):
            result = agent.score_paper_with_keywords(
                "title", ["Alice"], "abstract", {"unused native keyword": 1.0}
            )

        self.assertEqual(result.strategy_id, MLSYS_SINGLE_MODEL_V1)
        self.assertEqual(result.total_score, 10)
        self.assertEqual(result.keyword_scores, {"base_score": 8, "preference_bonus": 2})
        self.assertTrue(result.is_qualified)
        self.assertEqual(result.passing_score, 6.0)
        self.assertEqual(result.reasoning, result.tldr)

    def test_mlsys_configured_gate_can_differ_from_prompt_recommended_gate(self):
        payload = json.dumps(
            {
                "paper_type": "mlsys", "base_score": 6, "preference_bonus": 0,
                "final_score": 6, "pass": True, "reason": "The paper fits the task.",
            }
        )
        with patch.object(settings, "SCORE_STRATEGY", MLSYS_SINGLE_MODEL_V1), patch.object(
            settings, "MLSYS_SINGLE_MODEL_PASSING_SCORE", 7.0
        ):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice"], "abstract", {"unused": 1.0}
            )
        self.assertTrue(result.model_pass)
        self.assertFalse(result.is_qualified)
        self.assertEqual(result.passing_score, 7.0)

    def test_mlsys_decimal_scores_allow_binary_rounding(self):
        payload = json.dumps({
            "paper_type": "borderline", "base_score": 5.1,
            "preference_bonus": 0.2, "final_score": 5.3,
            "pass": False, "reason": "The systems contribution is limited.",
        })
        with patch.object(settings, "SCORE_STRATEGY", MLSYS_SINGLE_MODEL_V1):
            result = self._agent_with_response(payload).score_paper_with_keywords(
                "title", ["Alice"], "abstract", {}
            )
        self.assertEqual(result.total_score, 5.3)
        self.assertFalse(result.is_qualified)

    def test_mlsys_prompt_strategy_rejects_inconsistent_or_out_of_range_json(self):
        invalid_payloads = [
            {"paper_type": "mlsys", "base_score": 8, "preference_bonus": 2,
             "final_score": 9, "pass": True, "reason": "Reason."},
            {"paper_type": "mlsys", "base_score": 11, "preference_bonus": 0,
             "final_score": 11, "pass": True, "reason": "Reason."},
            {"paper_type": "mlsys", "base_score": 8, "preference_bonus": 2,
             "final_score": 10, "pass": False, "reason": "Reason."},
            {"paper_type": "other", "base_score": 8, "preference_bonus": 2,
             "final_score": 10, "pass": True, "reason": "Reason."},
        ]
        with patch.object(settings, "SCORE_STRATEGY", MLSYS_SINGLE_MODEL_V1):
            for payload in invalid_payloads:
                with self.subTest(payload=payload), self.assertRaisesRegex(
                    RuntimeError, "论文评分失败"
                ):
                    self._agent_with_response(json.dumps(payload)).score_paper_with_keywords(
                        "title", ["Alice"], "abstract", {"unused": 1.0}
                    )

    def test_score_response_preserves_unknown_historical_committee_fields(self):
        response = WeightedScoreResponse(
            total_score=7, keyword_scores={}, author_bonus=0, expert_authors_found=[],
            passing_score=6, is_qualified=True, reasoning="historical", tldr="historical",
            extracted_keywords=[], strategy_id="mlsys_multi_model", committee_votes={"glm": 1},
        )
        hydrated = WeightedScoreResponse.model_validate_json(response.model_dump_json())
        self.assertEqual(hydrated.strategy_id, "mlsys_multi_model")
        self.assertEqual(hydrated.committee_votes, {"glm": 1})
        with patch.object(settings, "SCORE_STRATEGY", "mlsys_multi_model"):
            with self.assertRaisesRegex(ValueError, "SCORE_STRATEGY"):
                settings.normalized_score_strategy()


if __name__ == "__main__":
    unittest.main()
