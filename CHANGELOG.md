# Changelog

All notable changes to `agience-build` are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [2026.10.0] - 2026-10-09

### Added

- `hooks/` provides three best-effort hooks that make Mantle the agent's context store. `recall_context.py` (`UserPromptSubmit`) prints recalled artifacts into context, `store_file.py` (`PostToolUse` on `Write|Edit`) stores written files as artifacts, and `archive_transcript.py` (`SessionEnd`) stores the session transcript. When Mantle is down or refuses, a hook exits 0 with no output.
- `scripts/install_agent_env.py` reports drift between the hook sources and the installed copies. With `--install` it copies them into the agent's hooks directory.
- `mantle_target.py [home|dev]` points both the hooks and the agent's `mcpServers.mantle` entry at a single node, recorded in `mantle-target.json`. `mantle_hook_health.py` summarises the hook log, `mantle-hook.log`.
- Hooks authenticate to the target with either a static bearer token or an access token minted from the refresh token in `mantle-refresh-token`, which is kept outside every repository.

### Changed

- `hooks/embedder.py` uses the installed instrument package instead of a workspace checkout on `sys.path`.

### Removed

- The researcher workspace view under `vscode/`; it now lives with the research repositories.
