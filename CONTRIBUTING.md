# Contributing

## Branches

- `main` is the published record. The frozen policy freeze commit and other receipts
  point at it, so history on `main` is never rewritten or force-pushed.
- `dev` is the integration branch, if the maintainer has created it. Open feature PRs
  against `dev`; `dev` is merged to `main` when a batch is ready. If `dev` does not exist
  yet, target `main`.
- Name feature branches by intent, for example `fix/telegram-allowlist` or
  `docs/architecture`.

```bash
git fetch origin
git switch -c fix/my-change origin/dev   # or origin/main if there is no dev branch
# ... edit, test ...
git push -u origin fix/my-change
gh pr create --base dev
```

## Before opening a PR

1. Use Python 3.11+ and run the suite from the repo root:

   ```bash
   python -m pytest tests -q
   ```

2. Run the offline smoke scripts if you touched the gate, scorer, or adapters
   (see `docs/development.md`).
3. Add a test for any behavior change. Tests must not hit the network.

## What not to change

- Frozen policies, anchor files, and their hashes.
- Scoring math and verdict thresholds that back recorded results, unless the PR is
  explicitly about that and says why.
- Dated docs (`docs/*_2026-06-*.md`). Add a new dated doc instead.
- Anything that would add a Robinhood auth or order path.

## Secrets

Never commit tokens, captured manifests, raw account responses, or `var/` logs. Use env
vars. If a secret is committed by accident, rotate it first, then remove it.
