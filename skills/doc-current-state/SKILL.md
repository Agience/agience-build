---
name: doc-current-state
description: Rewrite docstrings, comments and Markdown so they state only what is true now - what the code does, why it is built that way, how to use it. Use before promoting a document to the published corpus, when docs have accumulated change history, or when asked to bring documentation up to date. Prose only; it changes no code.
---

# Current-state documentation pass

Rewrite docstrings, comments and Markdown so they state only what is true **now**: what the code
does, why it is built that way, and how to use it. **Change no code — this pass touches prose only.**

Two surfaces sweep together: the tree's prose, and the Claude memory for the same project.

## Where this pass does NOT apply

**Never swept, in any workspace:**

- **`_archive/` and anything under it.** An archive is a dated record of what was true then.
  Narration, glyphs and superseded facts are the point; rewriting one destroys the record.
- **Dated records and benches** — a ledger, a build log, a live worksheet on the working floor,
  one-shot code beside it. The dates are the content and a date sweep destroys them. Recognise them
  by what they are for, not by where they live.
- **Correction banners anywhere.** Where a document records that it was previously wrong, that
  banner is the most useful thing on the page. Never rewrite a wrong statement into a right one
  silently — the correction is the content.

## The published corpus

A workspace's public, external-facing prose is swept like any other repository, with one difference
that outranks everything else in this skill:

**Its statements of a limit are the most credible writing in it, and the Delete list below must
never reach them.** A section headed *what this does not establish* or *what is not yet measured*, a
mandatory-qualifier marker, the strongest objection to a document, and every emphatic negation
inside one are load-bearing. So is any glyph a legend defines in the same file — a roadmap that
defines its own state markers in its first table loses the state of every item if they are stripped.

Because it is external-facing, three deletions matter more there than anywhere else: dated personal
attributions, pointers into documents that are not published, and internal machine names.

**Verify a claim before deleting it as stale.** One such pass found four documents asserting that a
section "was never written" when it had been there all along, and a naming document accusing a
README of stating two licences backwards when the README matched the actual licence files. Both
survived earlier passes because they read like provenance. Check the tree, not the prose.

## Keep

- **What it does.** The subject of the module, class or function.
- **Why it is built this way.** Rationale a caller or implementer needs in order to use or fill it
  correctly: why `None` is a result rather than an error, why a check is per-member, why a value is
  derived rather than typed.
- **How to use it.** Parameters, return shapes, examples, invariants the caller must hold.
- **Present constraints.** "A corpus embodiment does not fill this" is current state. State it
  plainly and positively, as a property of the design.
- **A measurement that justifies a decision.** "Measured: 2.048s vs 0.018s, so this uses the loopback
  address" is not history — it is the reason the line reads as it does, and deleting it invites the
  change back.

## Delete

*(Not in an exempt tree — check the section above first.)*

- **Change history.** "This used to be…", "no longer", "formerly", "previously", "reversed",
  "inverted", "rewritten", "joined the contract on <date>", "absorbed X", "WHAT CHANGED". Git
  carries this.
- **Dated notes and attributions in code docstrings** — a bracketed name and date, `MEASURED <date>`,
  a dated removal marker — **unless** the date is what makes the statement true (see Keep, last
  item), or the file is in an exempt tree.
- **Failure narration.** "The gap was silent", "that belief was false", "I missed this on the first
  pass", "which is how noise was reported as deterministic", "this cost a published conclusion".
- **Self-justification and debate.** Rejected alternative names, why an option was discarded, replies
  to objections nobody raised, "this is a decision and not an oversight".
- **Hedging.** "should work", "for now", "temporarily", "hopefully", "probably", "not sure",
  "seems to", "at the moment".
- **Defensive framing.** "…which is the failure this note exists to prevent", "stated here rather
  than left to be discovered", "do NOT read that as…". State the rule; drop the defence of it.
- **Emphasis glyphs and shouting.** Warning and prohibition glyphs, and ALL-CAPS sentences or
  headers. Ordinary prose, ordinary case. Reserve capitals for identifiers that are genuinely
  capitalised. **Two exceptions, and they are absolute.** A glyph that a legend in the same file
  defines is a notation, not decoration — keep it, or replace it with the word it stands for; never
  just delete it. And a glyph or capital inside a statement of a limit stays: strip the alarm from a
  rule, never from an admission.
- **Migration scaffolding.** Notes addressed to whoever was mid-move, once the move is done.
- **Forward-looking promises.** "the follow-up lane that renames this", "this becomes X in a later
  pass". If it is not true now, it does not belong.
- **Spurious negation.** "something is a, not b", "this rather than that" — where b or that are
  inconsequential.

**Rewrite prohibitions as properties.** "NEVER a silent degradation" becomes "A host that cannot
measure says so at the point of measurement." The rule survives; the alarm does not.

## Scope

Applies to module, class and function docstrings; inline comments; attribute comments; Markdown; and
test docstrings. A test docstring says what the test pins and why that matters — not which bug
prompted it, or that its assertion was once the opposite.

**Leave alone:** user-facing runtime strings, log and error messages, identifiers, and anything
inside string literals the program emits. Changing those changes behaviour.

Planning documents keep their planning purpose: condense to what is true and what is pending, and
drop the run-by-run history and blocker post-mortems.

## Claude memory

Sweep this project's memory alongside its code. It lives under Claude's per-project state directory,
one directory per working directory Claude has been run in, named after that path. **List the
projects directory and pick the one matching the target rather than guessing, and sweep no other
project's memory.**

Each file holds one fact in the present tense, with `name` / `description` / `metadata` frontmatter,
and `[[name]]` links to related memories. The index file is one line per memory, never content. The
Keep and Delete rules apply, plus:

- **Verify before rewriting.** A memory naming a file, function, flag or path is a claim about the
  code. Check it against the code, not against the memory's own confidence.
- **A false fact is deleted, not softened.** Remove the file and its index row, and name the evidence
  that disproved it. Hedging a wrong memory leaves it in circulation.
- **A drifted fact is corrected** against what the code does now, keeping the same `name` so inbound
  `[[links]]` still resolve.
- **Dates stay.** A memory's absolute date is its content — when a thing was measured or decided —
  not the dated attribution the Delete rules strip from source prose.
- **The index must match the directory.** Every row resolves to a file; every file has a row.
- A memory that only restates what the repo already records — structure, a past fix, git history,
  the project's own instructions file — is redundant rather than wrong. Delete it and say so.

## Method

1. **Read the code first.** The docstring is a claim; the code is the evidence. Where they disagree,
   the code wins and the prose changes.
2. **Verify every path, flag and command the prose names.** A document that cites a file that moved
   sends the reader somewhere wrong. Extract the paths a file names and test each one against disk —
   this is the single highest-yield check in the pass, and it is two lines:

   ```powershell
   Select-String -Path <file> -Pattern '`([\w./-]+\.\w{1,5})`' -AllMatches |
     ForEach-Object { $_.Matches.Groups[1].Value } | Sort-Object -Unique |
     Where-Object { -not (Test-Path (Join-Path <root> $_)) }
   ```
3. **Do not invent.** If you cannot tell why something is the way it is, say what it does and leave
   the why out. A plausible rationale that is wrong is worse than an absent one.
4. **Preserve the voice.** Docs that argue their case should keep arguing it. Do not flatten them
   into neutral summary.

## Procedure

1. **Inventory both surfaces**, excluding vendored, cached, generated and archived trees, and locate
   the matching memory directory.

   ```powershell
   $skip = '\\(node_modules|dist|build|\.git|obj|bin|\.venv|venv|__pycache__|\.pytest_cache|\.ruff_cache|\.next|_archive)\\'
   $files = Get-ChildItem <TARGET> -Recurse -File -Include *.py,*.ts,*.tsx,*.js,*.c,*.h,*.cs,*.md |
     Where-Object { $_.FullName -notmatch $skip }
   ```

2. **Rank by density.** Fix the worst files first; they carry most of the volume.

   ```powershell
   $pat = '(?i)\b(previously|no longer|formerly|used to|for now|hopefully|should work|caveat|unfortunately|turns out|20\d\d-\d\d-\d\d)\b'
   Select-String -Path $files.FullName -Pattern $pat |
     Group-Object Path | Sort-Object Count -Descending |
     Select-Object -First 40 | ForEach-Object { "{0,5}  {1}" -f $_.Count, $_.Name }
   ```

3. **Rewrite, file by file.** Read the whole file before editing — a header often argues against its
   own cleanup, and stale cross-references hide in the prose.

   - For a header that is mostly narration, draft the replacement separately and splice it in by
     line range rather than by string match.
   - For scattered blocks, use exact-match edits so code is never touched.
   - Preserve every code line byte for byte, and the file's existing line endings.

4. **Correct stale facts while you are there.** Narration often names archived packages, renamed
   modules or superseded signatures. Replace them with what is true now, verified against the code.

5. **Sweep the memory directory.** One file at a time, verifying each claim against the code before
   touching the prose. Reconcile the index last, once the directory has settled.

6. **Verify each file.** Re-run the density pattern and expect no hits; parse the file to prove the
   code is intact; then run the repo's own test suite once the repo is done. Prose edits do not
   change behaviour, so a failure means a code line was disturbed.

   Memory verifies in both directions: every index row resolves to a file, every file has a row, and
   every `[[link]]` names a memory that exists or is deliberately yet to be written.

7. **Report.** Files touched, lines removed, stale facts corrected, memories rewritten, memories
   deleted with the evidence for each, test result.

**Leave all changes uncommitted in the working tree.**

## After

Two counts, taken before the pass and again after, over every file you touched:

- **References to paths that do not resolve** — the check in Method step 2, run across the whole
  target rather than one file. It may only shrink.
- **Published figures still carrying their qualifier.** Diff out the removed lines and confirm no
  number left without the condition that made it true: `git diff -U0 | grep '^-'`, then look for
  every figure in it in the new text with its *simulated*, *not yet wired*, *measured before the
  repair* intact.

If the repo happens to enforce either of these in CI, that run is a second opinion, not a substitute
— take your own reading before and after, because a gate tells you the state, not the delta.

**If the unresolvable-path count went up, the pass introduced a stale reference.** Fix it before
finishing.

## Writing style

Objective and positive. State the fact, then the reason if a caller needs it.

| Instead of | Write |
| --- | --- |
| `Returns None when the frame cannot carry a read. None is the computed null and it is a RESULT — never a fabricated coupling.` | `Returns None when the frame cannot carry a read. None is the computed null and it is a result: the caller propagates the frame unabsorbed.` |
| `JOINED THE CONTRACT <date>. The gap was SILENT, which is the worst kind…` | `Required whenever a frame co-registers heterogeneous planes, because read raw the leading mode is the unit mismatch.` |
| `This used to compare CODE POINTS, mirroring Python's sorted()…` | `Compares UTF-16 code units, matching JavaScript's own string ordering.` |
| `STEP 2 IS TRANSITIONAL, AND NAMED AS SUCH. It exists because plan item D5 moved…` | *(delete — describe what step 2 does, not why it is temporary)* |

One idea per paragraph. Prefer a short table or signature block to a paragraph of prose about shapes.

## The shape this takes

One module went 1,144 lines to 610. Its 90-line header opened with name-choice debates, dated
attributions, and an argument against being cleaned up ("rewriting them would erase the attribution
that makes them auditable"), while saying almost nothing about what the class was or how to fill one.
It now opens with the contracts, who fills each, and a usage block. The prose also still named an
archived package that the live data in the same file had already stopped pointing at.

The shape recurs: **the densest narration sits in headers, the header argues for its own
preservation, and the stale fact sits next to the narration rather than inside it.**
