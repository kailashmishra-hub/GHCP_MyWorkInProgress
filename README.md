GHCP SDK - GitHub Impacted Scenarios Tracker

Terminal impact workflow
------------------------
Run the analyzer directly when you do not want to launch Streamlit:

    python impact_analyzer.py

This writes:

    runtime/impact-report.json
    runtime/trace-agent-input.json
    runtime/trace-agent-prompt.md
    runtime/impacts-facts.json
    runtime/copilot-agent-prompt.md

GitHub Copilot Agent writes its selected subset to:

    runtime/copilot-regression-subset.json

To analyze a pull request directly:

    python impact_analyzer.py --pull-request https://github.com/owner/repository/pull/123

Manual GitHub Copilot Agent subset selection:

1. Run `python impact_analyzer.py`.
2. Open GitHub Copilot Agent.
3. Run the custom agent named `trace_impact`.
4. Ask it to trace impacted scenarios from `runtime/trace-agent-input.json` and write `runtime/impacts-facts.json`.
5. Run the custom agent named `copilot_agent_prompt`.
6. Ask it to select the RBT regression subset from `runtime/impacts-facts.json`.
7. Let Copilot Agent create or overwrite `runtime/copilot-regression-subset.json`.

If the custom agent only starts and says it is ready, paste this follow-up:

    Read runtime/trace-agent-input.json, follow indirect step-definition call chains, and write the impacted scenario facts to runtime/impacts-facts.json.

Then run `copilot_agent_prompt` and paste:

    Read runtime/impacts-facts.json, apply the RBT risk_score rules from your agent instructions, and write the final JSON result to runtime/copilot-regression-subset.json.

If Trace Agent returns JSON in chat but does not write the file, paste the JSON into
`runtime/trace-agent-response.json`, then run:

    python impact_analyzer.py --save-trace-response runtime/trace-agent-response.json

If Copilot returns the JSON in chat but does not write the file, paste the JSON into
`runtime/copilot-response.json`, then run:

    python impact_analyzer.py --save-copilot-response runtime/copilot-response.json

Streamlit impact dashboard
--------------------------
The dashboard lists every changed source class in a pull request, shows its code
diff, prepares Trace Agent inputs, traces impacted scenarios through Copilot when
`COPILOT_GITHUB_TOKEN` is configured, and then selects a small RBT regression
subset through Copilot.
It analyzes an active GitHub pull-request URL and compares the PR head with the
target branch configured on that pull request.

    python -m pip install -r requirements.txt
    streamlit run streamlit_app.py

The deterministic recommendation works without an API key. The AI recommendation
uses the Python GitHub Copilot SDK and does not require reviewers to install or log
in to a separate command-line application.

When `COPILOT_GITHUB_TOKEN` is present, the Streamlit buttons run the Trace Agent
and subset prompt directly and write:

    runtime/impacts-facts.json
    runtime/copilot-regression-subset.json

For local development, create `.streamlit/secrets.toml` (this file is ignored by
Git) with:

    COPILOT_GITHUB_TOKEN = "github_pat_your_token"

For Streamlit Community Cloud:

1. Deploy this repository and set `streamlit_app.py` as the entry point.
2. Open the app's **Settings > Secrets** page.
3. Add `COPILOT_GITHUB_TOKEN = "github_pat_your_token"`.
4. Reboot the app after saving the secret.

Use a supported fine-grained PAT (`github_pat_`), GitHub OAuth user token (`gho_`),
or GitHub App user token (`ghu_`) belonging to a user with GitHub Copilot access.
Do not commit a real token. The SDK package manages its own runtime, so no separate
CLI installation command is needed on Streamlit Cloud. Its first request can take
longer while that runtime is downloaded and started.

The single secret above is suitable for a private prototype: every reviewer uses
the configured account's Copilot entitlement. A production multi-user deployment
should authenticate each reviewer with GitHub OAuth and pass that reviewer's token
to an isolated Copilot SDK session.

Public pull requests need no repository-access token. To analyze private GitHub
repositories, add a separate Streamlit secret with read access to repository
contents and pull requests:

    GITHUB_REPOSITORY_TOKEN = "github_pat_your_repository_read_token"

Do not reuse a Copilot-Requests-only token for GitHub repository API access.
