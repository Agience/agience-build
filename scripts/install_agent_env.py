r"""Install the workspace's agent tooling into the places assistants actually read.

    python agience-build/scripts/install_agent_env.py            # --check (default): report drift
    python agience-build/scripts/install_agent_env.py --install   # copy sources into ~/.claude
    python agience-build/scripts/install_agent_env.py --adopt     # pull ~/.claude/hooks INTO the repo

## Why this exists

Skills and hooks are read from `~/.claude/`, which is **outside every repo**. A home directory is
not version-controlled, not pushed, not reviewed and not restorable — so the workspace's own agent
tooling was the one piece of configuration the fleet could not rebuild.

Measured 2026-08-24: `~/.claude/hooks/` held four shared files; `agience-build/.claude/hooks/` and
`agience-mantle/.claude/hooks/` each held a different version of the same four; all six pairwise
diffs were non-empty; and `.claude/` is in `.gitignore` for four repos and tracked by none. The copy
that ran was recoverable from nowhere.

The rule that fixes it: **configuration that describes the workspace lives in a repo that is
pushed.** Sources here, installed outward — never edited in place at the destination.

## What it manages

    agience-build/skills/<name>/SKILL.md   ->   ~/.claude/skills/<name>/SKILL.md
    agience-build/hooks/*.py               ->   ~/.claude/hooks/*.py        (once adopted)

`--check` is the default and reports three states per file: **same**, **drifted** (destination
differs from source), **missing**. It writes nothing, so it is safe to wire into a suite.

**`--adopt` copies the LIVE hooks into the repo, making the running copy the source.** That is the
right direction exactly once — when bringing an existing installation under version control — and
the wrong direction afterwards, because it would overwrite reviewed sources with whatever is on this
box. It refuses if the repo already has hook sources, unless `--force`.
"""
from __future__ import annotations

import argparse
import filecmp
import pathlib
import shutil
import sys
from typing import List, Tuple

HOME_CLAUDE = pathlib.Path.home() / ".claude"
#: (source subdir under agience-build, destination under ~/.claude, glob)
MANAGED: Tuple[Tuple[str, str, str], ...] = (
    ("skills", "skills", "*/SKILL.md"),
    ("hooks", "hooks", "*.py"),
)


def build_root() -> pathlib.Path:
    """`agience-build`, from this file's own location."""
    return pathlib.Path(__file__).resolve().parents[1]


def _pairs(root: pathlib.Path) -> List[Tuple[pathlib.Path, pathlib.Path, str]]:
    out: List[Tuple[pathlib.Path, pathlib.Path, str]] = []
    for src_dir, dst_dir, pattern in MANAGED:
        base = root / src_dir
        if not base.is_dir():
            continue
        for src in sorted(base.glob(pattern)):
            rel = src.relative_to(base)
            out.append((src, HOME_CLAUDE / dst_dir / rel, f"{dst_dir}/{rel.as_posix()}"))
    return out


def _state(src: pathlib.Path, dst: pathlib.Path) -> str:
    if not dst.exists():
        return "missing"
    # shallow=False: compare CONTENT. A shallow compare uses size and mtime, and a copied file has
    # a fresh mtime with identical bytes, which reads as drifted on every run.
    return "same" if filecmp.cmp(src, dst, shallow=False) else "drifted"


def check(root: pathlib.Path) -> int:
    pairs = _pairs(root)
    if not pairs:
        print("no managed sources under %s" % root)
        print("  (expected agience-build/skills/*/SKILL.md — and hooks/ once adopted)")
        return 1
    worst = 0
    print("managed agent environment — source: %s\n" % root)
    for src, dst, label in pairs:
        st = _state(src, dst)
        mark = {"same": "✅", "drifted": "⚠ ", "missing": "⛔"}[st]
        print("  %s %-40s %s" % (mark, label, st))
        worst = max(worst, {"same": 0, "drifted": 1, "missing": 1}[st])
    if worst:
        print("\nRun with --install to copy sources into %s" % HOME_CLAUDE)
        print("A DRIFTED file means the live copy was edited in place. Check what the destination")
        print("holds before overwriting it — --install discards it.")
    else:
        print("\n✅ everything installed matches its source in the repo")
    return worst


def install(root: pathlib.Path) -> int:
    n = 0
    for src, dst, label in _pairs(root):
        if _state(src, dst) == "same":
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print("  installed %s" % label)
        n += 1
    print("  %d file(s) installed" % n if n else "  everything already current")
    return 0


def adopt(root: pathlib.Path, force: bool) -> int:
    """Bring the LIVE hooks under version control, once."""
    dest = root / "hooks"
    live = HOME_CLAUDE / "hooks"
    if not live.is_dir():
        print("no %s to adopt" % live, file=sys.stderr)
        return 2
    existing = sorted(dest.glob("*.py")) if dest.is_dir() else []
    if existing and not force:
        print("REFUSING: %s already holds %d source file(s)." % (dest, len(existing)))
        print("  Adopting again would overwrite reviewed sources with this box's live copies.")
        print("  Use --install to push the repo's sources OUT, or --adopt --force if you really")
        print("  mean to replace them.")
        return 3
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted(live.glob("*.py")):
        shutil.copy2(src, dest / src.name)
        print("  adopted hooks/%s" % src.name)
        n += 1
    print("\n%d file(s) adopted into %s" % (n, dest))
    print("⚠ `.claude/` is gitignored in this repo but `hooks/` is not — check `git status`,")
    print("  then commit. Until it is committed the fleet still cannot restore these.")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--adopt", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    root = build_root()
    if args.adopt:
        return adopt(root, args.force)
    if args.install:
        return install(root)
    return check(root)


if __name__ == "__main__":
    raise SystemExit(main())
