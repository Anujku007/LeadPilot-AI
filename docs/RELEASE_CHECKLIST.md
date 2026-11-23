# LeadPilot AI — v1.0.0 release checklist

**Goal:** publish the locally verified source code without leaking CRM records or credentials. The release scripts should run on the Windows machine that owns `D:\LeadPilot_AI`.

## Before publishing

1. Keep `D:\LeadPilot_AI\leadpilot_data.sqlite3`, `.env`, Google OAuth files, and admin account material private; do not share them in screenshots or commit them.
2. Review `docs/screenshots/*.png`. The provided images were captured from your demo UI, with demo lead IDs and local usernames. Replace or remove any screenshot you do not want publicly visible.
3. Run the Python tests against an isolated test database and `npm run build`; fix unexpected failures rather than claiming success based on prior runs.
4. Confirm a signed-out call to `/api/dashboard/summary` returns **401**, and sales staff cannot load someone else's lead (**403**). Avoid using real customer data in tests.
5. Confirm `git remote -v` points to **Anujku007/LeadPilot-AI** and `git branch --show-current` is `main`.
6. `git fetch origin main`. Do not force-push a diverged history; reconcile it first.
7. Review `git diff`, `git status`, and `git diff --cached --stat`; staged content is what will be published.
8. Before publishing, run `python scripts/release_verify.py --staged-scan` to block secret-like file names and obvious leaked credentials.
9. Commit and push verified changes. Create and push **annotated** `v1.0.0` only after the commit lands. Do not overwrite an existing tag.
10. Confirm GitHub's README, files, screenshots, and tag match your local release.

## Verified vs. outstanding

- Verified from the user's latest installation: salesperson viewport and panel scrolling; frontend production build reported success.
- Previously verified: NVIDIA browser voice, BANT, calendar event, CRM workflow; authentication 401; role-restricted staff workspace.
- Full test suite **after** the latest multi-user/viewport changes is pending local execution; do not report pass without new output.
- Public deployment is **not yet complete**; see `DEPLOYMENT_READINESS.md`.

## Suggested release commit

`feat: release LeadPilot AI local MVP with team CRM and voice copilot`

## Troubleshooting

- If the full suite fails due to old unauthenticated fixtures: update those tests with proper auth fixtures and rerun. Do not bypass auth or expose the API.
- If Git reports `non-fast-forward`, do not use `--force`. Inspect `git log --oneline --graph --all` and reconcile the remote before continuing.
- If staged scan finds secrets: unstage them with `git restore --staged <path>`, remove them from tracking with `git rm --cached <path>` if necessary, and rotate any credential that was already pushed.
- If a screenshot contains a private lead name, either replace it with a clean demo screenshot or remove it before publishing.
