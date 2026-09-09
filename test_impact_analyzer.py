import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

from unittest.mock import patch

from impact_analyzer import (
    ChangedFile, Impact, Scenario, StepDefinition, _github_api, cucumber_pattern,
    discover_scenarios, impacted_definitions, minimal_subset, parse_github_pull_location,
    parse_azure_pull_request_url, parse_pull_request_url,
)


class ImpactAnalyzerTests(unittest.TestCase):
    def test_github_api_uses_curl_when_python_socket_is_blocked(self):
        blocked = URLError(PermissionError(10013, "Socket access forbidden"))
        curl_result = SimpleNamespace(returncode=0, stdout='{"number": 12}', stderr="")
        with patch("impact_analyzer.urlopen", side_effect=blocked), patch(
            "impact_analyzer.subprocess.run", return_value=curl_result
        ) as run:
            self.assertEqual(_github_api("/repos/example/project/pulls/12")["number"], 12)
            self.assertEqual(run.call_args.args[0][0], "curl.exe")

    def test_cucumber_string_and_int_expressions(self):
        self.assertTrue(cucumber_pattern("I search for {string}").fullmatch('I search for "Laptop"'))
        self.assertTrue(cucumber_pattern("I enter {string} and {string}").fullmatch('I enter "user" and "password"'))
        self.assertTrue(cucumber_pattern("I have {int} items").fullmatch("I have 12 items"))
        self.assertFalse(cucumber_pattern("I have {int} items").fullmatch("I have many items"))

    def test_parses_scenario_local_tags(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            feature = repo / "src/test/resources/cart.feature"
            feature.parent.mkdir(parents=True)
            feature.write_text("""@feature_tag
Feature: Cart
  @smoke @cart
  Scenario: Add
    Given I have 1 items
""", encoding="utf-8")
            scenarios = discover_scenarios(repo)
            self.assertEqual(scenarios[0].tags, ["@smoke", "@cart"])

    def test_minimal_subset_covers_all_units(self):
        first = Impact(Scenario("a.feature", "Broad", 1), [], [], [], {"A", "B"})
        second = Impact(Scenario("a.feature", "Narrow", 5), [], [], [], {"A"})
        third = Impact(Scenario("b.feature", "Other", 1), [], [], [], {"C"})
        selected, uncovered = minimal_subset([first, second, third])
        self.assertEqual([item.scenario.name for item in selected], ["Broad", "Other"])
        self.assertFalse(uncovered)

    def test_changed_page_object_impacts_referencing_step(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            step_file = repo / "src/test/java/LoginSteps.java"
            step_file.parent.mkdir(parents=True)
            step_file.write_text("class LoginSteps { LoginPage loginPage; }", encoding="utf-8")
            definition = StepDefinition(
                "src/test/java/LoginSteps.java", "I sign in", 1, 1,
                '@When("I sign in") void signIn() { loginPage.signIn(); }',
            )
            with patch("impact_analyzer.changed_line_numbers", return_value={1}):
                links = impacted_definitions(
                    repo, [ChangedFile("M", "src/main/java/LoginPage.java", True)],
                    [definition], "base", "HEAD", True,
                )
            self.assertIn(definition, links)
            self.assertIn("src/main/java/LoginPage.java", links[definition])

    def test_changed_base_page_impacts_steps_using_child_page(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            base = repo / "src/main/java/pages/BasePage.java"
            child = repo / "src/main/java/pages/LoginPage.java"
            step_file = repo / "src/test/java/LoginSteps.java"
            base.parent.mkdir(parents=True)
            step_file.parent.mkdir(parents=True)
            base.write_text("class BasePage {}", encoding="utf-8")
            child.write_text("class LoginPage extends BasePage {}", encoding="utf-8")
            step_file.write_text("class LoginSteps { LoginPage loginPage; }", encoding="utf-8")
            definition = StepDefinition(
                "src/test/java/LoginSteps.java", "I sign in", 1, 1,
                '@When("I sign in") void signIn() { loginPage.signIn(); }',
            )
            with patch("impact_analyzer.changed_line_numbers", return_value={1}):
                links = impacted_definitions(
                    repo, [ChangedFile("M", "src/main/java/pages/BasePage.java", True)],
                    [definition], "base", "HEAD", False,
                )
            self.assertIn("src/main/java/pages/BasePage.java", links[definition])
            self.assertIn("inherits changed class BasePage", links[definition]["src/main/java/pages/BasePage.java"])

    def test_parses_github_pull_request_url(self):
        self.assertEqual(
            parse_pull_request_url("https://github.com/kailashmishra-hub/GHCP/pull/1"),
            ("kailashmishra-hub", "GHCP", 1),
        )
        self.assertIsNone(parse_pull_request_url("https://github.com/kailashmishra-hub/GHCP/pulls"))
        self.assertEqual(
            parse_github_pull_location("https://github.com/kailashmishra-hub/GHCP/pulls"),
            ("kailashmishra-hub", "GHCP", None),
        )

    def test_parses_azure_pull_request_url(self):
        self.assertEqual(
            parse_azure_pull_request_url(
                "https://dev.azure.com/example-org/Automation/_git/UI-Tests/pullrequest/42"
            ),
            ("example-org", "Automation", "UI-Tests", 42),
        )
        self.assertEqual(
            parse_azure_pull_request_url(
                "https://example-org.visualstudio.com/Automation/_git/UI-Tests/pullrequest/42"
            ),
            ("example-org", "Automation", "UI-Tests", 42),
        )
        self.assertIsNone(parse_azure_pull_request_url("https://dev.azure.com/example-org/Automation"))

if __name__ == "__main__":
    unittest.main()
