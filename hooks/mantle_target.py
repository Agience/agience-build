#!/usr/bin/env python3
"""Point Claude Code AND its hooks at one mantle node. Both, or neither.

    python ~/.claude/hooks/mantle_target.py            # show the current target
    python ~/.claude/hooks/mantle_target.py home       # switch
    python ~/.claude/hooks/mantle_target.py dev --dry-run

The whole point is that it writes both. There are two independent paths to mantle:

  · `mcpServers.mantle` in `~/.claude.json` — Claude Code's own tools, a static bearer
  · `mantle_common.py` — the three hooks, an OAuth refresh grant

Nothing connects them. Switching one by hand gives a session that recalls context from one node and
writes to another, with no error on either side — the failure is silent, and it looks like the store
losing things rather than like a misconfiguration. So this is the only supported way to switch, and
it refuses rather than doing half of it (see `_preflight`).

Switching switches identity, not just an address. Each node is its own authority with its own
principals, so the same person is a different subject on each and artifacts do not follow. Nothing
is copied, nothing is migrated, and the previous node's contents stay exactly where they are.

Claude Code reads `~/.claude.json` at startup. The hook half takes effect on the next hook run —
the tool half needs a restart. That gap is the one moment the two halves genuinely disagree, so it
is stated on every switch rather than left to be discovered.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

# A cp1252 console kills the status view without this. Printing `` raises UnicodeEncodeError
# from inside the branch that reports a target as unusable — so the one command whose job is to
# explain why a switch cannot happen would be the one command that crashes. Descriptions carrying
# an em-dash come out as mojibake for the same reason. Reconfiguring is better than retreating to
# ASCII: a terminal that can render these still gets them, and one that cannot gets a replacement
# character instead of a traceback.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TARGET_FILE = Path(os.environ.get(
    "MANTLE_TARGET_FILE", str(Path.home() / ".claude" / "mantle-target.json")))
CLAUDE_CONFIG = Path(os.environ.get(
    "CLAUDE_CONFIG_JSON", str(Path.home() / ".claude.json")))

#: The server name under `mcpServers`. One name, rewritten in place, rather than one entry per
#: node: two registered servers would put both tool sets in front of the model at once and make
#: every call a choice it can get wrong, and `recall` could answer from either store.
SERVER_NAME = "mantle"


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: Dict[str, Any]) -> None:
    """Write via a temp file and one rename. `~/.claude.json` is Claude Code's own live config —
    a truncated write here is not a failed switch, it is a broken client."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _preflight(target: Dict[str, Any], name: str) -> Tuple[bool, str]:
    """Refuse a switch that would leave the two halves pointing at different nodes.

    A target with no bearer cannot serve the MCP half, and a target with no client id cannot serve
    the hook half. Either way, completing the switch would move one consumer — which is the exact
    silent split this tool exists to prevent. Refusing loudly with the reason beats a switch that
    half-worked and reads as the store misbehaving.
    """
    missing = [k for k in ("mcp_url",) if not target.get(k)]
    if not target.get("mcp_bearer"):
        missing.append("mcp_bearer (Claude Code's tools cannot authenticate)")

    # A static bearer satisfies both halves at once, so the OAuth trio is only required when
    # there is no static bearer to fall back on. `home` is its own authority and verifies a token
    # minted from its own KEYS_DIR, so it needs no registered client, no refresh token and no
    # password; `dev` sits behind an Origin and uses the refresh grant. Demanding the OAuth fields
    # of every target would block the switch on credentials one of them structurally does not need.
    if not target.get("mcp_bearer"):
        if not target.get("token_url"):
            missing.append("token_url (no static bearer, so the hooks need the OAuth endpoint)")
        if not target.get("client_id"):
            missing.append("client_id (no static bearer, so the hooks cannot mint one)")
        token_file = os.path.expanduser(target.get("refresh_token_file") or "")
        if token_file and not Path(token_file).exists():
            missing.append(f"refresh token file {token_file} (does not exist)")
    if missing:
        return False, (f"target {name!r} is not usable yet — missing:\n    - "
                       + "\n    - ".join(missing))
    return True, ""


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv[1:]

    try:
        cfg = _load(TARGET_FILE)
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {TARGET_FILE}: {e}", file=sys.stderr)
        return 1
    targets: Dict[str, Any] = cfg.get("targets") or {}
    active = cfg.get("active") or ""

    if not args:
        print(f"active target: {active}")
        for name, t in targets.items():
            mark = "*" if name == active else " "
            ok, why = _preflight(t, name)
            print(f"  {mark} {name:6} {t.get('mcp_url','')}")
            print(f"      {t.get('description','')}")
            if not ok:
                print(f"      ⛔ not switchable: {why.splitlines()[0].split('missing:')[0].strip()}")
                for line in why.splitlines()[1:]:
                    print(f"      {line}")
        return 0

    name = args[0]
    if name not in targets:
        print(f"unknown target {name!r} — known: {', '.join(targets) or '(none)'}", file=sys.stderr)
        return 2
    target = targets[name]

    ok, why = _preflight(target, name)
    if not ok:
        print(f"⛔ refusing to switch: {why}", file=sys.stderr)
        print("\nNothing was changed. Both halves must be able to authenticate, or the switch\n"
              "would move one consumer and leave the other on the old node.", file=sys.stderr)
        return 3

    try:
        cc = _load(CLAUDE_CONFIG)
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {CLAUDE_CONFIG}: {e}", file=sys.stderr)
        return 1

    servers = cc.setdefault("mcpServers", {})
    entry = servers.setdefault(SERVER_NAME, {"type": "http"})
    before = entry.get("url")
    entry["type"] = "http"
    entry["url"] = target["mcp_url"]
    # ── the SCHEME, not just the token ──────────────────────────────────────────────────────────
    # Measured 2026-08-27: this line wrote the bare JWT, and `https://mantle.home.agience.ai/mcp`
    # answers **401** to the raw token and **200 with 7 tools** to the same token behind `Bearer `.
    # So the MCP half had never authenticated — the mantle tools were absent from every session,
    # while `mantle_common` built its own header as `f"Bearer {token}"` and the hook half worked.
    #
    # That is the same split this file exists to prevent, on an axis it was not checking: the two
    # halves agreed on the NODE and disagreed on how to address it. `_preflight` compares urls, and
    # a url that matches is not a lane that works.
    #
    # The failure is silent in the worst way. A rejected MCP server surfaces as a model that simply
    # has no mantle tools — indistinguishable from a node that was never configured, and invisible
    # to `mantle_hook_health.py`, which reads the hook log and never exercises this header.
    #
    # Idempotent: a value that already carries the scheme is left alone rather than doubled, so
    # re-running this against a config an operator has already fixed by hand is safe.
    _bearer = str(target["mcp_bearer"]).strip()
    if not _bearer.lower().startswith("bearer "):
        _bearer = "Bearer " + _bearer
    entry.setdefault("headers", {})["Authorization"] = _bearer

    cfg["active"] = name

    if dry:
        print(f"DRY RUN — nothing written\n"
              f"  mcpServers.{SERVER_NAME}.url : {before} -> {target['mcp_url']}\n"
              f"  hooks (mantle-target.json)   : {active} -> {name}")
        return 0

    # The client config is backed up before it is touched. It holds far more than this one entry,
    # and an operator who wants the previous state back should not have to reconstruct it.
    try:
        shutil.copy2(CLAUDE_CONFIG, CLAUDE_CONFIG.with_suffix(".json.bak"))
    except OSError:
        pass

    _save(CLAUDE_CONFIG, cc)
    _save(TARGET_FILE, cfg)

    print(f"✅ target is now {name}  ({target['mcp_url']})")
    print(f"   hooks      : active immediately — the next hook run reads the new target")
    print(f"   Claude Code: RESTART REQUIRED — ~/.claude.json is read at startup")
    print(f"   backup     : {CLAUDE_CONFIG.with_suffix('.json.bak').name}")
    print()
    print("   Until the restart, the tools still answer from the previous node while the hooks")
    print("   answer from this one. That is the one window where the two halves disagree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
