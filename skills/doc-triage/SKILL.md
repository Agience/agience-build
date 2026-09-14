---
name: doc-triage
description: Decide WHERE documents and working code live across a multi-repo workspace - promote finished prose to the published corpus, park open threads in _scratch/CURRENT, bench code in _scratch/lab, set the rest down in _archive. Use when documents have accumulated in a repo or in _scratch, when asked to tidy or clean up the working floor, or after a restructure. Placement only; it rewrites no prose.
---

# Doc triage — where a document lives

Documents move in **one direction**, and nothing is deleted:

```
      a repo  ──┐
                ├──▶  _scratch  ──┬──▶  the published corpus   finished, external-facing
    a session ──┘                 ├──▶  _scratch/CURRENT       still open
                                  └──▶  _archive               set down, dated, never deleted
```

`_scratch` is a staging floor, not a store. Anything that has stopped moving has left it: forward to
the corpus if it is true and someone outside this session needs it, sideways to `_archive` if it is
not. What remains in `CURRENT/` is the open worklist and nothing else — that is the whole point of
the pass.

**This pass decides placement only.** Change no code and rewrite no prose. Its companion,
`doc-current-state`, rewrites a document's prose — and the published corpus is public, so it takes
finished prose. **Run the prose pass BEFORE promoting, never after.**

## The two lanes

Prose and code have the same lifecycle and different destinations. A pass that moves one without the
other leaves a document citing scripts that are no longer beside it.

| stage | prose | code |
|---|---|---|
| **born** | a repo, or a session | `_scratch/lab/<thread>/` |
| **live** | `_scratch/CURRENT/<THREAD>.md` — flat, `.md` only | `_scratch/lab/<thread>/` — same name |
| **finished** | → the published corpus | → the repo it acts on, **with a test** |
| **set down** | → `_archive/<YYYY-MM-DD>-<reason>/` + manifest | → same |

## Six rules

1. **`CURRENT/` is flat and `.md` only.** The directory listing is the index; its `README.md` is the
   annotation. A subdirectory there is how a worklist turns into an archive.
2. **One thread = one document**, and optionally one `lab/` subdirectory of the same name.
3. **Nothing is deleted.** Archiving is a recorded move.
4. **Every promotion updates the destination tree's index.** That index is what makes a document
   reachable; a promoted file nothing links to is a file nobody finds.
5. **Prose pass before promotion**, never after.
6. **Generated data is never tracked; pinned fixtures always are.** The test is: *does regenerating
   it destroy its purpose?* No → it is output, gitignore it. Yes → it is a fixture, track it. A
   bench whose questions are pinned so a comparison spans a corpus change is the second kind, and
   regenerating it silently destroys the comparison.

## Scope — discover it, never assume it

Default to the whole workspace. Given a target, sweep that tree only.

The **workspace root** is the directory holding `_scratch` and `_archive`. Everything else is
discovered from disk on the day you run:

- **A repo is any directory containing `.git`.** Search for them; do not work from a remembered list
  and do not assume they are all direct children of the root. Some products ship as several repos
  nested inside one plain directory.
- **The published corpus** is the repo the workspace treats as its public, external-facing prose.
  Read its own README and top-level index to learn its sections and what each is for. Its shape
  changes; the pass reads it each run rather than carrying a copy.
- **Skip vendored, generated and build trees** — dependency directories, caches, compiled output,
  virtual environments — and anything the repo's own ignore file already excludes.
- **Check the destination's remotes before describing what a move does.** Some trees in a workspace
  are deliberately local or NAS-only, so moving a document there takes it off its host. That is a
  consequence people do not expect; say it in the report, having checked rather than assumed it.

## Stage 1 — pull prose out of the repos

Sweep the Markdown under each discovered repo.

**Stays in the repo** — the test is *does a reader of this code need it here?*

- The orientation a reader of the tree opens first, at any level.
- Licence, governance and contribution files, and the host's own metadata directory.
- Operational records bound to one machine or one deploy — inventories, runbooks, cutover and
  backup notes, key custody. These describe a specific host and are read next to it.
- Tables a script regenerates.

**Stages to `_scratch`** — prose about the system rather than about running this repo:

- Design notes, architecture arguments, plans, proposals.
- Handovers, session state, working notes, post-mortems, review write-ups.
- Measurement and bench reports, findings, evaluations.
- Anything with a date in the name or the body that reads as a snapshot.
- An orientation file that has grown into a design document: leave a short orientation behind and
  stage the design half under a new name.

`git mv` where both trees are git repos; plain `mv` otherwise. Preserve the filename unless it
collides, in which case prefix it with the source repo's name.

## Stage 2 — triage `_scratch`

Three surfaces, every run:

- **The `_scratch` root.** Loose documents there have no lane. Each one is promoted, moved into
  `CURRENT/` as an open thread, or archived — nothing is left at the root because it was awkward.
- **`CURRENT/`.** Re-triaged every run, never skipped: a thread that has since closed leaves.
- **`lab/`.** The code lifecycle above, triaged by thread rather than by file.

Read each document. Classify it as exactly one of:

- **PROMOTE** — true today, and someone outside this session needs it.
- **IN-PROGRESS** — a live thread, not finished. Stays in `CURRENT/`. **Name what it is waiting on.**
  A document you cannot name an open thread for is not in progress; it is one of the other two.
- **ARCHIVE** — superseded (name the successor), completed and recorded elsewhere, a dated snapshot
  whose conclusion has been absorbed, or a plan that was abandoned.

Judge on content, not age. A note from three weeks ago that still states the governing rule is
PROMOTE; a report from yesterday whose numbers were replaced this morning is ARCHIVE.

### How to decide

1. **Is it true?** If it describes a state that no longer exists it is a candidate for `_archive`,
   not for promotion. Check against the tree, not against other documents.
2. **Who is its reader?** A reader of one repo → that repo. Someone outside the company deciding
   whether to trust the system → the corpus. Nobody, yet → `CURRENT/`.
3. **Does it have a finish line?** Live work with one stays in `CURRENT/`. Work whose finish line
   has passed is promoted or archived.
4. **Is it a duplicate?** Two documents on one subject is the thing this pass exists to end. Name
   which survives and why; the other is archived, and the delta it held is folded into the survivor
   before it goes.

Do not promote a document that merely repeats what the corpus already says.

**A document written to advise a decision closes when the decision lands.** Check whether it landed
before calling the thread open: read the code, not the document's own expectation.

### The assistant's memory has the same index rule

Claude's memory for this project is a third surface with the same shape as `CURRENT/`: a flat
directory of one-fact files, plus an index that must match it. Check it in the same pass, for the
same reason — an index that covers part of a directory reads as complete.

- **Every index row resolves to a file, and every file has a row.** Both directions.
- **Every `[[link]]` names a memory that exists**, or one deliberately yet to be written.
- **The index holds one line per memory and never content.** A memory whose substance has leaked
  into the index is a memory nobody will open.

Placement only, as everywhere else in this pass: whether a memory is *true* is `doc-current-state`'s
question and `tighten`'s D7, not this one. Locate the directory by listing Claude's per-project
state directory and matching the target's path; touch no other project's memory.

## Stage 3 — placement

**PROMOTE → the published corpus.** Place by the section's stated audience, read from the corpus
itself on the day. One distinction survives every reshape and is the one that matters:

> **If the corpus separates what exists from what is intended, unbuilt work goes in the intended
> tree regardless of how finished its design is.** Putting unbuilt work beside built work is how a
> corpus starts claiming capability it does not have.

There is no staging tree inside the corpus. A document with no finish line either states something
durable, in which case it is promoted, or it stays in `_scratch`.

A promoted document declares its own status in its own first screen, and gets a row in its section's
index. **It carries no provenance banner**: the corpus is read by people outside the company, and
"promoted from `_scratch/CURRENT` by this pass" is internal bookkeeping addressed to nobody they
are. Where a document describes something unbuilt, it says so plainly in its own opening words.

**IN-PROGRESS → `_scratch/CURRENT/`.** One flat directory, no dating, no per-topic subdirectories —
a worklist, not an archive. Its `README.md` gives each document one line naming its open thread, and
is **rewritten from the directory listing each run**. Two failures to avoid, both of which have
happened:

- An index that covers part of the directory is worse than none: it reads as complete.
- An index that accumulates arrival and departure history stops being a worklist and becomes a
  change log. It states what is open now. What moved and why is recorded in the `_archive` manifest
  and in git, not here.

**ARCHIVE → `_archive/<YYYY-MM-DD>-<reason>/`** with a `README.md` listing each file, its origin
path, and one line on why it was set down, **naming the successor where there is one**.

## Procedure

1. **Measure the shape before you touch anything.** Four checks, and they are the acceptance test at
   the end as well as the diagnosis at the start. Run them yourself; do not go looking for a tool
   that does it.

   ```powershell
   $s = "<workspace>/_scratch"
   Get-ChildItem $s/CURRENT | Where-Object { $_.PSIsContainer -or $_.Extension -ne '.md' }   # must be empty
   $docs = (Get-ChildItem $s/CURRENT -Filter *.md -File).Name | Where-Object { $_ -ne 'README.md' }
   $rows = Select-String -Path $s/CURRENT/README.md -Pattern '\[`?([^\]`]+\.md)`?\]' -AllMatches |
             ForEach-Object { $_.Matches.Groups[1].Value } | Sort-Object -Unique
   Compare-Object $docs $rows                                                                 # must be empty
   git -C $s ls-files | ForEach-Object { Get-Item "$s/$_" } |
     Where-Object Length -gt 1MB | Select-Object FullName, Length                             # only pinned fixtures
   Get-ChildItem $s -File | Where-Object Extension -eq '.md'                                  # loose at the root: each needs a lane
   ```

   A `git ls-files` that returns nothing means the tree is not a git repository. Treat that as
   *cannot measure*, never as *clean*.
2. **Inventory.** Every candidate with its path, size and mtime. Move nothing yet.
3. **Report the proposed classification as one table** — path, verdict, destination, one-line
   reason. For each IN-PROGRESS name the open thread. Flag anything you could not judge as
   UNKNOWN-VALUE rather than guessing.
4. **Wait for approval on the table.**
5. **Execute.** `git mv` inside a repo; copy plus `git rm --cached` across repos, so history stays
   where it was written.
6. **Rewrite the indexes** — the destination section's, `CURRENT/README.md` from the directory
   listing, and the new `_archive/<dated>/README.md`.
7. **Fix inbound links.** Grep the workspace for every moved filename and repoint what you find.
   Report any left verbatim — dated records of a completed migration are left as-is by convention,
   and repointing a reference inside code is a code change, which this pass does not make.
8. **Re-run the four shape checks from step 1.** Every one must come back empty, or you must say
   which invariant you left broken and why.
9. **Report.** Counts per verdict, what moved where, links repointed, anything left UNKNOWN-VALUE.

**Do not commit or push.** Leave the working trees staged and say what is ready to commit in each.

Several sessions may share these checkouts. Stage the paths you changed by name; staging everything
picks up another session's half-finished edit and commits it under your message.

## Report before moving

List every proposed move as `from → to`, with the one-line reason and the state you are assigning.
**Get agreement before writing.** A wrong promotion publishes a false statement, and the corpus is
what everything else is checked against.
