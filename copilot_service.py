from __future__ import annotations

import asyncio
import json
from typing import Any


def build_regression_prompt(facts: dict[str, Any]) -> str:
    return (
        "You are a senior test-impact analyst. Use only the supplied facts. Select the smallest "
        "defensible scenario subset that covers every changed class and impacted step, prioritizing "
        "higher regression risk when multiple equally small subsets exist. Never invent files, tags, "
        "or scenarios. Return a concise Markdown table with Priority, Feature, Scenario, Tags, and "
        "Coverage reason, followed by one sentence explaining why the subset is sufficient.\n\n"
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
    client = CopilotClient(mode="empty", use_logged_in_user=False)
    session = None
    try:
        await client.start()
        session = await client.create_session(
            github_token=github_token,
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
