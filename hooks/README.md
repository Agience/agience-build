# Claude Code hooks → Mantle

Hooks that make Mantle Claude Code's context store. Sources live here and are installed into
`~/.claude/hooks/`:

```
python agience-build/scripts/install_agent_env.py            # report drift
python agience-build/scripts/install_agent_env.py --install  # copy into ~/.claude
```

| hook | event | does |
|---|---|---|
| `recall_context.py` | `UserPromptSubmit` | recalls artifacts for the prompt and prints them into context |
| `store_file.py` | `PostToolUse` (`Write\|Edit`) | stores the written file as an artifact |
| `archive_transcript.py` | `SessionEnd` | stores the session transcript |

`mantle_common.py` holds the shared HTTP and auth code. Every hook is best-effort: when Mantle is down
or refuses, the hook exits 0 with no output.

**Target.** `python ~/.claude/hooks/mantle_target.py [home|dev]` points both the hooks and Claude
Code's own `mcpServers.mantle` at one node (`~/.claude/mantle-target.json`). Switch only through it;
switching one half by hand writes to one node and recalls from another. `mantle_hook_health.py`
summarises the hook log (`~/.claude/mantle-hook.log`).

**Credentials.** A static bearer for the target, or an access token minted from the refresh token in
`~/.claude/mantle-refresh-token` (outside every repo).

**Checking.** `/hooks` in a session lists what is registered; `claude --debug` shows a hook's stderr.
A hook can be run by hand by piping its JSON input on stdin.
