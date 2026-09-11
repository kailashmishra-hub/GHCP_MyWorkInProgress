GHCP - Cucumber BDD Automation Framework (sample)

Streamlit impact dashboard
--------------------------
The dashboard compares any local Git repository with master/main, lists all file
changes, traces Java/page-object and step-definition changes to Cucumber scenarios
and tags, and selects a small regression subset using coverage optimization.
It analyzes an active GitHub pull-request URL and compares the PR head with the
target branch configured on that pull request.

    python -m pip install -r requirements.txt
    streamlit run streamlit_app.py

The deterministic recommendation works without an API key. The AI recommendation
uses the Python GitHub Copilot SDK and does not require reviewers to install or log
in to a separate command-line application.

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

Purpose
-------
This repository (GHCP) contains a minimal Java project with a small sample application and unit test. The repository name and layout suggest it is intended as a Cucumber BDD automation framework, but the current source contains only a basic Maven Java app (org.example.App) and a JUnit 3 style test (AppTest).

Prerequisites
-------------
- Java JDK 8+ installed and JAVA_HOME set
- Maven 3.x installed and on your PATH

Build and test
--------------
From the repository root (where pom.xml is located):

- Build: mvn clean package
- Run unit tests: mvn test
- Run the application jar (after build): java -cp target/GHCP-1.0-SNAPSHOT.jar org.example.App

Cucumber tests (notes)
----------------------
This project currently has no Cucumber dependencies or .feature files. To add and run Cucumber tests:

1. Add Cucumber dependencies to pom.xml (cucumber-java, cucumber-junit or cucumber-junit-platform-engine for JUnit 5).
2. Add a test runner class annotated for Cucumber (or use the JUnit platform).
3. Place .feature files under src/test/resources/features and step definitions under src/test/java.
4. Run with: mvn test or using a specific Cucumber CLI option, e.g.:
   mvn test -Dcucumber.options="--tags @smoke"

Typical usage
-------------
- Developers will add step definitions under src/test/java and feature files under src/test/resources/features.
- Use Maven to build and execute tests. If you add the Cucumber dependencies, you can run BDD scenarios with the test runner.

Notes and assumptions
---------------------
- The current pom.xml only declares JUnit 3.8.1 as a test dependency; no Cucumber dependencies were found.
- No .feature files are present in the repository.
- Documentation under docs/ describes the existing package org.example and its classes.

Files created by doc-writer
--------------------------
- README.md (this file)
- docs/index.md
- docs/org.example.md
- docs/org.example.App.md

If you want me to add Cucumber support (pom changes, example feature + step defs, and a test runner), tell me and I can create a minimal working example.
