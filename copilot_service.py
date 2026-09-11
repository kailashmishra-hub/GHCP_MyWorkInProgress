from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any


def build_regression_prompt(facts: dict[str, Any]) -> str:
    return (
        "You are a senior test-impact analyst. Use only the supplied facts. The application has "
        "already computed mandatory_minimal_subset using deterministic set-cover over the traced "
        "changed-method and step-definition coverage units. Do not select, replace, add, or omit "
        "scenarios. Briefly explain why that exact subset covers the supplied impacts and identify "
        "any residual risk represented by uncovered_coverage_units. Never invent files, tags, "
        "steps, scenarios, or project conventions. Return two concise sentences and no table.\n\n"
        f"Facts:\n{json.dumps(facts, indent=2)}"
    )


async def _generate(prompt: str, github_token: str) -> str:
    try:
        from copilot import CopilotClient
        from copilot.session import PermissionHandler
    except ImportError as exc:
        raise RuntimeError(
            "The GitHub Copilot SDK is not installed. Install the packages in requirements.txt."
        ) from exc

    # Empty mode prevents a hosted session from receiving filesystem or shell tools.
    # Recent SDK versions require its runtime storage to be explicitly isolated.
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
            # This is a pure text-generation request. Explicitly grant no tools.
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


def generate_regression_subset(facts: dict[str, Any], github_token: str) -> str:
    token = github_token.strip()
    if not token:
        raise RuntimeError(
            "COPILOT_GITHUB_TOKEN is not configured in Streamlit Secrets."
        )
    return asyncio.run(_generate(build_regression_prompt(facts), token))
