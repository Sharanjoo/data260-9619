from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from code.agents_demo import finalize_payload, run_pipeline  # noqa: E402
from code.hw1_client import is_bullet_only, serialized_history_length, snapshot_stats  # noqa: E402
from scripts.run_nondeterminism import percentile, summarize  # noqa: E402
from src.model_client import ModelResponse, OllamaModelClient  # noqa: E402


class StaticDeliverableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (PROJECT_ROOT / "code/web_application/index.html").read_text(encoding="utf-8")
        cls.javascript = (PROJECT_ROOT / "code/web_application/app.js").read_text(encoding="utf-8")
        cls.schema = (PROJECT_ROOT / "DOMAIN_SCHEMA.md").read_text(encoding="utf-8")

    def test_configuration_math_and_domain(self) -> None:
        sid4 = 9619
        self.assertEqual(8000 + sid4 % 900, 8619)
        self.assertEqual(sid4 % 8, 3)
        for expected in ("9619", "8619", "s9619", "269619", "DOMAIN_ID` | 3"):
            self.assertIn(expected, self.schema)

    def test_required_html_fields(self) -> None:
        self.assertIn("<title>HW1-Sharan Lourduraj</title>", self.html)
        self.assertRegex(self.html, r"<h1>\s*Grocery Supply and Recall Notices\s*</h1>")
        for field_id in (
            "productName",
            "brandName",
            "submitterEmail",
            "description",
            "category",
            "termsAccepted",
        ):
            self.assertIn(f'id="{field_id}"', self.html)
        self.assertIn("autofocus", self.html)
        self.assertIn("I agree to the terms and conditions.", self.html)
        self.assertIn('<script src="app.js"></script>', self.html)

    def test_four_domain_categories(self) -> None:
        select = re.search(r'<select id="category".*?</select>', self.html, flags=re.DOTALL)
        self.assertIsNotNone(select)
        values = re.findall(r'<option value="([^"]+)"', select.group(0))
        self.assertEqual(
            values,
            ["food-safety-recall", "allergen-alert", "quality-withdrawal", "supply-shortage"],
        )

    def test_custom_alerts_run_before_native_validation(self) -> None:
        description_check = self.javascript.index("descriptionInput.value.trim().length <= 25")
        terms_check = self.javascript.index("!termsInput.checked")
        native_check = self.javascript.index("!form.checkValidity()")
        self.assertLess(description_check, native_check)
        self.assertLess(terms_check, native_check)
        self.assertIn("JSON.stringify", self.javascript)
        self.assertIn("JSON.parse", self.javascript)
        self.assertIn("submissionDate", self.javascript)
        self.assertIn("submissionCounter", self.javascript)

    def test_fixed_experiment_input(self) -> None:
        path = PROJECT_ROOT / "reports/hw01/cases/nondeterminism_input.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(data["title"].strip())
        self.assertGreater(len(data["content"].split()), 25)


class FakeClient:
    model = "fake-model"

    def __init__(self, contents: list[str]) -> None:
        self.contents = iter(contents)

    def complete(self, messages, tools=None, **kwargs) -> ModelResponse:  # noqa: ANN001
        content = next(self.contents)
        return ModelResponse(
            content=content,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            model=self.model,
            total_duration_ns=100,
            raw={},
        )


class AgentPipelineTests(unittest.TestCase):
    def test_finalizer_enforces_shape(self) -> None:
        result = finalize_payload(
            {"tags": ["Allergen Alert", "allergen alert", "Cookies"], "summary": " ".join(["x"] * 40)},
            "Cookie recall",
            "Cookies contain an undeclared peanut allergen and should be returned.",
        )
        self.assertEqual(len(result["tags"]), 3)
        self.assertEqual(len(set(result["tags"])), 3)
        self.assertLessEqual(len(result["summary"].split()), 25)

    def test_pipeline_uses_planner_then_reviewer(self) -> None:
        client = FakeClient(
            [
                json.dumps(
                    {
                        "tags": ["undeclared peanuts", "cookie recall", "customer refunds"],
                        "summary": "Cookies are recalled for undeclared peanuts and may be returned for a refund.",
                    }
                ),
                json.dumps(
                    {
                        "tags": ["undeclared peanut", "chocolate cookies", "product refund"],
                        "summary": "Chocolate cookies are recalled for undeclared peanuts and customers may return them for a refund.",
                        "changed": True,
                        "explanation": "Made the tags more specific.",
                    }
                ),
            ]
        )
        result = run_pipeline(client, "Cookie recall", "Cookies contain undeclared peanuts.", 0.0)
        self.assertEqual(len(result["final"]["tags"]), 3)
        self.assertTrue(result["transcript"]["reviewer"]["changed"])
        self.assertEqual(result["model"], "fake-model")


class AccountingAndMetricsTests(unittest.TestCase):
    def test_bullet_only_check(self) -> None:
        self.assertTrue(is_bullet_only("- One issue.\n- Another issue."))
        self.assertFalse(is_bullet_only("Heading\n- One issue."))

    def test_stats_does_not_change_history(self) -> None:
        client = OllamaModelClient()
        history = [{"role": "system", "content": "- Return bullets."}]
        before = json.dumps(history)
        stats = snapshot_stats(client, history)
        self.assertEqual(json.dumps(history), before)
        self.assertEqual(stats["turn_count"], 0)
        self.assertEqual(stats["serialized_history_length"], serialized_history_length(history))

    def test_percentile_and_summary(self) -> None:
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        rows = [
            {"temperature": 0.7, "tags": ["a", "b", f"c{i}"], "latency_ms": i}
            for i in range(1, 21)
        ]
        result = summarize(rows, 0.7)
        self.assertEqual(result["runs"], 20)
        self.assertEqual(result["distinct_tag_sets"], 20)
        self.assertEqual(result["tags_in_all_runs"], ["a", "b"])
        self.assertEqual(len(result["tags_in_exactly_one_run"]), 20)

    def test_model_adapter_rejects_invalid_messages(self) -> None:
        with self.assertRaises(ValueError):
            OllamaModelClient._validate_messages([])
        with self.assertRaises(ValueError):
            OllamaModelClient._validate_messages([{"role": "invalid", "content": "x"}])


if __name__ == "__main__":
    unittest.main()
