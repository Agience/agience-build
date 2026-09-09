#!/usr/bin/env python3
"""PostToolUse hook (matcher: Write|Edit): keep mantle's copy of a file current.

One artifact per file -- not one per edit, and not one per lost reply. The file's resolved path
is the artifact's identity: it goes over the wire as `identity`, Mantle derives the id from it,
and every write of that path lands on that one artifact. A `recall` therefore answers with the
file's current content, never with a copy of some earlier draft that happened to score better.

There is no local id index, and its absence is the fix rather than a simplification: a local
path -> artifact-id map is a second source of truth about identity, and a second source of truth
fails the way they always do -- a write whose reply is lost still succeeds server-side, so the
entry is never recorded, and the next write of the same path creates a second root that nothing
reconciles. It also needs a lock around read -> create -> write, or two hook processes for one
file can both read "not tracked" and both create. Measured 2026-08-13: this repo's README.md
stored as two artifacts three minutes apart, the older and larger of which was the stale one.

Reads the file back off disk after the tool ran, rather than trusting `tool_input` -- Write's
input carries the full content but Edit's carries only the diff (old_string/new_string), so disk
is the one place both tools' input shapes agree on "the current content." Best-effort: any
failure (mantle down, file gone, too large, not text) is silent and exits 0 -- this must never
turn a successful edit into a visible error.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from mantle_common import log_event, read_stdin_json, store_artifact

_CONTENT_TYPE_BY_SUFFIX = {
    ".py": "text/x-python", ".md": "text/markdown", ".json": "application/json",
    ".js": "text/javascript", ".jsx": "text/javascript", ".ts": "text/typescript",
    ".tsx": "text/typescript", ".yaml": "application/yaml", ".yml": "application/yaml",
    ".toml": "application/toml", ".html": "text/html", ".css": "text/css",
    ".sh": "text/x-shellscript", ".sql": "application/sql",
}


#: Path fragments whose contents are ephemeral by construction. An OS temp file is written to be
#: thrown away; keeping it forever inverts the one thing its location was telling us.
#:
#: `_scratch` is deliberately NOT here. It reads like a temp directory and is not one -- it is a
#: working directory holding notes and write-ups meant to be kept, which is exactly the prose this
#: hook exists to capture. Machine-generated caches (`.git`, `node_modules`, `__pycache__`) stay
#: excluded because nothing in them was written by a person.
#:
#: `.claude` is excluded because it is the other store. Claude Code keeps a free, automatic,
#: local cross-session memory under `~/.claude/.../memory/`, and this repo's CLAUDE.md draws the
#: line in one sentence: "Don't write the same fact to both stores — that's the one place real
#: duplication happens." Capturing those files here writes every memory into BOTH lanes, which
#: is the duplication the rule exists to prevent — and it puts notes about how to work with
#: Claude into a corpus meant for engineering answers, where they compete with them. `MEMORY.md`
#: is the worst case: an index of one-line pointers, all signal-free, all matching everything.
#: Measured 2026-08-13 — three such artifacts had already landed.
#: Vendored dependency trees joined the list 2026-08-24, on the rule already stated above:
#: "nothing in them was written by a person". `node_modules` was the only one named, and it is not
#: the only one that exists.
#:
#: Measured that day by walking the workspace with this very function: `entroptics-mass-gap` offered
#: **9,874** files for capture, of which **9,658 were under `research/lean/.lake/packages`** — the
#: downloaded Mathlib and its siblings. 9,386 `.lean` files of third-party library source, plus
#: `.npy` binaries. That is 75% of every capturable file in the workspace, and none of it is this
#: workspace's information.
#:
#: This is not a judgment about content: none of it decides anything by looking at what a file
#: says, and a `.lean` file written here is still captured, at any length. What is excluded is a
#: tree that was downloaded rather than written — the same test `node_modules` already passed,
#: applied to the package directories of the other toolchains in this workspace.
#:
#: `build/` and `vendor/` are deliberately NOT here. `agience-mantle/build/` holds a real Dockerfile
#: and compose files, and chorus carries hand-written notes under a `vendor/` path. An exclusion is
#: only safe where the directory name means "downloaded" in every repo that has one.
_EPHEMERAL_MARKERS = ("\\temp\\", "/temp/", "\\tmp\\", "/tmp/", "\\scratchpad\\", "/scratchpad/",
                      "\\.git\\", "/.git/", "\\.claude\\", "/.claude/",
                      "\\node_modules\\", "/node_modules/", "\\__pycache__\\", "/__pycache__/",
                      "\\.lake\\packages\\", "/.lake/packages/",
                      "\\site-packages\\", "/site-packages/",
                      "\\.venv\\", "/.venv/", "\\dist\\", "/dist/",
                      "\\.pytest_cache\\", "/.pytest_cache/",
                      "\\.mypy_cache\\", "/.mypy_cache/", "\\.ruff_cache\\", "/.ruff_cache/")


def _should_capture(path: Path) -> bool:
    """Is this file worth keeping in the lattice at all?"""
    lowered = os.path.normcase(str(path))
    return not any(marker in lowered for marker in _EPHEMERAL_MARKERS)


def _content_type_for(path: Path) -> str:
    return _CONTENT_TYPE_BY_SUFFIX.get(path.suffix.lower(), "text/plain")


def _identity(path: Path) -> str:
    """The name this file is stored under: `file:` + its resolved absolute path, case-folded.

    Resolved and absolute because the same file reached from a different working directory --
    or through a symlink, or with different capitalisation on Windows -- has to produce one
    name, or the store ends up with two artifacts for one file, which is the whole failure.

    This travels to the server: it is the `identity` Mantle derives the artifact id from, so
    this string is what makes the write idempotent. Changing how it is computed re-points every
    file at a new artifact and orphans the old one -- the same break as renaming a primary key,
    and worth the same caution.

    The `file:` prefix keeps this caller's namespace tidy: identities are per-principal, so a
    file and a session cannot collide with each other by accident.
    """
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    return "file:" + os.path.normcase(str(resolved))


def main() -> int:
    payload = read_stdin_json()
    if payload.get("tool_name") not in ("Write", "Edit"):
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path:
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(cwd) / path

    if not _should_capture(path):
        log_event("store_file", outcome="skipped", path=str(path), reason="ephemeral")
        return 0

    try:
        # No size cap: a fixed byte limit here would skip anything larger on the theory that a
        # big file is probably generated. A cap is a guess about content made from its length, and
        # the one document it would silently drop is the long one nobody can reconstruct. A file
        # that is not text still fails the decode below, which is a measurement rather than a guess.
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    try:
        rel = str(path.relative_to(cwd))
    except ValueError:
        rel = str(path)

    identity = _identity(path)
    content_type = _content_type_for(path)
    # A tag that names the file, because the title cannot. `title` is the relative path, so
    # "README.md" is the title of a README in every repo on this machine — recovering identity from
    # it would let one project's write adopt another project's artifact. `file_path` in the context
    # is unambiguous but `recall` does not return context, so it cannot be searched on. Tags are
    # both filterable and returned in hits, so the identity goes there, hashed: the absolute path
    # of a source tree is not something to publish into a shared store as a searchable term.
    path_tag = "path-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    # `title` stays the readable relative label; `file_path` carries the absolute one, so an
    # artifact says both what to call it and which file on disk it mirrors.
    context = {"title": rel, "tags": ["claude-code", "file", path_tag], "project": cwd,
               "file_path": str(path)}
    description = f"File written by Claude Code in {cwd}"

    # One call, whether this file has been stored before or not. The server resolves `identity`
    # to an id and creates or updates accordingly, so there is no decision to make here, no
    # index to consult, and nothing a lost reply or a concurrent hook process can corrupt.
    stored = store_artifact(
        identity=identity, content=text, name=rel, content_type=content_type,
        description=description, context=context,
    )
    if stored:
        log_event("store_file", outcome="stored", path=rel, chars=len(text), id=stored)
    else:
        # Unknown rather than failed -- the write may well have landed. It needs no reconciling
        # either way: the next write of this path carries the same identity and lands on the
        # same artifact, so a missed reply costs one stale artifact until the next edit, never a
        # duplicate.
        log_event("store_file", outcome="unconfirmed", path=rel, chars=len(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
