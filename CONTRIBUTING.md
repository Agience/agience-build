# Contributing to Agience Build

**This repo ships no product code.** It holds the skills and hooks that assistants read, the scripts
that install them, and the editor views. Changing how the *workspace* works belongs here. Changing
what the platform *does* does not.

## Build and test

```bash
python -m pytest -q
```

## Rules

1. **`skills/` and `hooks/` are the source.** They run from `~/.claude/`, which no repo tracks. Edit
   them here and run `install_agent_env.py --install`; an edit made at the destination is lost on the
   next install, and `--adopt` is how one is brought back.
2. **The workspace location is configuration, not a guess.** Hooks read `AGIENCE_REPOS` or the
   `repos_root` setting and report when neither is set. Do not add a discovery fallback that walks up
   looking for a marker — it finds a lookalike as readily as the real tree.
3. **Reports by default, writes behind a flag.** Every script here follows it.
4. **Several agents share one checkout.** Run `python scripts/fleet_guard.py preflight <repo>` before
   committing, and stage the paths you changed by name. Never `git add -A`.

## Contributing

Fork, branch from `main`, sign off every commit (`git commit -s`) to certify the
[DCO](https://developercertificate.org/), open a PR. Commit format: `fix:` · `feat(scope):` ·
`docs:` · `test:` · `chore:`.

Licensed under Apache-2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
