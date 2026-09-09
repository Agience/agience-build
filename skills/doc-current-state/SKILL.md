---
name: doc-current-state
description: Rewrite docstrings, comments and Markdown so they state only what is true now - what the code does, why it is built that way, how to use it. Use before promoting a document to pharos, when docs have accumulated change history, or when asked to bring documentation up to date. Prose only; it changes no code.
---

# Current-state documentation pass

Rewrite docstrings, comments and Markdown so they state only what is true **now**: what the code
does, why it is built that way, and how to use it. **Change no code — this pass touches prose only.**

Two surfaces sweep together: the tree's prose, and the Claude memory for the same project.

## ⛔ Where this pass does NOT apply

**`agience-pharos/status/` and `agience-pharos/genesis/` are exempt from the deletions below.**

Those trees are *built* on dated, attributed, provenance-marked claims. `status/README.md` requires
every claim to carry ⚑ *measured in this pass*, 📄 *read out of a named source*, or ⚠ *unverified but
carried*, and states that an unmarked flat statement is a document that needs a pass. The rule there
is **"date a claim, or maintain it"** — a dated claim stays true forever and needs no re-check.

Applying the Delete list to those trees destroys exactly the provenance they exist to carry. This
pass is calibrated for **code docstrings and repo READMEs**.

**Never swept, in any workspace:**

- **`_archive/` and anything under it.** An archive is a dated record of what was true then.
  Narration, glyphs and superseded facts are the point; rewriting one destroys the record.
- **The published canon (pharos).** It is LEDGER-gated and carries its own state markers, so a prose
  edit there without a LEDGER row puts the two out of step. Clean a document up in `_scratch`
  **before** it is promoted, not after.
- **Correction banners anywhere.** Where a document records that it was previously wrong, that
  banner is the most useful thing on the page. Never rewrite a wrong statement into a right one
  silently — the correction is the content.

## Keep

- **What it does.** The subject of the module, class or function.
- **Why it is built this way.** Rationale a caller or implementer needs in order to use or fill it
  correctly: why `None` is a result rather than an error, why a check is per-member, why a value is
  derived rather than typed.
- **How to use it.** Parameters, return shapes, examples, invariants the caller must hold.
- **Present constraints.** "A corpus embodiment does not fill this" is current state. State it
  plainly and positively, as a property of the design.
- **A measurement that justifies a decision.** "Measured: 2.048s vs 0.018s, so this uses 127.0.0.1"
  is not history — it is the reason the line reads as it does, and deleting it invites the change
  back.

## Delete

*(Not in an exempt tree — check the section above first.)*

- **Change history.** "This used to be…", "no longer", "formerly", "previously", "reversed",
  "inverted", "rewritten", "joined the contract on <date>", "absorbed X", "WHAT CHANGED". Git carries
  this.
- **Dated notes and attributions in code docstrings** — `[John, 2026-08-04]`, `MEASURED 2026-08-04`,
  `⛔ REMOVED 2026-07-30` — **unless** the date is what makes the statement true (see Keep, last
  item), or the file is in an exempt tree.
- **Failure narration.** "The gap was silent", "that belief was false", "I missed this on the first
  pass", "which is how noise was reported as deterministic", "this cost a published conclusion".
- **Self-justification and debate.** Rejected alternative names, why an option was discarded, replies
  to objections nobody raised, "this is a decision and not an oversight".
- **Hedging.** "should work", "for now", "temporarily", "hopefully", "probably", "not sure",
  "seems to", "at the moment".
- **Defensive framing.** "…which is the failure this note exists to prevent", "stated here rather
  than left to be discovered", "do NOT read that as…". State the rule; drop the defence of it.
- **Emphasis glyphs and shouting.** `⛔ ⚠ ⭐ ✅ 🚫`, and ALL-CAPS sentences or headers. Ordinary
  prose, ordinary case. Reserve capitals for identifiers that are genuinely capitalised.
- **Migration scaffolding.** Notes addressed to whoever was mid-move, once the move is done.
- **Forward-looking promises.** "the follow-up lane that renames this", "when D6 completes it",
  "this becomes X in a later pass". If it is not true now, it does not belong.
- **Spurious negation.** "something is a, not b", "this rather than that" — where b or that are
  inconsequential.

**Rewrite prohibitions as properties.** `⛔ NEVER a silent degradation` becomes "A host that cannot
measure says so at the point of measurement." The rule survives; the alarm does not.

## Scope

Applies to module, class and function docstrings; inline comments; `#:` attribute comments; README
and other Markdown; and test docstrings. A test docstring says what the test pins and why that
matters — not which bug prompted it, or that its assertion was once the opposite.

**Leave alone:** user-facing runtime strings (`"This invite is no longer valid."`), log and error
messages, identifiers, and anything inside string literals the program emits. Changing those changes
behaviour.

Planning documents keep their planning purpose: condense to what is true and what is pending, and
drop the run-by-run history and blocker post-mortems.

## Claude memory

Sweep this project's memory alongside its code: `~/.claude/projects/<project-slug>/memory/`, where
the slug is the working directory path with separators replaced by `-`. A workspace has one slug per
directory Claude has been run in, so list `~/.claude/projects/` and pick the one matching the target
rather than guessing. **Sweep no other project's memory.**

Each file holds one fact in the present tense, with `name` / `description` / `metadata` frontmatter,
and `[[name]]` links to related memories. `MEMORY.md` is the index — one line per memory, never
content. The Keep and Delete rules apply, plus:

- **Verify before rewriting.** A memory naming a file, function, flag or path is a claim about the
  code. Check it against the code, not against the memory's own confidence.
- **A false fact is deleted, not softened.** Remove the file and its `MEMORY.md` row, and name the
  evidence that disproved it. Hedging a wrong memory leaves it in circulation.
- **A drifted fact is corrected** against what the code does now, keeping the same `name` so inbound
  `[[links]]` still resolve.
- **Dates stay.** A memory's absolute date is its content — when a thing was measured or decided —
  not the dated attribution the Delete rules strip from source prose.
- **The index must match the directory.** Every row resolves to a file; every file has a row.
- A memory that only restates what the repo already records — structure, a past fix, git history,
  `CLAUDE.md` — is redundant rather than wrong. Delete it and say so.

## Method

1. **Read the code first.** The docstring is a claim; the code is the evidence. Where they disagree,
   the code wins and the prose changes.
2. **Verify every path, flag and command the prose names.** A document that cites a file that moved
   sends the reader somewhere wrong. `agience-cloud/deploy/doc_paths_check.py` measures this for
   canon.
3. **Do not invent.** If you cannot tell why something is the way it is, say what it does and leave
   the why out. A plausible rationale that is wrong is worse than an absent one.
4. **Preserve the voice.** This workspace's docs are direct and argue their case. Do not flatten them
   into neutral summary.

## Procedure

1. **Inventory both surfaces**, excluding vendored and generated trees, and locate the matching
   memory directory.

   ```powershell
   $files = Get-ChildItem <TARGET> -Recurse -File -Include *.py,*.ts,*.tsx,*.js,*.c,*.h,*.cs,*.md |
     Where-Object { $_.FullName -notmatch '\\(node_modules|dist|build|\.git|obj|bin|\.venv|venv|__pycache__|\.pytest_cache|\.ruff_cache|\.next|_archive)\\' }
   Get-ChildItem ~/.claude/projects -Directory | Where-Object Name -match '<target-slug-fragment>'
   ```

2. **Rank by density.** Fix the worst files first; they carry most of the volume.

   ```powershell
   $pat = '(⛔|⚠|⭐)|(?i)\b(previously|no longer|formerly|used to|for now|hopefully|should work|caveat|unfortunately|turns out|20\d\d-\d\d-\d\d)\b'
   Select-String -Path $files.FullName -Pattern $pat |
     Group-Object Path | Sort-Object Count -Descending |
     Select-Object -First 40 | ForEach-Object { "{0,5}  {1}" -f $_.Count, $_.Name }
   ```

3. **Rewrite, file by file.** Read the whole file before editing — a header often argues against its
   own cleanup, and stale cross-references hide in the prose.

   - For a header that is mostly narration, draft the replacement separately and splice it in by
     line range rather than by string match.
   - For scattered blocks, use exact-match edits so code is never touched.
   - Preserve every code line byte for byte.

4. **Correct stale facts while you are there.** Narration often names archived packages, renamed
   modules or superseded signatures. Replace them with what is true now, verified against the code.

5. **Sweep the memory directory.** One file at a time, verifying each claim against the code before
   touching the prose. Reconcile `MEMORY.md` last, once the directory has settled.

6. **Verify each file.**

   ```powershell
   Select-String -Path <file> -Pattern '(⛔|⚠|⭐)|20\d\d-\d\d-\d\d'   # expect no hits
   python -c "import ast; ast.parse(open(r'<file>',encoding='utf-8').read())"
   ```

   Memory verifies in both directions: every `MEMORY.md` row resolves to a file, every file has a
   row, and every `[[link]]` names a memory that exists or is deliberately yet to be written.

   Run the repo's test suite once the repo is done. Prose edits do not change behaviour, so a failure
   means a code line was disturbed.

7. **Report.** Files touched, lines removed, stale facts corrected, memories rewritten, memories
   deleted with the evidence for each, test result.

**Leave all changes uncommitted in the working tree.**

## After

Run the gates — a prose pass is exactly the change that moves their numbers:

    python agience-cloud/deploy/doc_paths_check.py       # baseline may only shrink
    python agience-cloud/deploy/claims_check.py          # qualifiers still attached

If a path count went **up**, the pass introduced a stale reference. Fix it before finishing.

## Writing style

Objective and positive. State the fact, then the reason if a caller needs it.

| Instead of | Write |
| --- | --- |
| `⛔ Returns None when the frame cannot carry a read. None is the computed null and it is a RESULT — never a fabricated coupling.` | `Returns None when the frame cannot carry a read. None is the computed null and it is a result: the caller propagates the frame unabsorbed.` |
| `⭐ JOINED THE CONTRACT 2026-08-07. The gap was SILENT, which is the worst kind…` | `Required whenever a frame co-registers heterogeneous planes, because read raw the leading mode is the unit mismatch.` |
| `This used to compare CODE POINTS, mirroring Python's sorted()…` | `Compares UTF-16 code units, matching JavaScript's own string ordering.` |
| `⚠ STEP 2 IS TRANSITIONAL, AND NAMED AS SUCH. It exists because plan item D5 moved…` | *(delete — describe what step 2 does, not why it is temporary)* |

One idea per paragraph. Prefer a short table or signature block to a paragraph of prose about shapes.

## Worked example

One module went 1,144 lines to 610. Its 90-line header opened with name-choice debates, dated
attributions, and an argument against being cleaned up ("rewriting them would erase the attribution
that makes them auditable"), while saying almost nothing about what the class was or how to fill one.
It now opens with the contracts, who fills each, and a usage block. The prose also still named an
archived package that the live data in the same file had already stopped pointing at; the prose was
corrected against the code.

The shape recurs: **the densest narration sits in headers, the header argues for its own
preservation, and the stale fact sits next to the narration rather than inside it.**
