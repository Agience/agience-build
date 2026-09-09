r"""Import every prose document in the workspace into the active Mantle node.

    python agience-build/scripts/import_workspace_to_mantle.py             # report; writes nothing
    python agience-build/scripts/import_workspace_to_mantle.py --run
    python agience-build/scripts/import_workspace_to_mantle.py --run --only 'agience-pharos/*'
    python agience-build/scripts/import_workspace_to_mantle.py --run --force   # re-send unchanged

## What this is for

The hooks capture a document when somebody edits it. That is the right trigger and it has one gap:
**a file nobody has touched since the hooks started working has never been sent.** So the store
knows the corner of the workspace that happened to be edited recently, and nothing else. This is the
backfill — one pass that puts the whole corpus in, after which the hooks keep it current.

## It shares its identity rules with the hook, by importing them

`_identity`, `_content_type_for` and `_should_capture` are imported from `store_file.py` rather than
reimplemented. That is the whole design:

    identity = "file:" + normcase(resolved absolute path)

Mantle derives the artifact id from `identity`, so **a bulk import and a later hook write of the
same file land on the same artifact** — the import seeds it, the edit versions it, and there is no
duplicate. A second copy of that rule here would be a second answer to "which artifact is this
file", and the day the two disagreed the store would grow a shadow copy of every document with
nobody told.

The capture rule travels the same way: prose suffixes only, and never a temp, cache or VCS path.
`_scratch` reads like a temp directory and is deliberately NOT one — it holds notes meant to
survive, which is exactly the prose this exists for.

## Resumable, and cheap to re-run

A ledger at `~/.claude/mantle-import-ledger.json` records `identity -> sha256(content)`. A re-run
sends only what changed, so an interrupted import resumes and a scheduled one costs almost nothing.
`--force` re-sends everything regardless.

**A write can succeed and still not be confirmed.** The server finishes encrypting and indexing
whether or not the client is still listening, so a timeout is UNKNOWN, not FAILED. Unconfirmed
writes are counted separately and are NOT recorded in the ledger, so the next run retries them —
which is safe precisely because `identity` makes a retry an update rather than a second copy.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

HOOKS = Path.home() / ".claude" / "hooks"
LEDGER = Path.home() / ".claude" / "mantle-import-ledger.json"

sys.path.insert(0, str(HOOKS))
try:
    import mantle_common as mc
    import store_file as sf
except ImportError as exc:  # pragma: no cover - an install problem, not a runtime one
    print("cannot import the hook modules from %s: %s" % (HOOKS, exc), file=sys.stderr)
    print("Run: python agience-build/scripts/install_agent_env.py --install", file=sys.stderr)
    raise SystemExit(2)

#: Directory names never walked. This is about the WALK being cheap; the authoritative decision on
#: any individual file is `store_file._should_capture`, which is also what the hook uses.
_PRUNE = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
          ".pytest_cache", ".ruff_cache", "site-packages", "_secret", "_ci-work",
          ".mypy_cache", "htmlcov", ".next", ".vite", "_archive"}


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_ledger() -> Dict[str, str]:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_ledger(d: Dict[str, str]) -> None:
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=0), encoding="utf-8")
    os.replace(tmp, LEDGER)


def discover(root: Path, only: str | None) -> List[Path]:
    out: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE]
        for name in filenames:
            p = Path(dirpath) / name
            if not sf._should_capture(p):
                continue
            if only:
                rel = p.relative_to(root).as_posix()
                if not fnmatch.fnmatch(rel, only):
                    continue
            out.append(p)
    return sorted(out)


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true", help="actually send; default reports only")
    ap.add_argument("--only", default=None, help="glob over the workspace-relative path")
    ap.add_argument("--force", action="store_true", help="re-send even if unchanged")
    ap.add_argument("--limit", type=int, default=0, help="stop after N sends (0 = no limit)")
    args = ap.parse_args()

    root = workspace_root()
    print("workspace : %s" % root)
    print("target    : %s  (%s)" % (mc.MANTLE_TARGET_NAME, mc.MANTLE_MCP_URL))

    if not mc.get_access_token():
        print("\n⛔ no access token for the active target. Nothing was sent.", file=sys.stderr)
        print("   Check: python ~/.claude/hooks/mantle_hook_health.py", file=sys.stderr)
        return 2

    files = discover(root, args.only)
    ledger = _load_ledger()

    todo: List[Tuple[Path, str, str]] = []
    unchanged = unreadable = 0
    total_bytes = 0
    for p in files:
        text = _read(p)
        if text is None:
            unreadable += 1
            continue
        identity = sf._identity(p)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not args.force and ledger.get(identity) == digest:
            unchanged += 1
            continue
        todo.append((p, identity, digest))
        total_bytes += len(text.encode("utf-8"))

    print("\nprose files found : %d" % len(files))
    print("  already current : %d" % unchanged)
    print("  unreadable      : %d" % unreadable)
    print("  TO SEND         : %d  (%.1f MB)" % (len(todo), total_bytes / 1e6))

    by_repo: Dict[str, int] = {}
    for p, _, _ in todo:
        rel = p.relative_to(root).as_posix()
        by_repo[rel.split("/")[0]] = by_repo.get(rel.split("/")[0], 0) + 1
    for repo, n in sorted(by_repo.items(), key=lambda x: -x[1]):
        print("      %5d  %s" % (n, repo))

    if not args.run:
        print("\n--report: nothing sent. Re-run with --run.")
        return 0
    if not todo:
        print("\nnothing to do.")
        return 0

    print("\nsending ...")
    sent = unconfirmed = failed = 0
    t_start = time.time()
    for i, (p, identity, digest) in enumerate(todo, 1):
        if args.limit and sent + unconfirmed >= args.limit:
            print("  --limit reached")
            break
        text = _read(p)
        if text is None:
            failed += 1
            continue
        rel = p.relative_to(root).as_posix()
        path_tag = "path-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        context = {"title": rel, "tags": ["claude-code", "file", path_tag, "workspace-import"],
                   "project": str(root), "file_path": str(p)}
        got = mc.store_artifact(
            identity=identity, content=text, name=rel,
            content_type=sf._content_type_for(p),
            description="Workspace document imported from %s" % rel,
            context=context)
        if got:
            sent += 1
            ledger[identity] = digest        # only a CONFIRMED write is recorded
        else:
            # Unknown, not failed. Deliberately NOT ledgered, so the next run retries it; the
            # shared `identity` makes that retry an update rather than a duplicate.
            unconfirmed += 1
        if i % 25 == 0 or i == len(todo):
            _save_ledger(ledger)
            rate = i / max(time.time() - t_start, 1e-9)
            print("  %4d/%d  sent=%d unconfirmed=%d  (%.1f/s)"
                  % (i, len(todo), sent, unconfirmed, rate))

    _save_ledger(ledger)
    print("\nsent %d · unconfirmed %d · failed %d · %.1fs"
          % (sent, unconfirmed, failed, time.time() - t_start))
    if unconfirmed:
        print("Unconfirmed writes are UNKNOWN, not lost - the server may well have stored them.")
        print("They are not ledgered, so re-running retries them safely.")
    print("\nVerify with a recall, not from here:")
    print("  python ~/.claude/hooks/mantle_hook_health.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
