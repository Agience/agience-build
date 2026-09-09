#!/usr/bin/env python3
"""Make the three ways concurrent agents corrupt this workspace hard to do by accident.

    python scripts/fleet_guard.py status              every repo: dirty, staged, drift
    python scripts/fleet_guard.py preflight <repo>    is it safe to commit or push here now?
    python scripts/fleet_guard.py release             publish order, derived from declared deps

Several agents share one checkout of every repo. Nothing serialises them, so the working tree a
command reads is not necessarily the one it was reasoning about a minute earlier. Three failures
follow from that, and each is silent:

**Staging everything takes someone else's work.** `git add -A` stages whatever is in the tree,
including a half-finished edit another agent has not committed. The commit lands under a message
that does not describe it, and both agents' histories are wrong. `preflight` counts what is dirty
and refuses to call a tree safe while anything is uncommitted, so the check happens before the
commit rather than after.

**A remote moves between reading it and writing it.** An agent that read `main`, worked, then
pushed can overwrite a commit that landed in between. `status` compares each local remote-tracking
ref against the remote's actual tip, and `preflight` prints the exact `--force-with-lease` spec for
the sha it just observed: a lease turns that overwrite into a refusal.

**A branch maintained by replay drifts from the branch it mirrors.** Cherry-picking commits onto a
second branch one at a time misses any commit that lands between picks, and the divergence shows up
as a tree difference nobody looks at. `preflight` compares the trees of paired branches and says
which paths differ.

Reading a remote costs a network round trip, so `status` reads only remotes it can reach quickly
and reports the ones it could not rather than blocking on them.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import sys
import tomllib
from pathlib import Path

#: The workspace root: repos are siblings of `agience-build`, never children of it.
ROOT = Path(__file__).resolve().parents[2]

#: Trees, not products. They carry no distribution and are never part of a release order.
NON_PRODUCT = {"_scratch", "_archive", "_fleet"}


def _git(repo: Path, *args: str, timeout: float = 20.0, strip: bool = True) -> str:
    """`git -C repo args...`, stdout decoded. Empty string on any failure.

    Swallows failure because every caller is reporting on a repo it does not control: a remote that
    is unreachable, a branch that does not exist, and a repo mid-rebase are all states this tool
    describes rather than fails on.

    `strip=False` for output whose leading whitespace carries meaning. `git status --porcelain`
    puts the worktree status in column two, so an unstaged change begins with a space; stripping it
    shifts every column left and takes the first character of the path with it.
    """
    try:
        p = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, timeout=timeout)
        if p.returncode != 0:
            return ""
        out = p.stdout.decode("utf-8", "replace")
        return out.strip() if strip else out
    except (subprocess.TimeoutExpired, OSError):
        return ""


def repos() -> list[Path]:
    """Every git repo in the workspace, including one nested a level down.

    `agience-prism` holds its repo at `py/`, so a scan of the root's immediate children misses it.
    Rather than name that exception, this descends one level wherever the parent is not itself a
    repo — which finds it by shape.
    """
    found: list[Path] = []
    for child in sorted(ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / ".git").exists():
            found.append(child)
            continue
        for grand in sorted(child.iterdir()):
            if grand.is_dir() and (grand / ".git").exists():
                found.append(grand)
    return found


def name_of(repo: Path) -> str:
    """A short label for a repo. Its path under the workspace, or its own path when outside one.

    `preflight` accepts a path so it reaches a worktree or clone that is not a workspace member,
    and a repo outside the root has no relative name to print.
    """
    try:
        return str(repo.relative_to(ROOT)).replace(os.sep, "/")
    except ValueError:
        return str(repo)


# ── what the tree and the remotes actually say ───────────────────────────────────────────────

def dirty_paths(repo: Path) -> list[str]:
    """Every path git reports as changed, staged or not. `XY PATH`, so the path starts at column 3.

    A rename reads `R  old -> new`; the new name is what a later command would act on, so that is
    what is reported.
    """
    out = _git(repo, "status", "--porcelain", strip=False)
    paths = []
    for ln in out.splitlines():
        if len(ln) <= 3:
            continue
        p = ln[3:]
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        paths.append(p)
    return paths


def staged_paths(repo: Path) -> list[str]:
    out = _git(repo, "diff", "--cached", "--name-only")
    return [ln for ln in out.splitlines() if ln.strip()] if out else []


def branch_of(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "?"


def remotes_of(repo: Path) -> list[str]:
    out = _git(repo, "remote")
    return [ln.strip() for ln in out.splitlines() if ln.strip()] if out else []


def remote_tip(repo: Path, remote: str, branch: str) -> str | None:
    """The remote's real tip for `branch`, read now. `None` when the remote cannot be reached.

    `ls-remote` rather than the remote-tracking ref, because the tracking ref is a memory of the
    last fetch and the whole question here is whether it has gone stale.
    """
    out = _git(repo, "ls-remote", remote, f"refs/heads/{branch}", timeout=25.0)
    if not out:
        return None
    return out.split()[0]


def local_tip(repo: Path, branch: str) -> str | None:
    return _git(repo, "rev-parse", branch) or None


def tree_of(repo: Path, ref: str) -> str | None:
    return _git(repo, "rev-parse", f"{ref}^{{tree}}") or None


def _survey(repo: Path) -> dict:
    branch = branch_of(repo)
    local = local_tip(repo, branch)
    drift: dict[str, str] = {}
    for remote in remotes_of(repo):
        tip = remote_tip(repo, remote, branch)
        if tip is None:
            drift[remote] = "unreachable"
        elif local and tip != local:
            ahead = _git(repo, "rev-list", "--count", f"{tip}..{local}") or "?"
            behind = _git(repo, "rev-list", "--count", f"{local}..{tip}") or "?"
            drift[remote] = f"+{ahead}/-{behind}"
    return {
        "repo": name_of(repo),
        "branch": branch,
        "dirty": len(dirty_paths(repo)),
        "staged": len(staged_paths(repo)),
        "drift": drift,
    }


def cmd_status(args) -> int:
    """Every repo at once: what is uncommitted, what is staged, and where a remote has moved."""
    rs = repos()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(_survey, rs))

    print(f"{'repo':<24} {'branch':<14} {'dirty':>5} {'staged':>6}  remotes")
    print("-" * 78)
    unsafe = 0
    for r in rows:
        marks = []
        for remote, state in sorted(r["drift"].items()):
            marks.append(f"{remote}:{state}")
        flag = ""
        if r["dirty"]:
            flag = "  <- uncommitted work here; do not stage everything"
            unsafe += 1
        print(f"{r['repo']:<24} {r['branch']:<14} {r['dirty']:>5} {r['staged']:>6}  "
              f"{', '.join(marks) if marks else 'in step'}{flag}")

    moved = [r for r in rows if any(v not in ("unreachable",) for v in r["drift"].values())]
    print()
    print(f"{len(rows)} repos, {unsafe} with uncommitted work, {len(moved)} whose remote differs "
          f"from the local branch")
    if unsafe:
        print("A repo with uncommitted work may be holding another agent's edit. Stage the paths "
              "you changed by name.")
    return 0


def cmd_preflight(args) -> int:
    """Whether it is safe to commit or push in one repo, and the lease to push with."""
    target = args.repo.rstrip("/").replace(os.sep, "/")
    match = [r for r in repos() if name_of(r) == target or r.name == target]
    if match:
        repo = match[0]
    else:
        # A path, so the check also reaches a worktree or clone outside the workspace root —
        # which is where an agent working in isolation actually sits.
        cand = Path(args.repo).expanduser().resolve()
        if (cand / ".git").exists():
            repo = cand
        else:
            print(f"no repo named {target!r} under {ROOT}, and {cand} is not a git repo",
                  file=sys.stderr)
            return 2
    branch = args.branch or branch_of(repo)
    problems = 0

    print(f"repo   {name_of(repo)}")
    print(f"branch {branch}")
    print()

    dirty = dirty_paths(repo)
    if dirty:
        problems += 1
        print(f"UNCOMMITTED  {len(dirty)} path(s) in the tree:")
        for p in dirty[:12]:
            print(f"    {p}")
        if len(dirty) > 12:
            print(f"    ... and {len(dirty) - 12} more")
        print("    Any of these may be another agent's. Stage by path; never `git add -A`.")
    else:
        print("clean        nothing uncommitted")

    local = local_tip(repo, branch)
    for remote in remotes_of(repo):
        tip = remote_tip(repo, remote, branch)
        if tip is None:
            print(f"{remote:<12} unreachable — cannot verify before pushing")
            problems += 1
            continue
        if tip == local:
            print(f"{remote:<12} in step ({tip[:8]})")
            continue
        problems += 1
        # Counting needs both commits present here. The remote's tip is absent until something
        # fetches it, which is exactly the state an agent is in when it is about to overwrite —
        # so say that rather than printing an empty count.
        have_tip = bool(_git(repo, "cat-file", "-e", f"{tip}^{{commit}}") or
                        _git(repo, "cat-file", "-t", tip))
        if have_tip and local:
            ahead = _git(repo, "rev-list", "--count", f"{tip}..{local}") or "?"
            behind = _git(repo, "rev-list", "--count", f"{local}..{tip}") or "?"
            span = f" (+{ahead}/-{behind})"
        else:
            span = "  - its tip is not in this clone; fetch before comparing"
        print(f"{remote:<12} MOVED: remote {tip[:8]}, local {(local or '?')[:8]}{span}")
        print(f"    push with: --force-with-lease=refs/heads/{branch}:{tip}")

    # paired branches maintained by replay drift silently; compare the trees, not the commits
    for other in (args.compare or []):
        a, b = tree_of(repo, branch), tree_of(repo, other)
        if a is None or b is None:
            print(f"compare      {other}: missing")
            continue
        if a == b:
            print(f"compare      {other}: same tree")
        else:
            problems += 1
            diff = _git(repo, "diff", "--name-only", branch, other)
            paths = [p for p in diff.splitlines() if p.strip()]
            print(f"compare      {other}: TREES DIFFER in {len(paths)} path(s)")
            for p in paths[:8]:
                print(f"    {p}")

    print()
    print("safe to commit and push" if not problems
          else f"{problems} thing(s) to resolve before committing or pushing")
    return 1 if problems else 0


# ── release order, derived rather than typed ─────────────────────────────────────────────────

def _distribution(repo: Path) -> tuple[str | None, list[str]]:
    """`(distribution name, sibling distributions it requires)` from a repo's pyproject.

    Names are read from the file rather than assumed from the directory: at least one repo here
    publishes under a name that is not its directory's, and mantle declared a dependency on a
    distribution that does not exist because the two were conflated.
    """
    pp = repo / "pyproject.toml"
    if not pp.is_file():
        return None, []
    try:
        with pp.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return None, []
    project = data.get("project") or {}
    name = project.get("name")
    reqs: list[str] = list(project.get("dependencies") or [])
    for extra in (project.get("optional-dependencies") or {}).values():
        reqs.extend(extra)
    deps = []
    for r in reqs:
        head = r.split(";")[0].strip()
        for sep in ("[", ">", "<", "=", "!", "~", " "):
            head = head.split(sep)[0]
        head = head.strip()
        if head.startswith("agience-") and head != name:
            deps.append(head)
    return name, sorted(set(deps))


def cmd_release(args) -> int:
    """Publish order: a distribution ships after everything it declares."""
    dists: dict[str, dict] = {}
    for repo in repos():
        if repo.name in NON_PRODUCT:
            continue
        name, deps = _distribution(repo)
        if not name:
            continue
        dists[name] = {"repo": name_of(repo), "deps": deps, "path": repo}

    known = set(dists)
    ordered: list[str] = []
    remaining = dict(dists)
    while remaining:
        ready = sorted(n for n, d in remaining.items()
                       if not (set(d["deps"]) & known & set(remaining)))
        if not ready:            # a cycle: report it rather than ordering arbitrarily
            print("dependency cycle among: " + ", ".join(sorted(remaining)), file=sys.stderr)
            ready = sorted(remaining)
        for n in ready:
            ordered.append(n)
            remaining.pop(n)

    print(f"{'#':<3} {'distribution':<24} {'repo':<22} requires")
    print("-" * 78)
    for i, n in enumerate(ordered, 1):
        d = dists[n]
        inside = [x for x in d["deps"] if x in known]
        print(f"{i:<3} {n:<24} {d['repo']:<22} {', '.join(inside) if inside else '-'}")
    print()
    print("Ship in this order. A distribution published before something it declares leaves that "
          "requirement unresolvable for anyone installing it.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fleet_guard.py",
        description="Concurrency and release checks across the workspace.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="every repo: dirty, staged, remote drift").set_defaults(
        func=cmd_status)

    p = sub.add_parser("preflight", help="is it safe to commit or push in one repo?")
    p.add_argument("repo")
    p.add_argument("--branch", default=None, help="branch to check (default: checked out)")
    p.add_argument("--compare", action="append",
                   help="another branch whose tree should match; repeatable")
    p.set_defaults(func=cmd_preflight)

    sub.add_parser("release", help="publish order derived from declared dependencies").set_defaults(
        func=cmd_release)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
