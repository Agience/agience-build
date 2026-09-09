# agience-build

[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](scripts/)
[![Sponsor](https://img.shields.io/badge/Sponsor-Agience-EA4AAA?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/Agience)

**The agent tooling for a multi-repo workspace.** The skills and hooks that assistants read, the
scripts that install them, and the editor views onto the whole tree.

The repos are **siblings** of this one under a shared parent. That parent holds repos and is not
itself a repo, so the tooling that describes the workspace lives here instead — in a repo that is
pushed, so the workspace carries what restores its own configuration.

## Install the agent environment

`skills/` and `hooks/` are the **source**. They run from `~/.claude/`, which no repo tracks, so a
copy that runs is recoverable from nowhere unless it is installed from one that is.

```bash
python scripts/install_agent_env.py            # what would change, changing nothing
python scripts/install_agent_env.py --install  # copy skills and hooks out to ~/.claude/
python scripts/install_agent_env.py --adopt    # bring an edit made at the destination back here
```

Edit them here and install outward. An edit made at the destination is lost on the next install, and
`--adopt` is how one is brought back.

## Skills

| skill | what it decides |
|---|---|
| [`doc-triage`](skills/doc-triage/SKILL.md) | **where** a document lives — promoted, parked as live work, or set down. Placement only; it rewrites no prose |
| [`doc-current-state`](skills/doc-current-state/SKILL.md) | **how** a document reads — state what is true now, drop the change history. Prose only; it changes no code |
| [`doc-sweep`](skills/doc-sweep/SKILL.md) | the same current-state pass at workspace scale: a mechanical pre-pass, then a ranked worklist handed out one file at a time |

## Hooks — the memory lane

[`hooks/`](hooks/) carries prose and transcripts into a running store and reads context back before a
prompt. Every hook imports `mantle_common`, which is why a missing setting there is reported rather
than raised: a raise would take the whole capture layer down over a value most hooks never read.

| hook | when it runs |
|---|---|
| [`recall_context.py`](hooks/recall_context.py) | before each prompt — the read, and the latency a user waits through |
| [`store_file.py`](hooks/store_file.py) · [`capture_commits.py`](hooks/capture_commits.py) | after an edit, and after a commit |
| [`archive_transcript.py`](hooks/archive_transcript.py) | on `Stop` and `SessionEnd`, into one artifact per session |
| [`mantle_target.py`](hooks/mantle_target.py) · [`mantle_hook_health.py`](hooks/mantle_hook_health.py) | switch nodes; check the lane is live |

**The workspace location is configuration, never a guess.** Set it once with
`python ~/.claude/hooks/mantle_target.py --repos-root <path>`, or export `AGIENCE_REPOS` for a
one-off. There is no discovery fallback: walking up for a marker file either finds nothing, or finds
a lookalike and addresses the wrong tree.

## Scripts

All report by default; writing takes a flag.

| script | what it does | flags |
|---|---|---|
| [`install_agent_env.py`](scripts/install_agent_env.py) | copies [`skills/`](skills/) and [`hooks/`](hooks/) out to `~/.claude/` | `--install` · `--adopt` · `--force` |
| [`fleet_guard.py`](scripts/fleet_guard.py) | the three ways concurrent agents corrupt a shared checkout, made hard to do by accident | `status` · `preflight <repo>` · `release` |
| [`mcp_config.py`](scripts/mcp_config.py) | writes `.vscode/mcp.json` into each repo. The bearer token is a VS Code `${input:}` and is never written to disk | `--write` · `--check` |
| [`import_workspace_to_mantle.py`](scripts/import_workspace_to_mantle.py) | sends the workspace's prose to the active store, covering documents the edit hooks never saw | `--run` · `--only` · `--force` · `--limit` |
| [`doc_sweep.py`](scripts/doc_sweep.py) | the mechanical half of the prose pass: safe deletions applied, everything else flagged for a person | `--write` · `--flags` · `--worklist` |

### Working alongside other agents

Several agents share one checkout. Nothing serialises them, so the tree a command reads is not
necessarily the one it was reasoning about a minute ago.

```bash
python scripts/fleet_guard.py status            # every repo: dirty, staged, remote drift
python scripts/fleet_guard.py preflight <repo>  # is it safe to commit or push here now?
```

`preflight` refuses to call a tree safe while anything is uncommitted, and prints the exact
`--force-with-lease` spec for the sha it just observed. **Stage the paths you changed by name.**
`git add -A` takes whatever is in the tree, including another agent's half-finished edit, and the
commit then lands under a message that does not describe it.

## The views

Five editor workspaces, one per role. Each is a window onto the same disk and copies nothing.

| view | for |
|---|---|
| [`vscode/agience.code-workspace`](vscode/agience.code-workspace) | platform developer / architect — the services and the canon behind them |
| [`vscode/ops.code-workspace`](vscode/ops.code-workspace) | operator — what runs, where it runs, and what ships |
| [`vscode/entroptics.code-workspace`](vscode/entroptics.code-workspace) | researcher — the entroptics repos and the working floor |
| [`vscode/mantle.code-workspace`](vscode/mantle.code-workspace) | the lattice slice |
| [`vscode/agience-all.code-workspace`](vscode/agience-all.code-workspace) | everything, for when the role is not yet clear |

They open the workspace **root** as their first folder, so their paths are relative to
[`vscode/`](vscode/) and read `../..` outward. Adding a repo means adding a folder entry; nothing
else registers it.

The views are windows, not a registry — a repo appears in one because it is on disk, not because the
view enrols it.

## Conventions

- `node.env` is committed and carries no credential; `.env` beside it is ignored. That split is what
  makes configuration reviewable.
- A `_`-prefixed directory is a working tree rather than a product, and is not published.
- Line endings are load-bearing: [`.gitattributes`](.gitattributes) normalises to LF in the
  repository, because a shell script with CRLF fails inside a container with an error that names the
  interpreter rather than the line endings.

Licensed under Apache-2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Contributions:
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Declaration of generative AI use

The author used Anthropic's Claude Opus (versions 4.8 and 5) in the preparation of this work. Its
contribution was to write code, and to generate and validate content. The ideas, the construction
and the claims are the author's. No other generative AI tool was used. The author reviewed and
edited all output and takes full responsibility for the content of this publication.
