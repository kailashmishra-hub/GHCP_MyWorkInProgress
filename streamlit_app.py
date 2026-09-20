from __future__ import annotations

import difflib
import html
import json
import os
from pathlib import Path

import streamlit as st

from impact_analyzer import (
    Analysis,
    NoActivePullRequest,
    analyze,
    build_copilot_agent_prompt,
    parse_github_pull_location,
    parse_copilot_subset_response,
    parse_trace_agent_response,
    prepare_remote_pull_repository,
    write_copilot_agent_prompt,
    write_trace_agent_files,
)
from copilot_service import generate_copilot_response


st.set_page_config(page_title="GitHub Impact Tracker", page_icon="🔎", layout="wide")

STATUS_NAMES = {
    "A": "Added",
    "C": "Copied",
    "D": "Deleted",
    "M": "Modified",
    "R": "Renamed",
    "U": "Unmerged",
}


def impact_rows(analysis: Analysis) -> list[dict[str, object]]:
    return [{
        "Feature": impact.scenario.file,
        "Scenario": impact.scenario.name,
        "Tags": " ".join(impact.scenario.tags) or "—",
        "Impacted steps": " | ".join(impact.impacted_steps),
        "Changed classes": " | ".join(impact.changed_files),
        "Reason": " | ".join(impact.reasons),
    } for impact in analysis.impacts]


def highlighted_pair(before: str, after: str, before_changed: bool, after_changed: bool) -> tuple[str, str]:
    if not before_changed and not after_changed:
        return html.escape(before), html.escape(after)
    if not before:
        return "<span class='diff-absent'>(not present)</span>", f"<mark>{html.escape(after)}</mark>"
    if not after:
        return f"<mark>{html.escape(before)}</mark>", "<span class='diff-absent'>(removed)</span>"
    before_parts: list[str] = []
    after_parts: list[str] = []
    for operation, a1, a2, b1, b2 in difflib.SequenceMatcher(None, before, after).get_opcodes():
        before_text = html.escape(before[a1:a2])
        after_text = html.escape(after[b1:b2])
        if operation == "equal":
            before_parts.append(before_text)
            after_parts.append(after_text)
        else:
            if before_text:
                before_parts.append(f"<mark>{before_text}</mark>")
            if after_text:
                after_parts.append(f"<mark>{after_text}</mark>")
    return "".join(before_parts), "".join(after_parts)


def render_code_change_table(change) -> None:
    rows: list[str] = []
    for row in change.rows:
        before, after = highlighted_pair(row.before, row.after, row.before_changed, row.after_changed)
        changed_class = " changed-row" if row.before_changed or row.after_changed else ""
        rows.append(
            f"<tr class='{changed_class}'><td><code>{before}</code></td>"
            f"<td><code>{after}</code></td></tr>"
        )
    st.markdown(
        """
        <style>
        .code-diff { width: 100%; border-collapse: collapse; table-layout: fixed; margin: .35rem 0 1rem; }
        .code-diff th { text-align: left; padding: .55rem .7rem; border: 1px solid #d0d7de; background: #f6f8fa; }
        .code-diff td { width: 50%; vertical-align: top; padding: .4rem .7rem; border: 1px solid #d8dee4; }
        .code-diff code { white-space: pre-wrap; overflow-wrap: anywhere; color: inherit; background: transparent; }
        .code-diff mark { background: #d0d0d0; color: #111; padding: 1px 0; }
        .code-diff .diff-absent { color: #6e7781; font-style: italic; }
        </style>
        """
        f"<table class='code-diff'><thead><tr><th>Master code</th><th>Committed code</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>",
        unsafe_allow_html=True,
    )


def configured_secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return os.environ.get(name, "").strip()


def write_json_file(path: str | Path, payload: dict[str, object]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def sdk_prompt_with_json(prompt: str, json_path: str | Path, label: str) -> str:
    payload = Path(json_path).read_text(encoding="utf-8")
    return (
        f"{prompt}\n\n"
        "IMPORTANT FOR THIS STREAMLIT SDK RUN:\n"
        "You cannot read or write workspace files directly in this SDK session. "
        "Use the embedded JSON below as the complete input data. Return JSON only in the requested shape; "
        "the Streamlit app will validate and save your response to disk.\n\n"
        f"{label}:\n"
        "```json\n"
        f"{payload}\n"
        "```"
    )


def render_analysis(analysis: Analysis) -> None:
    st.caption(
        f"Comparison: `{analysis.base_ref}` → `{analysis.target_ref}` "
        f"(base commit `{analysis.base_sha[:10]}`)"
    )
    changed_classes = [item for item in analysis.changed_files if item.source]
    impacting_paths = {path for impact in analysis.impacts for path in impact.changed_files}
    st.metric("Changed class files", len(changed_classes))

    st.subheader("1. Changed class files")
    if changed_classes:
        for item in changed_classes:
            with st.expander(f"{STATUS_NAMES.get(item.status, item.status)} · {item.path}", expanded=True):
                if item.path not in impacting_paths:
                    st.caption("No existing feature scenario references the changed behavior in this class.")
                for change in item.code_changes:
                    st.markdown(f"**Method/Function:** `{change.method}`")
                    st.markdown(f"**Change Type:** {change.change_type}")
                    render_code_change_table(change)
    else:
        st.info("No class files changed in this pull request.")

def main() -> None:
    st.title("GitHub Impacted Scenarios Tracker")
    st.write("Analyze a GitHub pull request, trace source changes into Cucumber scenarios, and choose a compact regression set.")

    with st.sidebar:
        st.header("Repository")
        pull_request_link = st.text_input(
            "GitHub pull request link",
            placeholder="https://github.com/owner/repository/pull/1",
            help="You can also enter the repository pull-request list URL ending in /pulls.",
        )
        st.text_input("Base branch", value="PR target branch (automatic)", disabled=True)
        analyze_clicked = st.button("Analyze impact", type="primary", use_container_width=True)

        st.divider()
        st.header("GitHub Copilot")
        copilot_github_token = configured_secret("COPILOT_GITHUB_TOKEN")
        repository_github_token = configured_secret("GITHUB_REPOSITORY_TOKEN")
        if copilot_github_token:
            st.success("Copilot SDK is configured")
        else:
            st.warning("Copilot SDK token is not configured.")
            st.caption("Add COPILOT_GITHUB_TOKEN to Streamlit Secrets. Do not put the token in this repository.")

    if analyze_clicked:
        try:
            with st.spinner("Comparing Git changes and tracing Cucumber coverage..."):
                if not parse_github_pull_location(pull_request_link):
                    st.error("Enter a valid GitHub PR link ending in /pull/NUMBER or /pulls.")
                    return
                analysis_repo, pull_number, base_ref = prepare_remote_pull_repository(
                    pull_request_link, repository_github_token
                )
                target_ref = "HEAD"
                st.session_state.pr_number = pull_number
                st.session_state.analysis = analyze(analysis_repo, base_ref, target_ref, False)
                st.session_state.pop("ai_review", None)
                st.session_state.pop("show_impacted_scenarios", None)
        except NoActivePullRequest as exc:
            st.session_state.pop("analysis", None)
            st.session_state.pop("ai_review", None)
            st.session_state.pop("show_impacted_scenarios", None)
            st.session_state.pop("pr_number", None)
            st.info(str(exc))
            return
        except Exception as exc:
            st.error(str(exc))
            return

    analysis = st.session_state.get("analysis")
    if not analysis:
        st.info("Choose a repository and select **Analyze impact**.")
        return
    if st.session_state.get("pr_number"):
        st.success(f"Analyzing GitHub pull request #{st.session_state.pr_number} against its target branch.")
    render_analysis(analysis)

    st.subheader("2. All potentially impacted scenarios")
    st.caption(
        "Generate Trace Agent inputs so the agent can follow direct and indirect step-definition call chains."
    )
    if st.button("Find all potentially impacted scenarios"):
        st.session_state.show_impacted_scenarios = True
        trace_input_file, trace_prompt_file = write_trace_agent_files(analysis)
        subset_prompt_file = write_copilot_agent_prompt()
        st.session_state.trace_input_file = str(trace_input_file)
        st.session_state.trace_prompt_file = str(trace_prompt_file)
        st.session_state.subset_prompt_file = str(subset_prompt_file)
        st.success("Trace Agent inputs are ready.")
        if copilot_github_token:
            try:
                with st.spinner("Copilot is tracing impacted scenarios..."):
                    trace_prompt = Path(trace_prompt_file).read_text(encoding="utf-8")
                    trace_sdk_prompt = sdk_prompt_with_json(trace_prompt, trace_input_file, "Trace Agent input JSON")
                    trace_response = generate_copilot_response(trace_sdk_prompt, copilot_github_token)
                    trace_facts = parse_trace_agent_response(trace_response)
                    facts_file = write_json_file(Path("runtime") / "impacts-facts.json", trace_facts)
                    st.session_state.trace_facts = trace_facts
                    st.session_state.trace_facts_file = str(facts_file)
                st.success(f"Copilot Trace Agent saved impacted scenario facts to {facts_file}.")
            except Exception as exc:
                st.error(f"Copilot Trace Agent failed: {exc}")
    if st.session_state.get("show_impacted_scenarios"):
        if copilot_github_token:
            st.info("Copilot token is configured, so Streamlit can run the Trace Agent prompt directly.")
        else:
            st.info(
                "Streamlit prepared the files. Configure COPILOT_GITHUB_TOKEN to run Copilot here, "
                "or open Copilot Chat/Agent in your IDE, run the custom agent named `trace_impact`, "
                "and paste the prompt below."
            )
        if st.session_state.get("trace_facts"):
            impacted = st.session_state.trace_facts.get("impacted_scenarios", [])
            st.metric("Trace Agent impacted scenarios", len(impacted) if isinstance(impacted, list) else 0)
            if impacted:
                st.dataframe(impacted, use_container_width=True, hide_index=True)
            if st.session_state.get("trace_facts_file"):
                st.caption(f"Trace facts: `{st.session_state.trace_facts_file}`")
        if st.session_state.get("trace_input_file"):
            st.caption(f"Trace input: `{st.session_state.trace_input_file}`")
        if st.session_state.get("trace_prompt_file"):
            st.caption(f"Trace prompt: `{st.session_state.trace_prompt_file}`")
            trace_prompt = Path(st.session_state.trace_prompt_file).read_text(encoding="utf-8")
            st.text_area("Prompt for trace_impact agent", trace_prompt, height=260)
        st.caption("If the agent replies with JSON but does not write the file, save that JSON and run: "
                   "`python impact_analyzer.py --save-trace-response runtime\\trace-agent-response.json`")

    st.subheader("3. Risk-based subset agent")
    st.caption("After Trace Agent writes runtime/impacts-facts.json, run the Copilot subset agent.")
    if st.session_state.get("subset_prompt_file"):
        if copilot_github_token:
            if st.button("Generate risk-based subset with Copilot", type="primary"):
                try:
                    with st.spinner("Copilot is selecting the RBT regression subset..."):
                        facts_file = Path("runtime") / "impacts-facts.json"
                        subset_prompt = build_copilot_agent_prompt(facts_file, Path("runtime") / "copilot-regression-subset.json")
                        subset_sdk_prompt = sdk_prompt_with_json(subset_prompt, facts_file, "Impact facts JSON")
                        subset_response = generate_copilot_response(subset_sdk_prompt, copilot_github_token)
                        subset = parse_copilot_subset_response(subset_response)
                        subset_file = write_json_file(Path("runtime") / "copilot-regression-subset.json", subset)
                        st.session_state.copilot_subset = subset
                        st.session_state.copilot_subset_file = str(subset_file)
                    st.success(f"Copilot subset saved to {subset_file}.")
                except Exception as exc:
                    st.error(f"Copilot subset generation failed: {exc}")
            if st.session_state.get("copilot_subset"):
                st.json(st.session_state.copilot_subset)
                st.caption(f"Subset output: `{st.session_state.copilot_subset_file}`")
        else:
            st.info(
                "Configure COPILOT_GITHUB_TOKEN to run the subset selection here, or run the custom agent named "
                "`copilot_agent_prompt` and paste the prompt below."
            )
        st.caption(f"Subset prompt: `{st.session_state.subset_prompt_file}`")
        subset_prompt = Path(st.session_state.subset_prompt_file).read_text(encoding="utf-8")
        st.text_area("Prompt for copilot_agent_prompt agent", subset_prompt, height=240)
    else:
        st.markdown("Click **Find all potentially impacted scenarios** first to generate the subset-agent prompt.")


if __name__ == "__main__":
    main()
