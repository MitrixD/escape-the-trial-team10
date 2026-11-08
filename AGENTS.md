# Setting up Verdict Agent for a user

Instructions for an AI coding agent (Claude Code, Cursor, Codex and others) asked to set this project up or show what it does. The user should not have to read the README: you run the steps, show the results and ask before anything that needs their account or touches another folder.

## Rules

- The tool only reads Adapty. Never run `adapty ab-tests start|stop|replace|archive` or any other command that changes the account, and never `adapty apps get` (it prints the secret key).
- Never read, print or commit `.env` or `~/.config/adapty/config.json`.
- Ask the user before: `adapty auth login`, installing the stop guard or the MCP config into a folder outside this repo, and editing `.env`.

## Steps

1. **Set up and check.** Run `scripts/setup.sh`. It finds Python 3.10+, creates `.venv`, installs `requirements.txt`, runs the tests and prints a decision card on a recorded synthetic test. Show the user the card and explain it in two sentences: raw P2BB (received money only) picks `annual_upfront`, while the verdict, counting pending trials and renewals, confirms `weekly_trial`; one more test day costs $148.98, shipping the leader now risks $2.35. Quote only numbers from the card.
2. **Offer the stop guard (no Adapty login needed).** With the user's yes: `scripts/setup.sh --guard <folder> --guard-mode strict`, then tell them to run `cd <folder> && VERDICT_GUARD_REPLAY=<this repo>/tests/fixtures/synthetic/day14 claude` and ask that agent to run `adapty ab-tests stop 50e46448-6692-54c6-b1e0-1b2e2fa62cdd --app 00000000-0000-0000-0000-000000000000 --winner annual_upfront --yes`. The hook denies it before the command runs.
3. **Offer the MCP tool.** With the user's yes: `scripts/setup.sh --mcp <their agent's project>`. It writes `.mcp.json` with the server `verdict-agent` and the tool `ab_test_verdict`.
4. **Offer live reads from their own Adapty account.** Run `scripts/setup.sh --live` and follow its `[todo]` lines: the user logs in with `adapty auth login` themselves; `ADAPTY_EXPECTED_COMPANY` is the company from `adapty auth whoami`; `ADAPTY_APP_ID` is an app of theirs with purchase history. Then `adapty ab-tests list --app <app id> --type flow --json` and `.venv/bin/python -m verdict_agent.cli <test id> --format card`. On a seeded Lumen, the Onboarding test agrees with the dashboard and Main returns `not_enough_data` with a come-back date.

If a step fails, show the exact `[fail]` line and the command output; do not work around it by editing code.

More: `README.md` (section "For judges"), `README.ru.md` in Russian.
