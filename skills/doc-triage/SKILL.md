---
name: doc-triage
description: Decide WHERE documents and working code live across the agience workspace - promote to pharos, park in _scratch/CURRENT, bench code in _scratch/lab, or set down in _archive. Use when documents have accumulated in a repo or in _scratch, when asked to tidy or triage docs, or after a restructure. Placement only; it rewrites no prose.
---

# Doc triage — where a document lives

Documents move in **one direction**, and nothing is deleted:

```
      a repo  ──┐
                ├──▶  _scratch  ──┬──▶  agience-pharos      the published, public corpus
    a session ──┘                 ├──▶  _scratch/CURRENT    still open
                                  └──▶  _archive            set down, dated, never deleted
```

**This pass decides placement only.** Change no code and rewrite no prose. Its companion,
`doc-current-state`, rewrites a document's prose — and pharos is published and public, so it takes finished
prose. **Run the prose pass BEFORE promoting, never after.**

## The two lanes

Prose and code have the same lifecycle and different destinations. A pass that moves one without
the other leaves a document citing scripts that are no longer beside it.

| stage | prose | code |
|---|---|---|
| **born** | a repo, or a session | `_scratch/lab/<thread>/` |
| **live** | `_scratch/CURRENT/<THREAD>.md` — flat, `.md` only | `_scratch/lab/<thread>/` — same name |
| **finished** | → `agience-pharos/<tree>/` | → the repo it acts on, `scripts/` or `experiments/`, **with a test** |
| **set down** | → `_archive/<YYYY-MM-DD>-<reason>/` + manifest | → same |

## Six rules

1. **`CURRENT/` is `.md` only.** The directory listing is the index; `README.md` is the annotation.
2. **One thread = one document**, and optionally one `lab/` subdirectory of the same name.
3. **Nothing is deleted.** Archiving is a recorded move.
4. **Every promotion updates the destination tree's `README.md` index.** That index is what makes a
   document reachable; a promoted file nothing links to is a file nobody finds.
5. **Prose pass before promotion**, never after.
6. **Generated data is never tracked; pinned fixtures always are.** The test is: *does regenerating
   it destroy its purpose?* No → it is output, gitignore it. Yes → it is a fixture, track it.
   A bench whose questions are pinned so a comparison spans a corpus change is the second kind, and
   regenerating it silently destroys the comparison.

## Scope

Default to the whole workspace. Given a target, sweep that tree only.

The **workspace root** is the directory holding `_scratch` and `_archive`. Every sibling directory
with a `.git` is a repo in scope — plus `agience-prism/{py,js,c}`, which are three repos inside a
plain directory. **Discover them; do not assume a list.**

`_scratch` and `_archive` are `FLEET_NO_GITHUB` — NAS-only by decision. **Archiving takes a document
off GitHub.** Say so in the report; it is a consequence people do not expect.

## Stage 1 — pull prose out of the repos

Sweep `*.md` under each repo, excluding `.git/`, `.pytest_cache/`, `dist/`, `build/`, `vendor/`,
`node_modules/`, `.venv/`, `site-packages/`, `bin/`, `obj/`.

**Stays in the repo** — a reader of the code needs it there:

- `README.md` at any level, including per-package.
- Licence and governance: `LICENSE`, `CLA`, `COMMERCIAL_LICENSE`, `PATENTS`, `PLEDGE`,
  `CONTRIBUTING`, `.github/*`.
- Operational records bound to a specific machine or deploy — inventories, runbooks, backup and
  cutover notes, key custody. These describe one host and are read next to the thing they operate.
- Generated or mechanical tables that a script rewrites.

**Stages to `_scratch`** — prose about the system rather than about running this repo:

- Design notes, architecture arguments, plans, proposals, RFCs.
- Handovers, session state, working notes, post-mortems, review write-ups.
- Measurement and bench reports, findings, evaluations.
- Anything with a date in the name or the body that reads as a snapshot.
- A `README.md` that has grown into a design document: leave a short orientation README behind and
  stage the design half under a new name.

`git mv` where both trees are git repos; plain `mv` otherwise. Preserve the filename unless it
collides, in which case prefix it with the source repo's name.

## Stage 2 — triage `_scratch`

`*.md` at the `_scratch` root and inside `CURRENT/`. `_scratch/lab/` has the code lifecycle above —
triage it in the same pass, but by thread rather than by file.

`CURRENT/` is **re-triaged every run**, never skipped: a thread that has since closed leaves it.

Read each document. Classify it as exactly one of:

- **PROMOTE** — true today, and someone outside this session needs it.
- **IN-PROGRESS** — a live thread, not finished. Stays in `CURRENT/`. **Name what it is waiting on.**
- **ARCHIVE** — superseded (name the successor), completed and recorded elsewhere, a dated snapshot
  whose conclusion has been absorbed, or a plan that was abandoned.

Judge on content, not age. A note from three weeks ago that still states the governing rule is
PROMOTE; a report from yesterday whose numbers were replaced this morning is ARCHIVE.

### How to decide

1. **Is it true?** If it describes a state that no longer exists it is a candidate for `_archive` or
   for a superseded banner — not for promotion. Check against the tree, not against other documents.
2. **Who is its reader?** A reader of one repo → that repo. Someone deciding whether to trust the
   system → pharos. Nobody, yet → `CURRENT/`.
3. **Does it have a finish line?** Live work with one stays in `CURRENT/`. Work whose finish line has
   passed is promoted or archived.
4. **Is it a duplicate?** Two documents on one subject is the thing this pass exists to end. Name
   which survives and why; the other gets a superseded banner and moves to `_archive`.

Do not promote a document that merely repeats what a pharos document already says — fold the delta
into the existing document and archive the source.

**A document written to advise a decision closes when the decision lands.** Check whether it landed
before calling the thread open: read the code, not the document's own expectation.

## Stage 3 — placement

**PROMOTE → `agience-pharos/<section>/`**:

Pharos has six trees, and every one of them is written for a reader **outside the company**:

| section | takes |
|---|---|
| `start/` | the three ways in — the headline, the narrative, the complete picture. Nothing else belongs here |
| `learn/` | the Entroptics course |
| `features/` | capability that works today, capability by capability |
| `design/` | how the system that exists is built — the specification, the components, the vocabulary |
| `research/` | the papers and the measurements behind the claims |
| `vision/` | what is intended and **not yet built** |

**The `design/` ÷ `vision/` line is the one that matters.** `design/README.md` opens by saying it
describes the system that exists. Anything not built, not GA, or not working yet belongs in
`vision/` regardless of how finished its design is — a device fleet, a transport hardening plan, a
roadmap. Putting unbuilt work in `design/` is how a corpus starts claiming hardware it does not have.

There is no `working/` tree. A document with no finish line either states something durable, in
which case it is promoted, or it stays in `_scratch`.

A promoted document declares its own status in its own first screen, and gets a row in its tree's
`README.md`. **It carries no provenance banner**: pharos is read by people outside the company, and
"promoted from `_scratch/CURRENT` by the 2026-09-09 pass" is internal bookkeeping addressed to
nobody they are. Where a document describes something unbuilt, it says so plainly in its own opening
words instead.

**IN-PROGRESS → `_scratch/CURRENT/`.** One flat directory, no dating, no per-topic subdirectories —
a worklist, not an archive. `README.md` lists each document and its open thread in one line,
**rewritten each run so the list matches the directory**. An index that covers some of the directory
is worse than none: it reads as complete.

**ARCHIVE → `_archive/<YYYY-MM-DD>-<reason>/`** with a `README.md` listing each file, its origin
path, and one line on why it was set down, **naming the successor where there is one**.

## Procedure

1. **Inventory first.** Every candidate with its path, size and mtime. Move nothing yet.
2. **Report the proposed classification as one table** — path, verdict, destination, one-line
   reason. For each IN-PROGRESS name the open thread. Flag anything you could not judge as
   UNKNOWN-VALUE rather than guessing.
3. **Wait for approval on the table.**
4. **Execute.** `git mv` inside a repo; `git rm --cached` + copy across repos, so history stays
   where it was written.
5. **Update** the destination tree's `README.md`, `CURRENT/README.md`, and the new
   `_archive/<dated>/README.md`.
6. **Fix inbound links.** Grep the workspace for every moved filename and repoint what you find.
   Report any left verbatim — dated records of a completed migration are left as-is by convention,
   and repointing a reference inside code is a code change, which this pass does not make.
7. **Report.** Counts per verdict, what moved where, links repointed, anything left UNKNOWN-VALUE.

**Do not commit or push.** Leave the working trees staged and say what is ready to commit in each.

## Report before moving

List every proposed move as `from → to`, with the one-line reason and the state you are assigning.
**Get agreement before writing.** A wrong promotion publishes a false statement to the public, and
pharos is what everything else is checked against.
