---
name: doc-sweep
description: Run the current-state prose pass across a whole workspace rather than one document - a mechanical pre-pass that strips emphasis glyphs and review tags safely, then a ranked worklist handed to subagents one file at a time, gated so a rewrite cannot change code. Use when many repos have accumulated narration, after a fast-change period, or when doc-current-state would take too long by hand. Prose only; it changes no code.
---

# Doc sweep — the current-state pass, at workspace scale

`doc-current-state` states what the prose should say. This states how to get there across hundreds
of files without breaking anything, and it exists because doing it by hand does not finish: the
first six files of one such pass took the effort of a small refactor, and there were 850 flagged.

**Read `doc-current-state` first.** Its Keep and Delete lists are the rules; nothing here replaces
them. What this adds is the split, the ranking and the harness.

## The split — two jobs, and only one is fan-out work

| | rewrite | stale facts |
|---|---|---|
| the work | shouting and change-history phrasing into present-tense properties | prose that contradicts the code |
| needs | the flagged block, and the code it describes | reading the code properly |
| suits a subagent | yes | no |
| what it is worth | the tree reads like one voice | this is where every real defect was found |

Keep them apart. A pass measured on one workspace found a route the module header still advertised
after it was deleted, a docstring describing a branch its function does not contain, a test naming a
path template that had changed, and an evidence file whose removal turned 21 tests red. **Every one
came from reading the code, none from matching a pattern.**

So the agent **reports** a suspected stale fact and never acts on it. A plausible rationale that is
wrong is worse than an absent one, and an agent asked to tidy prose will write one confidently.

## 1. The mechanical pre-pass

`agience-build/scripts/doc_sweep.py` removes what carries no meaning a reader needs — emphasis
glyphs, review-item tags, dated ruling attributions — and flags what needs a person.

    python agience-build/scripts/doc_sweep.py <path> [...]              report, write nothing
    python agience-build/scripts/doc_sweep.py --write <path> [...]      apply the safe deletions
    python agience-build/scripts/doc_sweep.py --flags <path> [...]      every flag, as path:line kind hit
    python agience-build/scripts/doc_sweep.py --worklist <path> [...]   the ranked set, cuts applied
    python agience-build/scripts/doc_sweep.py --shape <file.py> [...]   the code digest the harness gates on

It rewrites `tokenize` COMMENT tokens and `ast` docstring nodes and nothing else, so an OpenAPI
`description=`, a log message and an error string are out of reach. It refuses to write when the
rewrite changes the code's AST or the result will not parse, and both refusals are pinned against
planted corruptions in `scripts/test_doc_sweep.py`.

Run it per repo, not at the root, until you have read what it would do. It skips the published
canon, `_secret`, vendored trees, generated agent instructions, and itself — and it applies those
exclusions to a path typed on the command line as well as to one the walk found, so pointing it at
a canon file skips the file and says so.

**Python is rewritten; the C family is only ranked.** `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`,
`.cs`, `.c` and `.h` are scanned for flags and never written: their comments are found by a scanner
that tracks string literals, template literals and escapes, which is enough to rank a file for a
person and not enough to edit one safely. Without them the ranking was blind to 432 files here, and
`agience-observe`'s tray app — 17 files, almost all of them shouting — did not appear at all.

**Then run the repo's test suite.** The pre-pass is safe by construction and the suite is what
proves it on the day the construction is wrong.

## 2. Rank, and cut the list before spending anything

Three cuts, in order. On one workspace they took 850 files to 143.

**Fix the pattern before trusting its output.** A flag list is read by someone deciding where to
spend an hour, so a phrase that is wrong more often than right costs more than it catches. `it was`
raised 195 files, `corrected` 19, `rewritten` 12 — ordinary English almost every time. Removing
four such phrases took 850 to 663 and cost nothing.

**And record the ones you measured and kept.** `no longer` is the loosest phrase still on the list:
235 occurrences, about half of them a condition a checker looks *for* — "a generated file that no
longer matches its source", "tests for modules that no longer exist" — rather than a change the
code went through. No lexical rule separates the two senses; splitting on a preceding relative
clause came out 117 against 108, which is no signal. It stays, because the other half is real and a
reader tells them apart at a glance. The measurement sits beside the pattern so the next pass does
not re-derive the same non-result.

**Skip the dated records, and the benches with them.** A ledger, a build log, a report under
`tighten/REPORTS/`, a live worksheet in `_scratch/CURRENT/` — the dates are the content and a date
sweep destroys them. Thirteen such files held 602 flags, every one of which should stay. Recognise
them by what they are for, not by where they live: `_scratch/lab/` is the same kind of thing one
step down, one-shot code whose dated verdicts the documents beside it quote, and it was 45 of the
78 files an earlier ranking offered — a worklist sending a person to the least durable prose in the
workspace. A lab script that stops being one-shot moves into the repo it acts on, and it is swept
there.

**Take the head, and say what you left.** With the dated records out, 143 files carried 1,760 flags
and the remaining 507 carried 993 between them — under six apiece, mostly one incidental date or
phrase. Working the head and reporting the tail honestly is the pass finishing; working the tail is
the pass never finishing.

`--worklist` applies the cuts and prints the ranked set with the tail, the skipped records and the
skipped benches counted, so the list is reproduced on demand rather than committed to a tree and
left to go stale.

**Read the kind mix, not the count.** Each row prints its flags by kind, because eighteen dates and
eighteen shouted headers are not the same hour. Shouting is always rewritten. A date in a gate under
`agience-cloud/deploy/` is almost always a baseline's provenance — *first pinned 2026-08-25 at what
each tree measured* — and the Keep list protects it, so a date-dominated gate row is a small correct
diff and not an hour. Send the caps-dominated rows first.

## 3. One file per agent, never a repo

The failure mode is an agent rewriting prose about code it has not read. Give it one file, the
flagged line numbers, and nothing else to do.

```
Rewrite the flagged prose in ONE file. Prose only — change no code.

File: <path>

Get the flagged lines yourself:
    python agience-build/scripts/doc_sweep.py --flags <path>

Read the whole file first, including the code the prose describes.

REWRITE, in place:
- ALL-CAPS sentences and headers → ordinary case
- change history ("used to", "no longer", "previously", "this said X until
  <date>") → state what is true now, as a property
- dated attributions in code docstrings → drop the date, keep the fact
- failure narration, self-justification, hedging, defensive framing → drop

KEEP:
- a measurement that justifies a decision ("measured 2.048s vs 0.018s, so
  this uses 127.0.0.1") — deleting it invites the change back
- present constraints, stated positively
- correction banners: where a document records that it was wrong, that IS
  the content

NEVER TOUCH:
- string literals the program emits: OpenAPI description=, log messages,
  error detail=, user-facing text. Tests pin exact tokens inside them.
- any line that is not a comment or a docstring
- a docstring `doc_sweep.py` itself cannot tell is emitted: a FastAPI/Pydantic
  `BaseModel`'s class docstring becomes its OpenAPI schema `description`
  verbatim (confirmed by calling `.model_json_schema()`), and a route
  handler's docstring becomes its operation `description` UNLESS the
  decorator already passes an explicit `description=` — check the decorator
  before touching a route handler's docstring, and skip every response/
  request model's docstring outright
- a docstring a test pins by name. Before editing one, grep the repo's tests
  for this module and for `__doc__`; a test asserting exact wording turns a
  de-shouting edit red, and neither a parse nor a code-shape check reads an
  assertion body

DO NOT INVENT. If you cannot tell why something is the way it is, say what
it does and leave the why out.

If the prose contradicts the code, DO NOT FIX IT. Finish the rewrite, then
list each contradiction under "SUSPECTED STALE:" with file:line and what the
code actually does. Someone else verifies those.

Do not run git. Do not commit. Do not run the suite — the harness does that
once per repo, after the batch.

Report, and nothing else:
1. FILE
2. FLAGS: n before -> n after, from a second --flags run
3. KEPT: each flag you deliberately left, with why
4. SUSPECTED STALE: file:line + what the code actually does, or "none"
```

**Edited in place, never printed back.** Handing the whole file through the report doubles the cost
of every large file and puts a transcription between the agent's judgement and the disk, while the
harness reads the disk anyway.

## 4. The harness — do not trust the output, check it

```
before the batch:
    doc_sweep.py --shape <every .py in the head>   > shapes.before
    the suite of every repo you are about to touch > the baseline failures

per file, worst first:
    run the agent

after the batch:
    doc_sweep.py --shape <the same files>          compare to shapes.before
    a digest that moved means prose work reached code — revert that file

per repo:
    the repo's own test suite            catches an edited emitted string
    dotnet test <the .csproj>            for C-family work: it compiles first, and a
                                         comment marker landed in code will not compile
    doc_paths_check.py                   the count must not go UP
    build_bundles.py --check             if any chorus persona source was touched

collect every SUSPECTED STALE for a human pass
```

`--shape` prints a digest of the file's code with every docstring blanked, so two files with the
same digest differ only in prose. It is the only check that catches an agent quietly editing code,
and it is cheap.

**Take the baseline before the batch, not after.** These trees carry several sessions' in-flight
work, and a repo mid-restructure is red for reasons a prose pass did not cause. On the run of
2026-09-07 `agience-cloud` was already 33 failures and one collection error — moved compose files,
a deleted gate module, a lint baseline raised by another session's new code — and without the
before-reading there is no way to say so rather than guess it.

## What goes wrong

- **Emitted strings.** This is the one that will cost a suite. Tests pin literal tokens inside
  OpenAPI descriptions — a capitalised word, a phrase a client must be told. An agent tidying those
  breaks tests and cannot see why. The rule is not "be careful with strings", it is *comments and
  docstrings only*.
- **A docstring that is not a comment, and is still emitted.** *Comments and docstrings only* is
  necessary but not sufficient: `doc_sweep.py`'s own mechanical safety knows about explicit
  `description=` strings and stops there, but two docstring shapes reach a caller by a path the
  tool cannot see. Measured directly against this workspace's pydantic (2.13.4): a `BaseModel`'s
  class docstring is copied verbatim into `.model_json_schema()["description"]`, and a FastAPI
  route handler's docstring becomes the OpenAPI operation `description` whenever the decorator has
  no explicit `description=` of its own (an explicit one wins outright and the docstring goes
  unused — confirmed both ways). `agience-mantle/src/mantle/routers/grants_router.py` carried five
  flagged blocks inside exactly this shape (`GrantResponse`, `GrantWithClaimResponse`,
  `InviteDetailsResponse` docstrings; a `Field(description=...)`) — left flagged and untouched.
  Before rewriting any router-file docstring: is it a `BaseModel` subclass, or a decorated handler
  with no `description=` in its decorator? Either one is off limits regardless of what the flag
  list says.
- **A file whose subject is the thing being removed.** `doc-current-state/SKILL.md` quotes a dated
  removal marker as an example of what to delete; `doc_sweep.py` documents the patterns by showing
  them. A sweep over either deletes the instructions rather than following them. Both are excluded
  by name, and a new one of these will need excluding too.
- **Line endings and alignment.** A rewrite rebuilt with a bare newline turns a CRLF file mixed one
  comment at a time, and a whitespace tidy-up applied to every line reformats aligned tables while
  removing nothing. Neither is visible to a syntax check or to an AST comparison. Both are pinned in
  the tool's tests because both shipped once.
- **Concurrent sessions.** Several sessions work these trees. A staged change is a change the next
  person's commit carries, including a staged deletion. Read and write inside one script, and check
  `git status` before concluding anything about what you changed.
- **A docstring can be pinned too, not just an emitted string.** `src/mantle/db/lattice_api.py::mark_materialized`
  read "called by the index JOB", and `tests/test_the_marker_follows_the_work.py::
  test_the_contract_docstring_no_longer_says_enqueue` asserts `"called by the index JOB" in
  lattice_api.mark_materialized.__doc__` verbatim, capital JOB included — a regression guard
  against the docstring drifting back to a prior wrong claim ("called wherever indexing is
  enqueued"). De-shouting that word to "job" is exactly the kind of edit this pass makes by
  default, and it broke the test. The tell is the test's own name or docstring naming "docstring"
  or quoting the exact prior wording — run the file's test suite after every rewrite (this skill
  already says to); do not treat a green `ast.parse` and a matching `code_shape` as sufficient on
  their own, since neither one reads assertion bodies.

## Report

Files touched, flags before and after, stale facts found and who verified them, the tail left with
its size, and the suite and gate results per repo. **Leave all changes uncommitted.**
