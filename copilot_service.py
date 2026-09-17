from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any


def build_regression_prompt(facts: dict[str, Any]) -> str:
    return (
        "You are a senior test-impact analyst. Use only the supplied facts. Select the smallest "
        "risk-aware regression subset from impacted_scenarios that covers every ID listed in "
        "required_coverage_unit_ids. "
        "Prefer a scenario that covers multiple units over scenarios with redundant coverage, but "
        "do not omit unique or high-risk coverage. Never invent or alter scenario IDs, files, tags, "
        "steps, or coverage units. Return JSON only, with this exact shape: "
        '{"selected_scenarios":[{"scenario_id":"exact supplied ID","reason":"brief coverage reason"}],'
        '"excluded_scenarios":[{"scenario_id":"exact supplied ID","reason":"brief redundancy reason"}],'
        '"summary":"brief overall rationale"}. Do not use Markdown fences.\n\n'
        f"Facts:\n{json.dumps(facts, indent=2)}"
    )


def parse_regression_response(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("GitHub Copilot did not return valid JSON.") from exc
        try:
            result = json.loads(text[start:end + 1])
        except json.JSONDecodeError as nested:
            raise RuntimeError("GitHub Copilot did not return valid JSON.") from nested
    if not isinstance(result, dict) or not isinstance(result.get("selected_scenarios"), list):
        raise RuntimeError("GitHub Copilot response is missing selected_scenarios.")
    return result


async def _generate(prompt: str, github_token: str) -> str:
    try:
        from copilot import CopilotClient
        from copilot.session import PermissionHandler
    except ImportError as exc:
        raise RuntimeError(
            "The GitHub Copilot SDK is not installed. Install the packages in requirements.txt."
        ) from exc

    runtime_directory = Path(tempfile.gettempdir()) / "ghcp-impact-copilot-runtime"
    runtime_directory.mkdir(parents=True, exist_ok=True)
    client = CopilotClient(
        mode="empty",
        base_directory=str(runtime_directory),
        github_token=github_token,
        use_logged_in_user=False,
    )
    session = None
    try:
        await client.start()
        session = await client.create_session(
            github_token=github_token,
            available_tools=[],
            on_permission_request=PermissionHandler.approve_all,
        )
        response = await session.send_and_wait(prompt, timeout=180)
        content = getattr(getattr(response, "data", None), "content", None)
        if not content or not content.strip():
            raise RuntimeError("GitHub Copilot returned an empty response.")
        return content.strip()
    finally:
        if session is not None:
            await session.disconnect()
        await client.stop()


def generate_regression_subset(facts: dict[str, Any], github_token: str) -> dict[str, Any]:
    token = github_token.strip()
    if not token:
        raise RuntimeError(
            "COPILOT_GITHUB_TOKEN is not configured in Streamlit Secrets."
        )
    content = asyncio.run(_generate(build_regression_prompt(facts), token))
    return parse_regression_response(content)
