---
name: tighten
description: The recurring workspace tightening pass - scan every repo for what the last few days of fast change left behind, and close it. Finds drift between code and prose, shadow and parallel implementations, paths that moved and left broken references, improvements that landed in one sibling and not the others, and dangling work nothing points at. Incremental against the last run; run it daily. Code and architecture only; it is not a doc-placement pass.
---

# Tighten — the recurring hygiene pass over every repo

Fast change leaves a wake. This pass reads the wake and closes it, **while the change is still
recent enough to be understood.** Run it daily; it is cheap when run often and expensive when not.

**Scope: technical.** Code, structure, references, configuration, architecture. Its companions
handle placement and prose — `doc-triage` decides where a document or a lab thread **lives**,
`doc-current-state` rewrites what a document **says**. This pass touches prose **only** where prose
makes a claim the tree no longer supports.

The seam is sharp and deliberate: `doc-triage` moves a file and repoints inbound *document* links,
and it states that **repointing a reference inside code is a code change it does not make**. That is
this pass's D2. **Run `tighten` after any `doc-triage` sweep** — a triage run is the largest single
source of moved paths a workspace produces.

**Rule zero governs every line of the report.** A finding is a measurement or it is not a finding.
Every entry carries the command that produced it and what that command printed. "It looks like a
duplicate" is not a finding; `diff` output is.

**Every sweep here is composed at run time.** No detector depends on a checked-in scanner, and none
should acquire one: a sweep frozen into a script goes stale exactly where a stale sweep is most
expensive, and a private copy in a scratch file is the shadow this pass exists to find. Build each
sweep from the rules below against the tree as it is today.

---

## 1. State — what makes this consistent run to run

The pass keeps its state in one directory, in a repo that is pushed. A pass whose memory lives
somewhere unrestorable silently restarts from zero and reports a week of old rot as new.

| file | what it holds |
|---|---|
| `STATE.json` | last run, per-repo HEAD, every finding ever raised |
| `LEDGER.md` | one line per run: date, mode, raised / fixed / carried |
| `REPORTS/TIGHTEN-YYYY-MM-DD.md` | the full report for one run |

**Locate that directory by searching for those three names before you start.** Create it only after
the search comes back empty, and never start a second one — two state directories means two
recurrence counts, and both are wrong. If you find state in a different place from where a document
says it should be, the document is the defect; report it and use what is on disk.

**First action of every run: read the state file.** Last action: write it back.

```json
{
  "last_run": "<iso timestamp>",
  "mode": "incremental",
  "repos": { "<repo>": { "head": "<sha>", "dirty": false } },
  "findings": {
    "<id>": { "first_seen": "...", "last_seen": "...", "runs": 7,
              "state": "open | fixed | accepted",
              "note": "why it is accepted, and by whom" }
  }
}
```

**Finding IDs are stable and derived, never invented:** `<detector>:<path>:<slug>`. The same rot
must produce the same ID next week, or the recurrence count is a lie and the pass becomes noise.

| state | meaning | on the next run |
|---|---|---|
| `open` | raised, not closed | re-verified, recurrence incremented, reported again |
| `fixed` | verified gone | verify once more, then stop reporting it |
| `accepted` | deliberate, with a written reason | **not re-litigated.** Named in one summary line |

**An accepted finding needs a reason and a person.** Accepting is the owner's call, not the pass's.
The pass may *propose* acceptance; it may not grant it. A finding that reappears for **five runs**
with nobody acting is escalated to the top of the report as `STALLED` — either it gets fixed or it
gets accepted, and drifting between the two is how a gate becomes something everyone ignores.

### Mode

| condition | mode |
|---|---|
| state file missing, or last run more than 7 days ago | **full** — every detector over every repo |
| otherwise | **incremental** — every detector, scoped to what changed since the last run |
| the 1st of the month, or on request | **full**, regardless |

Incremental is not a lighter pass. It runs all ten detectors; it just gives each a smaller window. A
daily run should finish; if a detector will blow the budget, say so in the report and defer it to
the next full sweep **by name**. **Never silently truncate** — a pass that covered less than it
claims is worse than one that admits it stopped.

---

## 2. Orient — establish the window

The **workspace root** is the directory holding `_scratch` and `_archive`. **A repo is any directory
containing `.git`, at any depth** — search for them; do not work from a remembered list, and do not
assume they are all direct children of the root, because some products ship as several repos nested
inside one plain directory. Where the workspace keeps a manifest of repos, the disk is still the
measurement: a repo on disk and not in the manifest is itself a D9 finding.

```sh
git -C <repo> log --oneline <last_head>..HEAD         # the commits in this window
git -C <repo> diff --name-status <last_head>..HEAD    # A / M / D / R — the file-level wake
git -C <repo> diff --name-status                      # uncommitted work counts as change
git -C <repo> ls-files --others --exclude-standard    # untracked counts as change
```

The **rename and delete set** — the `D` and `R` rows — is the single most productive input to this
pass. Everything in D2 and most of D6 keys off it.

The working floor is a repo like any other and is **in scope**: its lab tree holds real code and its
worklist holds the documents that code answers to. The archive is **out of scope** — it is what has
been set down, and it is allowed to be stale.

### The prune set — derive it, then apply it to every sweep this pass runs

Prune dependency trees, caches, virtual environments, packaging output and the archive. Start from
the obvious names, then **check the result against the tree** rather than trusting the list.

**Ask of every name: does the tooling GENERATE this name, or did a repo CHOOSE it?** Prune the
generated ones only. A name like `build` fails this test — it is a packaging artifact in one repo
and a real source tree in another, so pruning it by name hides working code. The fix is to prune the
*generator's* name, not the generic one, and to confirm by counting tracked files under each
candidate directory: a directory that is almost entirely untracked is output, one that is almost
entirely tracked is source.

Getting this wrong is expensive in a specific way. A pass that walks into a dependency tree reports
that dependency's debt as this workspace's, and it looks completely actionable — a real path, a real
line number, a real marker. It carried for three runs once before anyone re-measured with the
dependency pruned, at which point the entire finding evaporated.

**Prune during the descent, never filter after it.** A recursive glob has no prune hook, so a skip
applied to its output still pays for the whole walk and — worse — still *counts* what it walked if
you miss an entry. Use a walk that lets you edit the directory list in place, or `grep
--exclude-dir` / `find -prune`.

Two rules follow, and they are the same rule:

- **Vendored and generated trees are not this workspace's code.** A finding sourced from one is
  noise with a file path attached, and it is worse than no finding because it looks actionable.
- **A count is a claim.** Before carrying one, ask which directories produced it.

Uncommitted and untracked work is **in scope**. Most rot is catchable before it is committed.

---

## 3. Method — the faults this pass has actually made

Every rule below was written after this pass got something wrong. They sit here rather than under a
detector because they apply to all of them, and most of what follows is about not producing
findings-shaped noise. Read this before the detectors.

### An absence is only as good as the scope that produced it

**This is the most reliable fault this pass makes.** A clean or settled result is wrong because of
what the search did not cover, and widening it changes the answer. The recurring shapes:

- Searching the file you expect a symbol in, rather than the whole package.
- A suffix pattern that cannot match a bare filename.
- A head-only read that cannot see a banner further down the file.
- A single-level glob (`*/x`) that cannot see a nested one (`*/*/x`).
- A similarity or sampling parameter set so low that the candidate set is not recall at all.

**When a sweep returns clean, the first question is what it did not examine — and the second is
whether the pattern you wrote could have matched the missing case at all.** Half of these are a
pattern structurally incapable of matching. Write the widest form first and narrow it only when it
is too slow to run. **State the scope alongside any zero.**

### Do not publish a new detector's first number

Sample its output by hand, find the class it is wrong about, re-measure, and repeat until the
examples you spot-check are all real. One reference detector went 891 → 448 → 232 → 170 → 151 across
five refinements, and the pass published the third of those while this very rule said not to.

**"Refine until the number stops moving" is weaker than it sounds, because the number stops moving
when you stop looking.** What works is reading who cites what and asking whether a person wrote that
string as a path or as a name. A count cannot tell you that; a dozen examples read in context can.
The last two refinements above were both conventions rather than defects — a module naming its own
sibling package, and repo short-names.

### Count what you could not read, and print it beside the answer

*"314 found"* and *"314 found, 23 files unreadable"* are different claims, and only one of them can
be checked. A sweep hunting swallowed exceptions was itself a swallowed exception and printed a
total as though it had read everything. Two specific causes:

- **A byte-order mark defeats a plain UTF-8 parse.** It survives decoding, the parser raises, and an
  `except: continue` eats the file. Read source with `utf-8-sig`.
- **A NUL byte makes a file invisible to text search.** `grep` classifies it as binary and prints
  *"Binary file matches"* instead of the line. The file still opens, renders and passes every other
  gate. Assert zero NULs over the text tree; zero is the right number, not a baseline.

### Agreement between two implementations is agreement, not health

**A cross-check that compares two implementations and discards the verdict they agree on is not a
check.** One accounting cross-check compared three quantities against its own independent SQL, found
them equal, returned PASS — and never read the field that said the books did not balance. Both sides
agreed that rows had been lost, and the check printed PASS.

When you find a verification that cross-checks, ask what it does with the **answer**, not just
whether the two paths match. The same shape hides in any "A and B agree" assertion: a diff of two
renderers, a replay that compares against itself, a gate asserting a baseline equals its parts
without asking whether the parts are right.

**When an invariant is checked two ways, know which way is blind to which failure.** A cheap O(1)
identity and an expensive scan do not answer the same question, and a green cheap check is not the
expensive one's answer.

### A discrepancy's direction does not name the wrong side — find the third quantity

Reading "the counter is above the disk, so the counter over-counts" straight off the sign got it
exactly backwards on a live store. A third, independently derived quantity settled it: the counter
agreed with the allocation ledger to the unit, and the disk was short. The counter was the reliable
witness, and the repair applied to the wrong side silenced it *and* broke an invariant that had been
holding.

Before "correcting" either side of a mismatch, name a third quantity and see which side it agrees
with. If there isn't one, you do not yet know what is wrong — and a plausible repair applied to the
wrong side destroys the evidence that would have told you.

**And a reconciliation is not a correction.** Making the books balance by adjusting both sides is a
deliberate write-off declaring "these were removed", which erases the last signal that anything went
missing. That is an owner's decision with a record attached, never a tidy-up.

### Take two readings of a moving system inside one transaction

A scan and a counter read taken minutes apart compare two different instants, and under ingest the
absolute numbers move between them. Take both inside one read transaction: the drift then reads as a
stable offset while every absolute number moves under it, and that stability is what distinguishes a
historical loss from an ongoing leak. You cannot see it at all with two unsynchronised reads.

Related: **a read mode that promises a database file cannot change will skip its write-ahead log.**
It does no locking and never consults the WAL, so it silently answers from a stale snapshot. Reserve
it for genuinely frozen files.

### To find out whether a guard fires, read it — never run a writer to test its refusal

**A guard that fails and a guard that is bypassed look identical from outside**, and only one of
them is safe to discover by running it. Checking a refusal by executing the script that writes is
how a pass ends up running a known writer against a live store.

Reading is also faster and more correct. One guard could never fire for a structural reason visible
in four lines of source and invisible from outside: an environment loader ran first and populated
every variable the guard checked for.

**And a negative control that does not remove the input proves nothing.** Clearing one home-directory
variable does not neutralise path expansion on a platform that reads a different one.

**Settle it adversarially instead, and it is cheap.** Break the thing by one character, run the
suspected guard, see whether it fails, restore and confirm with a byte comparison. That takes a
minute and replaces an argument with a measurement.

### Before reporting that something is ungated, find the oracle

A verifier is deliberately **not** next to the thing it checks — a producer grading its own homework
catches nothing its own reader gets wrong. So a check placed away from its subject looks exactly
like absence to anyone who searches beside the subject. Search the whole test surface for the
subject's name, and grep for the behaviour rather than the expected spelling: a heuristic that looks
for a particular helper's name will miss a test that reads the real tree by calling the function
with no arguments at all.

Likewise, **enumerate the gates from the tree every pass, never from memory.** Discover them by
their shape — an executable check with a paired test — and count them. A pass once ran ten while the
tree held fourteen, and one of the four it never ran was red on a live outage that every other gate
and every test suite was green through. **A gate absent from the list the pass reads is a gate
nobody runs.**

### Pin a baseline against the committed tree, never the working tree

A local run answers *what does my machine hold*; a ratchet asks *what did we agree to*. They differ
by exactly the work in flight, and that difference is invisible until CI finds it. Numbers set from
a working tree with uncommitted edits in it turn CI red on arrival.

**But a CI materialisation is not the whole workspace, and the difference will lie to you.** A link
check measuring dozens of failures against the committed tree and zero against the working tree
looked like an uncommitted-work dependency; every failure actually pointed into a tree the CI
runner does not materialise. The links were fine and the tree they were measured in was incomplete.
**Before trusting a committed-tree reading, check that the check stays inside what CI materialises.**

Reproducing a CI red is cheap when a gate accepts a root — most do, via an explicit argument or a
root-taking entry point. Check the signature before assuming a gate can be redirected; more of them
take a root than you expect, and the ones that cannot are the exception worth naming.

### Another agent may be editing the same tree right now

A measurement taken mid-edit is not a finding. A lint check going red with undefined-name errors in
a freshly authored file returned all-clear two minutes later — the file had been photographed
half-written.

Before raising anything: check `git status --porcelain` for files you did not touch, and check
mtimes. **Seconds-old mtimes on files you did not write mean re-measure, not report.**

The corollary is kinder than it sounds: when a gate goes red immediately after someone else's work
lands, the first hypothesis is *"they are still typing"*, not *"they broke it"*.

**And the inverse holds.** Before calling a failure transient because it will not reproduce, ask
whose change caused it and whether the file moved under you — somebody may have repaired it in
between. One `ls` with timestamps settles it.

### Run the whole suite of any repo you touch, even for a two-line change

You are checking the tree, not your diff. Removing one dead line from each of six test files passed
per-file and could only be cleared by the full run, because the thing removed was a global side
effect. That run also came back with a failure that was not this pass's: a sibling repo had been red
at HEAD for hours and nothing had said so. A red suite nobody has run is indistinguishable from a
green one.

**And prove a failure is pre-existing before you say so** — park your edits, restore those files
from `HEAD` with `git show HEAD:<path> > <path>`, reproduce. Never stash: it round-trips text, and a
stash cycle has flipped every line ending in a file. Restoring with `git show` writes one named file
and cannot take anything else with it.

### Edit bytes, not text

A workspace holds both CRLF and LF files, sometimes side by side in one directory. Reading a CRLF
file as text and writing it back converts the whole file, turning a two-line repoint into an
800-line diff that buries the real change. **Read bytes, write bytes**, and if you must use text,
pass an explicit empty newline translation.

**The default text write is the trap**, not just the read: on Windows it translates line endings on
the way out, so every file written that way flips. That is how one pass converted 52 files across 14
repos having written this very rule the same morning.

**It hides in two ways and only one is visible.** In a repo with no line-ending attributes the diff
inflates — a one-line change shows as 85 insertions and 85 deletions. In a repo that declares LF,
git normalises on comparison so the diff stays clean **while the working tree holds the wrong
bytes**, which is precisely what breaks a fresh CI clone. **A clean `git diff` is not evidence that
the endings are right.** Compare the working tree against the blob with newlines normalised, and
flag where one holds CRLF and the other does not.

**Read the diffstat after every batch of fixes** — a fix whose diff is larger than the fix did
something you did not intend.

### Put no escape in the source at all

A backslash escape written through a shell layer loses a backslash and becomes the raw character.
This defect reproduced itself four times in one task, each time one layer further out: the script,
then the document explaining the fix, then the repair of that document (replacing a NUL with a NUL —
a silent no-op reporting success), then the detector added to catch it, whose own source would no
longer parse.

The rule that works: build the byte from character codes, and build the *text of an escape* from
character codes too. Then no layer can eat anything. For multi-line content, write the file with a
tool that takes no shell layer.

**And a backtick inside a double-quoted shell string is command substitution.** A workspace whose
prose is full of backticked identifiers hits this constantly: the substitution fails, prints to
stderr, returns empty, and the sentence ships with a hole in it while the write reports success. Use
a quoted heredoc, which interprets nothing. **Never pass markdown through `-c "..."`.** Read back
what you wrote — a mangled string looks like success from the exit code alone.

### Never undo a wildcard copy with a wildcard delete

Staging backups with a glob copy and then "cleaning up" with a glob delete removed twelve real
modules from a source tree. **The glob does not remember which files the copy put there.** Restore
by explicit path, one name at a time, or copy into a scratch directory that contains nothing else.

It was recoverable only because the files were committed and `git status` named exactly what was
missing. **Check `git status --porcelain` before and after any bulk file operation**, and treat a
deletion you did not intend as a stop-the-line event.

### A comment about a removed line still contains that line's text

Twice in one session: a paragraph explaining a broken path re-introduced the path and turned a path
gate red, and a guard asserting a call was gone tripped on the replacement comment that *mentioned*
it. When you assert that something is gone, assert it against the **code** — strip comment lines
before matching — not against the whole file.

### A line number that still resolves is the worst kind of stale reference

It reads as verified. One citation named a file that had been moved to a flatter path *and* a line
range that now held unrelated code; a reader who followed it would find real code and conclude the
citation was fine. When you repoint one, **name the enclosing function and drop the line number** —
the name is the durable half, and it survives a refactor that moves the code hundreds of lines.

### Treat a file that lands in many repos as a broadcast, and pre-flight it

A shared or generated file written into every repo carries whatever you put in it to all of them at
once. A clause that is true and useful in the repo you are thinking about can violate a naming rule,
or an evidence rule, in a sibling. **Name the seam, not the product.**

The question to ask before writing in such a file is not *is this true* but ***is this sayable in
every repo at once***: no brand a sibling may not name, no figure without a source, no path that
must resolve from a directory it will never be read in. The blast radius is usually small enough to
check in about a minute — the naming gate, the path gate, and the one sibling suite that holds every
quoted figure to a line in its findings file. Find those by searching; the set changes.

### A value with no durable home cannot stay put

Restoring a configuration value by hand is not a fix. One credential was restored by hand into a
generated file twice and destroyed both times — the file says in its own header that it is
generated. When something goes missing twice, stop restoring it and ask **where it is supposed to
live**. If the answer is "a generated file", that is the bug.

**Establish a configuration value by measurement where you can.** Four candidate key files existed;
tested individually against the affected data, two worked and two did not, and the two that worked
were byte-identical. That is a measured answer. Picking the plausible-looking path would have been a
guess that happened to be right or wrong silently.

**A failure that surfaces as the wrong kind of error hides from everything.** A rotated content key
rewrites nothing already on disk, so earlier-era blobs fail an authentication tag check and surface
as *missing object*. When you meet a gate whose subject nothing else touches, that is not
redundancy — it is the only witness.

### Read the module that owns the data before tuning the thing that reads it

When something is slow, the first question is not "how do I tune this query" but "what does this
subsystem already do instead of scanning?" One gate read millions of rows to count a few hundred
defects while the store it read already maintained those counts as O(1) counter rows, offered a
paged accessor documented as *never a scan*, and split cheap-check from full-recompute. The gate had
opted out of all three, and hours went into tuning before anyone read the owning module.

**A composite index is only usable from its leading column.** A cursor-windowing scheme was reported
as "measured worse" when the query had dropped the leading column, so the index was dead and the
engine scanned. Correctly scoped it was three orders of magnitude faster. **Print the query plan
before you believe any timing**; if it says scan where you expected a search, the measurement is
about your query, not about the idea.

**Measure cold and warm, and say which.** A cold read of a large store can be several times its warm
cost.

### Re-measure an inherited item before working it

A worksheet, punch list or audit item is a claim dated when it was **written**. Between then and
now, other sessions ship. So the first act on any inherited item is to re-measure the thing it
asserts, **before** doing the work — otherwise the pass spends its effort re-fixing what is fixed
and, worse, writes a decision record saying it did something it did not do.

Measured over one completed audit that walked every item to the end: **about one item in eight
needed no code change because the tree already did it.** The rule of thumb formed early off a small
sample held, and slightly understated the effect, when the denominator grew threefold — which is
worth recording precisely because this pass's usual result when a denominator grows is the opposite.

Count the already-done by what each **decision says**, never by grepping the word: in that audit,
sixteen decisions contained "already" and only thirteen meant *the item needed no code*. Counting
the word would have published the wrong rate.

### For everything changed in the window, check that its neighbours followed

For every signature, class, CLI flag, environment variable, config key or schema field changed in
the window:

- **Callers** — every call site updated, including in other repos and in working-floor scripts.
- **Tests** — a changed behaviour with an unchanged test is either an untested change or a test
  asserting the old behaviour. Both are findings, and they are *different* findings.
- **Docs and docstrings** naming the old shape.
- **The other end** — a changed writer with an unchanged reader, a changed schema with an unmigrated
  store, a changed request with an unchanged response.

Then, restricted to lines **added in the window**:

```sh
git -C <repo> diff <last_head>..HEAD -U0 | grep -nE '^\+.*(TODO|FIXME|XXX|HACK|WIP|temporarily|for now)'
```

Each one gets an owner and a finish line, or it is a finding. A "temporarily" from three weeks ago
is a permanent decision that nobody made. Likewise: **commented-out code added in the window**, a
feature flag with one branch never taken, a compatibility shim whose old path now has no callers,
and a migration script that has already run and is still wired in.

---

## 4. The detectors

Run all ten, **in this order**, every time. Fixed order is what makes two reports diffable.

Each detector below says what to measure. **Compose the sweep yourself** and apply the prune set from
§2 during the descent. A number a sweep prints is *what the tree contains*; it is never *what that
means*. An orphan may be a deliverable that never landed or a script reached by another name; a
duplicate may be a governed vendored copy or a shadow. **A finding raised from a count alone is a
count with a file path attached.**

### D1 · GENERATED — a generated file that no longer matches its source

Grep the changed set for generated-file banners ("generated", "do not edit", "autogenerated") and
check each against the source it names. **Read the whole file, not its head** — a banner further
down is the case a head-only read misses.

A hand-edit to a generated file is a finding **and the edit is a message** — someone wanted that
change. Report where it belongs in the source; do not merely overwrite it.

### D2 · PATHS — a reference to something that moved

For **every path in the D/R set** of this window, across the whole workspace:

```sh
grep -rn "<old-basename>" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=__pycache__
grep -rn "<old-import-path>"                          # module path, not just the file name
```

Cover all four reference kinds — they break independently:

1. **Imports** — module paths, JS/TS specifiers, C includes, packaging entry points.
2. **Markdown links**, relative and absolute.

   **Skip fenced blocks and inline code spans, or the checker reports its own examples.** A document
   that *discusses* link syntax — this file, a gate's docstring, a note proposing the very check —
   contains link syntax as prose. Blank out code spans and skip fences before matching.
3. **Scripts and config** naming a file — CI workflows, container files, test config, build files.
4. **Env vars and config keys** — a renamed key with a reader still looking for the old name fails
   *silently*, which is the worst kind.

**When a reference is stale, check whether its target changed too — not just its address.**
Repointing an address is the tidy-looking fix and it is sometimes the wrong one, because a document
can be stale in two independent ways at once:

- A rule warned *"do not strip dates"* and cited a prompt. The prompt had moved **and** its successor
  had reversed that position. Repointing the path alone would have preserved a false claim, making
  the document *more* wrong.
- A script's usage line named both a wrong path and a wrong argument, and the combination was
  harmless because the path failed first. **Fixing the path alone would have armed a `--yes` against
  a writable store.**

Ask of every repoint: *if this address were correct, would the sentence around it be true?* If not,
the sentence is the defect and the address is a symptom.

**Two classes must never be repointed.** A **vendoring attribution** records where code came from
when it was taken, not where to find it now — repointing turns a dated provenance record into a
false claim about today's tree. And **shorthand** — a repo's short name standing in for its full
directory — is a naming convention, not a defect.

A **forward reference** — a plan naming a file it exists to create or delete — is not a finding.
Never "repair" a reference into a lie.

### D3 · SHADOW — two implementations of one job

Byte-identical duplicates are the easy half: hash every file and group. **The class that matters is
the near-duplicate — two implementations that have begun to drift.** Measure it by shingling rather
than by eye: fixed-token windows at a stride, hashed, compared by Jaccard over the sets, bucketed by
the lowest K shingles so you are not comparing every pair.

**Set K high enough that an absence means something.** One run used four min-hashes, yielded a
hundred-odd candidate pairs, and found nothing; at K=32 the candidate set was fourteen times larger
and returned the same results — which is what made the zero worth reporting. **A negative result is
only worth the scope that produced it.**

For every path in the **A set** of this window: does a file of that basename, or that job, already
exist elsewhere?

Then check the standing shadow surfaces. **Derive them each run** rather than reading a list: any
pair of paths where one is a copy, a shim or an installed image of the other.

- A shim and its runner — shims carry **no logic**; behaviour lives in the one runner.
- Any second home for a reusable pass. One home per pass; a second copy diverges before anyone
  notices.
- A source tree and its installed copy. `diff -rq` them.
- Vendored trees, against whatever rule governs them.
- Any second manifest of the same thing. One manifest; a subset is a filter argument.

Report a shadow as: which copy is authoritative, why, and what the other must become — a re-export,
a deletion proposal, or a documented fork with a stated reason.

Two implementations that **agree today** are still a finding. The cost lands the day they stop.

### D4 · UNPROPAGATED — the fix that landed in one sibling only

This is the detector that pays for the pass. **Discover the sibling sets from the tree** — a set is
any group of directories with parallel structure and a shared contract — and ask of every change in
the window: is this specific to this member, or is it an improvement the whole set wants?

The recurring shapes: a family of SDKs in different languages sharing a wire protocol, vocabulary
and error taxonomy; a family of agents sharing a host seam; a set of applications over one library,
where an application carrying its own copy of a primitive the library now exports is a finding; a
set of gates sharing idioms, where a better one is a template for the rest; and a source tree with
its installed copy.

Where a checker covers one dimension of a set's agreement, **know what it does not cover** — a
vocabulary check says nothing about retry behaviour, and reading it as "the set is in step" is how
drift survives a green gate.

**A measurement change is not a refactor.** A port that silently swaps one statistical edge for
another changes results while looking like tidying. Before proposing that an improvement be
propagated, say **what number changes** in each destination — and if a number changes, that is a
proposal for the owner, never a fix this pass makes.

### D5 · LEFTOVER — a change that stopped halfway

**Undefined-name is the highest-value lint class in this workspace, because a swallow can hide it
for a month.** Run it deliberately, per repo, with your linter's undefined-name rule selected.

The shape to look for is *fail-soft and fail-silent*:

- A function missing a module-scope import, so every call raises into a bare `except: pass`. One
  such checkpoint helper was invoked three times per ingest and **had never once executed**.
- A module using a constant it defines nowhere, both uses inside `try` blocks. **The entire feature
  had never worked** — nothing published, nothing read — while its docstring promised otherwise.

**Fail-soft is right; fail-silent is what makes it undebuggable.** A swallow that never logs turns a
crash into a feature that quietly does nothing, and nothing in a test suite or a gate will say so.

### D6 · DANGLING — nothing points at it

**Before raising anything, ask whether the published corpus already answers it — with a date.** This
pass once reported an unreferenced module as worth a decision when canon had recorded the same
condition four weeks earlier: *"the base object is built but unwired."* The finding was late and said
less than the document it duplicated. Grep the corpus for the symbol before writing the finding — a
condition canon already states with a date is a **planning fact**, not a hygiene defect.

- **Files with no inbound reference** — start from the window's A/R set, then sweep wider on a full
  run. Not everything needs an inbound edge (entry points, fixtures, docs); say which kind it is.
- **Tests for modules that no longer exist**, and modules with no test that once had one.
- **Litter**: backup, retired, old, original and reject suffixes; empty directories; stray caches in
  a tracked tree. Cheap to find, and they hide real files.
- **Declared-but-unused dependencies**, and the reverse — an import with no declaration, which is the
  one that breaks a clean install.
- **Dead exports** — a public symbol with no consumer inside or outside its repo.
- **Orphaned lab threads.** A lab directory is the code half of a worklist document. Three findings
  live here: a lab directory whose document was promoted or archived (the code should have moved with
  it, into a repo **with a test**); a worklist document whose lab half is gone; and lab code that has
  quietly become the only implementation of something a repo needs. Report these; the move itself is
  `doc-triage`'s call.

**Propose, do not delete.** Nothing here is deleted by a scheduled pass. See §5.

### D7 · CLAIM — prose the tree stopped supporting

For prose changed in the window **and** for prose *about* code changed in the window: does the tree
still support it? Check the tree that is supposed to be true **today** first — it goes stale fastest.
Where the corpus marks its claims (measured, sourced, carried), an unmarked flat statement is a
finding.

**Never strip a dated note or an attribution.** A dated claim stays true forever. Where prose has
gone stale, the fix is a superseded banner or a measured update — never a deletion.

**The assistant's own memory for this project is in scope, and it is the highest-leverage prose in
the workspace.** It is loaded as background context at the start of every session, so a memory that
has gone stale steers the next session before it has read anything — and unlike a docstring, nothing
else reads it, so nothing else catches it. Every memory naming a file, function, flag, path or count
is a claim this detector checks like any other.

The rules that differ from ordinary prose: a false memory is **deleted**, not softened, with the
evidence that disproved it named; a drifted one is corrected against the code while keeping its
`name`, so inbound links still resolve; and its absolute dates are content rather than the dated
attributions the prose rules strip. The index must match the directory both ways. A memory that
only restates what the repo already records is redundant rather than wrong — delete it and say so.

Locate it by listing Claude's per-project state directory and matching the target's path; sweep no
other project's memory.

### D8 · GATES — run them, never edit them

Enumerate the gates from the tree (see §3), run every one, and report each gate's **number and its
direction since the last run**. A baseline that rose is the headline finding of the run, named
together with the change that raised it.

**Never edit a baseline to make a number go down.** A baseline shrinks only by fixing what it counts.
If a new invariant needs pinning, it is pinned at what it measures **on the day it lands** — never at
a figure quoted from an earlier pass.

**Time every gate, and treat cost that grows with the data as a defect.** The posture is a finite
aperture over infinite data: a check whose cost tracks the size of the store rather than the size of
the problem is wrong in shape, however fast it runs today. Ask of anything slow: *is it O(data) or
O(answer)?*

Also confirm any always-on capture or memory lane is actually working before trusting anything
downstream of it.

### D9 · CONFIG — what could not be restored

- **Untracked configuration.** Every run: what configuration exists on disk that no repo would
  restore?
- **The committed/ignored environment split.** The committed environment file carries no credential;
  the ignored one beside it does. A credential in a committed file is the top finding of the run,
  above everything else in the report.
- **Credential-shaped strings added in the window** — keys, tokens, connection strings, private
  hostnames or LAN addresses in a repo that has a public remote.
- **A secrets tree still has no `.git`.** That absence is the whole protection; confirm it every run.
- **Manifest against disk** — a repo on disk that the manifest does not list is a repo nobody pushes,
  and nobody is told.
- Installed copies in step with their source (see D4).

### D10 · BOUNDARY — a repo doing another repo's job

Check the window's changes against the roles the workspace's own rules assign:

- Product code in a repo that ships none.
- Logic in a shim rather than in the one runner.
- Implementation in a repo that carries configuration only.
- A second implementation of something another repo already owns.
- A new top-level directory for documents. There is one path; another place is another place for the
  truth to be.
- A working tree growing product code. It is a working tree, not a product.

---

## 5. What the pass may fix, and what it may only report

**Tier A — fix it, in the working tree, and list what you did.** Mechanical, reversible, and provably
correct on the evidence already gathered:

- Regenerate a generated file from its source — **after** carrying any hand-edit back into the source.
- Repoint a reference whose target moved, where the new target is **unambiguous**.
- Fix a broken relative link with exactly one candidate.
- Add a missing dependency declaration for an import that is already there.
- Correct a docstring or comment that names a shape the code no longer has.

**Tier B — report only, with a recommendation.** Anything that deletes, merges, changes a number, or
decides something:

- Deleting any file, litter included. **Propose the list; the owner runs it.**
- Merging two implementations, or picking which one survives.
- Re-pinning any baseline.
- Any change that alters a measured result.
- Moving a document between trees — that is `doc-triage`'s call.
- Anything touching a secrets tree, live infrastructure, or a deploy.

**Never, unless asked in those words:** commit · push · deploy · restart a service · run containers ·
install packages · touch live infrastructure · create a remote repo · delete anything · edit a gate
or its baseline. This pass ends with a dirty working tree and a report. That is correct.

---

## 6. The report

Write `REPORTS/TIGHTEN-<date>.md` under the state directory, with these sections, **always in this
order and always present, empty ones included** — a section that is absent reads as a section that
was skipped:

```
# Tighten — <date>
Mode: full | incremental · Window: <last run> → now · Repos: <n> · Commits: <n>

## Headline            the one thing to act on, or "nothing above the line"
## STALLED             open >= 5 runs. Fix or accept; drifting is not an option
## Fixed this run      Tier A edits made, file by file, with the reason
## New findings        by detector D1..D10, each with its ID, evidence, and Tier
## Carried             open findings, with recurrence counts, one line each
## Closed              findings verified gone since the last run
## Accepted            one line: "N accepted findings not re-litigated"
## Gates               each gate, its number, and the direction since last run
## Coverage            what was NOT examined this run, and why
```

**One report per day, not per run, when this is running as a loop.** At a ten-minute cadence "per
run" is the wrong unit — twenty-one reports in a day is noise, and the one time this pass met that
ambiguity it wrote **none**, which is worse. The ledger takes a line per run and the report
consolidates the day. Write it, or amend it, on every iteration; the ledger tells you which
iterations it must cover.

Then append one line to `LEDGER.md` and write the state file back.

**The Coverage section is not optional.** A detector that was deferred, a repo that was skipped, a
budget that ran out — name it. Silent truncation reads as "covered everything", which is how a report
stops being read.

---

## 7. Running it

    /tighten                    incremental, since the last run
    /tighten full               every detector over every repo, ignoring state
    /tighten <repo>             one tree only, still against the last run
    /tighten D4                 one detector, when chasing something specific

To run it on a schedule, use the `schedule` skill or `/loop`. Do not build a second scheduler.

**Do not extract this pass into a script.** Its sweeps are composed per run against the tree as it
is; a frozen copy answers last month's question and hides the widening that finds the defect. Where
one measurement genuinely earns permanence, it becomes a **gate** — an executable check with a
paired test, beside the other gates — not a private scanner this skill calls.
