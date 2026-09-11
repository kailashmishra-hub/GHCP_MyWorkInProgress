import unittest

from copilot_service import build_regression_prompt, generate_regression_subset


class CopilotServiceTests(unittest.TestCase):
    def test_prompt_contains_supplied_facts_and_anti_invention_rule(self):
        prompt = build_regression_prompt({"impacted_scenarios": [{"Scenario": "Login"}]})
        self.assertIn('"Scenario": "Login"', prompt)
        self.assertIn("Never invent", prompt)

    def test_missing_token_fails_before_starting_sdk(self):
        with self.assertRaisesRegex(RuntimeError, "COPILOT_GITHUB_TOKEN"):
            generate_regression_subset({}, "")


if __name__ == "__main__":
    unittest.main()
