#!/usr/bin/env python3
"""Move the hook's existing top-level artifacts into the Claude Code collection.

WHY. Mantle keys its encrypted index per ORIGIN ROOT, and a top-level artifact IS its own origin
root (`search/mantle/principal.resolve_cell_principal`). Every artifact these hooks stored was
therefore a separately keyed SSE owner, and a recall has to read every owner it is authorized
for — measured on 71/dev: 121 top-level artifacts, 4,520 file probes for a ten-term query. Filing
them in one collection gives them one shared root, so the read stops scaling with how much has
been stored.

Collections stay top-level, deliberately. A collection is an artifact like any other and it is
its own root — that is what a root IS. This pass skips them, and skips anything whose identity it
cannot reconstruct, rather than guessing.

DELETE-THEN-CREATE, in that order, and it is not the safe-looking one. The old top-level
artifact's id EQUALS the derived identity id, and a member created for the same identity carries
that same value as its ROOT. Both alive at once means two rows sharing a root — and both search
arms key on root_id, so they would collide in the index. The transient risk is a window where the
artifact is in neither place; the content is read into memory first, and every kind this migrates
is re-derivable from disk anyway (a file from the filesystem, a commit from git, a transcript from
its session log). A permanent index collision is worse than a momentary gap.

    python migrate_to_container.py --dry-run
    python migrate_to_container.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mantle_common import (  # noqa: E402
    _artifact_id_of, _claude_code_container, mcp_call,
)

_COLLECTION_CONTENT_TYPE = "application/vnd.agience.collection+json"


def identity_for(artifact: dict) -> Optional[str]:
    """The identity string this artifact was stored under, or None if it cannot be rebuilt.

    Each branch mirrors the hook that writes it — `store_file._identity`, `capture_commits`,
    `archive_transcript` — because the identity has to come out IDENTICAL. A near-miss does not
    move the artifact, it mints a second one under a name nothing will ever write again.
    """
    try:
        ctx = json.loads(artifact.get("context") or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(ctx, dict):
        return None
    if artifact.get("content_type") == _COLLECTION_CONTENT_TYPE:
        return None                      # a collection is its own root — leave it top-level
    if ctx.get("file_path"):
        return "file:" + os.path.normcase(str(ctx["file_path"]))
    if ctx.get("repo") and ctx.get("sha"):
        return "commit:%s:%s" % (ctx["repo"], ctx["sha"])
    if ctx.get("session_id"):
        return "session:%s" % ctx["session_id"]
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    container = _claude_code_container()
    if not container:
        print("could not resolve the Claude Code collection; nothing done")
        return 1
    print("collection: %s" % container)

    listing = mcp_call("list_artifacts", {"limit": 2000}) or {}
    rows = listing.get("result") if isinstance(listing.get("result"), list) else []
    if not rows:
        rows = listing.get("artifacts") or []
    top = [a for a in rows if not a.get("collection_id")]
    print("top-level artifacts: %d" % len(top))

    movable, skipped = [], []
    for a in top:
        ident = identity_for(a)
        (movable if ident else skipped).append((a, ident))
    print("movable: %d   skipped: %d" % (len(movable), len(skipped)))

    if args.dry_run:
        for a, ident in movable[:8]:
            print("  would move %s  <- %s" % (a["id"][:8], ident[:64]))
        if len(movable) > 8:
            print("  ... and %d more" % (len(movable) - 8))
        for a, _ in skipped:
            print("  SKIP %s  %s  (%s)" % (
                a["id"][:8], (a.get("name") or "?")[:40], a.get("content_type") or "?"))
        return 0

    moved = failed = 0
    for i, (a, ident) in enumerate(movable, 1):
        content = a.get("content") or ""
        payload = {
            "identity": ident,
            "container_id": container,
            "content": content,
            "content_type": a.get("content_type") or "text/plain",
            "name": a.get("name") or "",
            "description": a.get("description") or "",
        }
        if a.get("context"):
            payload["context"] = a["context"]

        # Read first (above), then remove, then recreate — see the module docstring on ordering.
        if mcp_call("delete_artifact", {"artifact_id": a["id"]}) is None:
            print("  ! could not delete %s; leaving it alone" % a["id"][:8])
            failed += 1
            continue
        if _artifact_id_of(mcp_call("create_artifact", payload)):
            moved += 1
        else:
            failed += 1
            print("  ! RECREATE FAILED for %s (%s) — re-run the capture hook for it"
                  % (a["id"][:8], ident[:60]))
        if i % 25 == 0:
            print("  %d/%d (moved=%d failed=%d)" % (i, len(movable), moved, failed))

    print("moved %d, failed %d, skipped %d" % (moved, failed, len(skipped)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
