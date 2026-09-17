from __future__ import annotations

import difflib
import html
import os

import streamlit as st

from impact_analyzer import Analysis, NoActivePullRequest, analyze, parse_github_pull_location, prepare_remote_pull_repository, risk_score
from impact_analyzer import Analysis, NoActivePullRequest, analyze, parse_github_pull_location, prepare_remote_pull_repository, risk_score, write_impact_facts

from copilot_service import generate_regression_subset


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


def candidate_rows(analysis: Analysis) -> list[dict[str, object]]:
    return [{
        "scenario_id": impact.scenario.key,
        "feature": impact.scenario.file,
        "scenario": impact.scenario.name,
        "tags": impact.scenario.tags,
        "impacted_steps": impact.impacted_steps,
        "changed_classes": impact.changed_files,
        "trace_reasons": impact.reasons,
        "coverage_unit_ids": sorted(impact.coverage_units),
        "risk_score": risk_score(impact),
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


def ai_recommendation(analysis: Analysis, github_token: str) -> str:
    impacting_paths = sorted({path for impact in analysis.impacts for path in impact.changed_files})
    required_units = sorted(set().union(*(impact.coverage_units for impact in analysis.impacts)))
    facts = {
        "changed_files_with_feature_impact": impacting_paths,
        "required_coverage_unit_ids": required_units,
        "impacted_scenarios": candidate_rows(analysis),
    }
    decision = generate_regression_subset(facts, github_token)
    by_id = {impact.scenario.key: impact for impact in analysis.impacts}
    selected_entries = decision.get("selected_scenarios", [])
    selected: list[tuple[object, str]] = []
    seen: set[str] = set()
    for entry in selected_entries:
        if not isinstance(entry, dict):
            raise RuntimeError("GitHub Copilot returned an invalid selected_scenarios entry.")
        scenario_id = str(entry.get("scenario_id", ""))
        if scenario_id not in by_id:
            raise RuntimeError(f"GitHub Copilot selected an unknown scenario: {scenario_id or '(missing ID)'}")
        if scenario_id not in seen:
            selected.append((by_id[scenario_id], str(entry.get("reason", "Selected by GitHub Copilot."))))
            seen.add(scenario_id)

    all_units = set(required_units)
    covered_units = set().union(*(impact.coverage_units for impact, _ in selected)) if selected else set()
    uncovered_units = sorted(all_units - covered_units)
    rows = [
        "| Priority | Feature | Scenario | Tags | Copilot selection reason |",
        "|---:|---|---|---|---|",
    ]
    for priority, (impact, reason) in enumerate(selected, 1):
        clean = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        rows.append(
            f"| {priority} | {clean(impact.scenario.file)} | {clean(impact.scenario.name)} | "
            f"{clean(' '.join(impact.scenario.tags) or '—')} | "
            f"{clean(reason)} |"
        )
    if not selected:
        rows.append("| — | — | No scenarios selected | — | Copilot returned an empty subset. |")
    summary = str(decision.get("summary", "No overall rationale was returned."))
    validation = (
        "✅ Python validation: all traceable PR impact units are covered."
        if not uncovered_units else
        "⚠️ Python validation: Copilot left these impact units uncovered: `" + "`, `".join(uncovered_units) + "`."
    )
    return "\n".join(rows) + f"\n\n**GitHub Copilot assessment:** {summary}\n\n{validation}"


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
        "View every scenario traced by impact_analyzer.py before GitHub Copilot selects a smaller subset."
    )
    if st.button("Find all potentially impacted scenarios"):
        st.session_state.show_impacted_scenarios = True
        facts_file = write_impact_facts(analysis)
        st.success(f"Impact facts saved to {facts_file}.")
    if st.session_state.get("show_impacted_scenarios"):
        st.metric("Potentially impacted scenarios", len(analysis.impacts))
        if analysis.impacts:
            st.dataframe(impact_rows(analysis), use_container_width=True, hide_index=True)
        else:
            st.info("impact_analyzer.py did not trace any feature scenarios to the changed class behavior.")

    st.subheader("3. GitHub Copilot recommended regression subset")
    st.caption("GitHub Copilot reviews only the traceable impacted scenarios and chooses the smallest risk-aware subset that covers the changed class behavior.")
    if not analysis.impacts:
        st.info("There are no impacted scenarios for AI to optimize.")
        return
    if st.button("Generate smallest subset with GitHub Copilot", type="primary"):
        try:
            with st.spinner("GitHub Copilot is selecting the smallest risk-aware regression subset..."):
                st.session_state.ai_review = ai_recommendation(analysis, copilot_github_token)
        except Exception as exc:
            st.error(f"GitHub Copilot generation failed: {exc}")
    if st.session_state.get("ai_review"):
        st.markdown(st.session_state.ai_review)


if __name__ == "__main__":
    main()
