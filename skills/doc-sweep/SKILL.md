---
name: doc-sweep
description: Run the current-state prose pass across a whole workspace rather than one document - rank the tree by narration density, cut the list down before spending anything, then hand files to subagents one at a time, gated by a code digest so a rewrite cannot change code. Use when many repos have accumulated narration, after a fast-change period, or when doc-current-state would take too long by hand. Prose only; it changes no code.
---

# Doc sweep — the current-state pass, at workspace scale

`doc-current-state` states what the prose should say. This states how to get there across hundreds
of files without breaking anything, and it exists because doing it by hand does not finish: on one
such pass the first six files took the effort of a small refactor, with hundreds still flagged.

**Read `doc-current-state` first.** Its Keep and Delete lists are the rules; nothing here replaces
them. What this adds is the ranking, the cuts and the harness.

**Everything here is composed at run time.** There is no tool to install and no worklist committed
to a tree. Every command below is one you build from the rules on the day, against the tree as it
actually is — which is the point, because a checked-in sweeper goes stale exactly where a stale
sweeper is most expensive.

## The split — two jobs, and only one is fan-out work

| | rewrite | stale facts |
|---|---|---|
| the work | shouting and change-history phrasing into present-tense properties | prose that contradicts the code |
| needs | the flagged block, and the code it describes | reading the code properly |
| suits a subagent | yes | no |
| what it is worth | the tree reads like one voice | this is where every real defect was found |

Keep them apart. One measured pass found a route a module header still advertised after it was
deleted, a docstring describing a branch its function does not contain, a test naming a path
template that had changed, and an evidence file whose removal turned twenty-one tests red. **Every
one came from reading the code, none from matching a pattern.**

So the agent **reports** a suspected stale fact and never acts on it. A plausible rationale that is
wrong is worse than an absent one, and an agent asked to tidy prose will write one confidently.

## 1. Inventory and rank

Walk the target, excluding vendored, cached, generated, secret and archived trees, and rank by how
many Delete-list markers each file carries. Build the pattern from `doc-current-state`'s Delete
list, not from memory.

```powershell
$skip = '\\(node_modules|dist|build|\.git|obj|bin|\.venv|venv|__pycache__|\.pytest_cache|\.ruff_cache|\.next|_archive|_secret)\\'
$files = Get-ChildItem <TARGET> -Recurse -File -Include *.py,*.ts,*.tsx,*.js,*.jsx,*.cs,*.c,*.h,*.md |
  Where-Object { $_.FullName -notmatch $skip }

$pat = '(?i)\b(previously|no longer|formerly|used to|for now|hopefully|should work|turns out|20\d\d-\d\d-\d\d)\b'
Select-String -Path $files.FullName -Pattern $pat |
  Group-Object Path | Sort-Object Count -Descending |
  Select-Object -First 40 | ForEach-Object { "{0,5}  {1}" -f $_.Count, $_.Name }
```

**Rank every language, rewrite only what you can verify.** A file in a language you cannot parse
into an AST still belongs in the ranking — without them the list is blind to whole repos, and a UI
tree that is almost entirely shouting never appears at all. It just gets a stricter harness
(see §4).

**Group the hits by kind, not just by count**, because eighteen dates and eighteen shouted headers
are not the same hour. Run the caps pattern separately from the change-history one and report both
per file. Shouting is always rewritten. A date inside a gate or a baseline is usually that
baseline's provenance — *first pinned on <date> at what each tree measured* — and the Keep list
protects it, so a date-dominated row is a small correct diff, not an hour. Send the caps-dominated
rows first.

### Claude's memory is a surface of this sweep, not a separate job

The assistant's own memory for this project is prose that makes claims about the code, and it drifts
the same way a docstring does — with one difference that makes it worse: **nothing reads it but the
assistant, and it is loaded as background context at the start of every session.** A wrong docstring
misleads whoever opens the file. A wrong memory misleads every future session before it has looked
at anything.

It lives under Claude's per-project state directory, one directory per working directory Claude has
been run in, named after that path. **List the projects directory and pick the one matching the
target rather than guessing, and sweep no other project's memory.** Its index file is one line per
memory, never content.

Rank it with the rest, and apply `doc-current-state`'s Keep and Delete lists, plus:

- **Verify before rewriting.** A memory naming a file, function, flag or path is a claim about the
  code. Check it against the code, not against the memory's own confidence.
- **A false fact is deleted, not softened.** Remove the file and its index row, and name the evidence
  that disproved it. Hedging a wrong memory leaves it in circulation.
- **A drifted fact is corrected** against what the code does now, keeping the same `name` so inbound
  `[[links]]` still resolve.
- **Dates stay.** A memory's absolute date is its content — when a thing was measured or decided —
  not the dated attribution the Delete rules strip from source prose.
- **The index must match the directory**, both ways, and every `[[link]]` names a memory that exists
  or is deliberately yet to be written.
- A memory that only restates what the repo already records — structure, a past fix, git history,
  the project's own instructions file — is redundant rather than wrong. Delete it and say so.

**Do not hand memory to a fan-out agent.** Each file is one fact, and the work is verifying that
fact against the code — which is the stale-facts job, not the rewrite job, and §"The split" says why
that half does not fan out.

## 2. Cut the list before spending anything

Three cuts, in order. They routinely take a flag list down by more than five to one.

**Fix the pattern before trusting its output.** A ranked list is read by someone deciding where to
spend an hour, so a phrase that is wrong more often than right costs more than it catches. Phrases
like *it was*, *corrected*, *rewritten* and *caveat* raise mostly ordinary English. Sample twenty
hits of any phrase before it earns a place in the pattern, and drop the ones that fail.

**Record the ones you measured and kept.** The loosest phrase to survive this test is *no longer*,
about half of whose hits are a condition a checker looks *for* — "a generated file that no longer
matches its source" — rather than a change the code went through. No lexical rule separates the two
senses, and splitting on a preceding relative clause came out near fifty-fifty, which is no signal.
It stays, because the other half is real and a reader tells them apart at a glance. **Report a
measurement that produced no rule**, so the next pass does not re-derive the same non-result.

**Skip the dated records, and the benches with them.** A ledger, a build log, a dated report, a live
worksheet on the working floor — the dates are the content and a date sweep destroys them. These are
few files carrying an enormous share of the hits, every one of which should stay. Recognise them by
what they are for, not by where they live: one-shot bench code is the same kind of thing one step
down, and left in, it dominates the list and sends a person to the least durable prose in the
workspace. A bench script that stops being one-shot moves into the repo it acts on, and is swept
there.

**Take the head, and say what you left.** The distribution is steep: a small head carries most of
the markers and a long tail carries a handful apiece, mostly one incidental date or phrase. Working
the head and reporting the tail with its size is the pass finishing; working the tail is the pass
never finishing.

## 3. One file per agent, never a repo

The failure mode is an agent rewriting prose about code it has not read. Give it one file and
nothing else to do.

```
Rewrite the narration in ONE file. Prose only — change no code.

File: <path>

Find the lines yourself, then read the WHOLE file before editing anything,
including the code the prose describes:

    grep -nEi '(previously|no longer|formerly|used to|for now|hopefully|should work|turns out|20[0-9]{2}-[0-9]{2}-[0-9]{2})' <path>
    grep -nE '^[^a-z]*[A-Z]{4,}' <path>

REWRITE, in place:
- ALL-CAPS sentences and headers → ordinary case
- change history ("used to", "no longer", "previously", "this said X until
  <date>") → state what is true now, as a property
- dated attributions in code docstrings → drop the date, keep the fact
- failure narration, self-justification, hedging, defensive framing → drop
- emphasis and prohibition glyphs → drop, or state the rule they shout

KEEP:
- a measurement that justifies a decision ("measured 2.048s vs 0.018s, so
  this uses the loopback address") — deleting it invites the change back
- every figure WITH its qualifier: simulated, not yet wired, measured
  before the repair. A number that loses its condition is worse than one
  deleted
- every statement of a limit — "what this does NOT establish", "not yet
  measured", "halts one node short". ALL-CAPS survives inside these; strip
  the shouting from a rule, never from an admission
- a glyph a legend in the same file defines. That is a notation, not
  decoration: keep it, or replace it with the word it stands for, but never
  just delete it — dropping a state marker silently changes an item's state
- present constraints, stated positively
- correction banners: where a document records that it was wrong, that IS
  the content

NEVER TOUCH:
- string literals the program emits: schema description=, log messages,
  error detail=, user-facing text. Tests pin exact tokens inside them.
- any line that is not a comment or a docstring
- a docstring that is emitted without looking like it. A web framework
  copies a request/response model's class docstring verbatim into its
  published schema, and a route handler's docstring becomes that
  operation's description UNLESS the decorator passes an explicit
  description= of its own. In a router or schema file, check which of
  those a docstring is; skip every request/response model docstring
  outright.
- a docstring a test pins by name. Before editing one, grep the repo's tests
  for this module and for `__doc__`; a test asserting exact wording turns a
  de-shouting edit red, and neither a parse nor a code-digest check reads an
  assertion body

DO NOT INVENT. If you cannot tell why something is the way it is, say what
it does and leave the why out.

If the prose contradicts the code, DO NOT FIX IT. Finish the rewrite, then
list each contradiction under "SUSPECTED STALE:" with file:line and what the
code actually does. Someone else verifies those.

Preserve the file's existing line endings and any aligned tables. Do not
reflow lines you are not rewriting.

Do not run git. Do not commit. Do not run the suite — the harness does that
once per repo, after the batch.

Before you report, prove you lost no number. Every measured figure in this
workspace's prose traces to a claim, and a figure that quietly vanishes in a
tidy-up is the one defect this pass can cause that nothing downstream catches:

    git diff -U0 -- <path> | grep '^-' \
      | grep -oE '[0-9]+\.[0-9]+|[0-9]+%|[0-9]+/[0-9]+' | sort -u > before.txt
    grep -oE '[0-9]+\.[0-9]+|[0-9]+%|[0-9]+/[0-9]+' <path> | sort -u > after.txt
    comm -23 before.txt after.txt      # must print nothing

A number that loses its qualifier is worse than one deleted, so when you move a
figure, its condition moves with it: *simulated*, *not yet wired*, *measured
before the repair*.

Report, and nothing else:
1. FILE
2. MARKERS: n before -> n after, from re-running the two greps
3. KEPT: each marker you deliberately left, with why
4. NUMBERS LOST: the comm output, which must be empty
5. SUSPECTED STALE: file:line + what the code actually does, or "none"
```

**Edited in place, never printed back.** Handing the whole file through the report doubles the cost
of every large file and puts a transcription between the agent's judgement and the disk, while the
harness reads the disk anyway.

## 4. The harness — do not trust the output, check it

The one check that matters is a **code digest**: a hash of the file's code with every docstring
blanked. Comments never reach an AST, so two files with the same digest differ only in prose. It is
the only thing that catches an agent quietly editing code, and it costs nothing.

```powershell
# digest one Python file — run over the head before the batch, and again after
python -c @"
import ast, hashlib, sys
tree = ast.parse(open(sys.argv[1], encoding='utf-8').read())
for node in ast.walk(tree):
    if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        if ast.get_docstring(node):
            node.body[0].value = ast.Constant('')
print(hashlib.sha256(ast.dump(tree).encode()).hexdigest())
"@ <path>
```

```
before the batch:
    the digest of every parseable file in the head   > digests.before
    the suite of every repo you are about to touch   > the baseline failures

per file, worst first:
    run the agent

after the batch:
    the same digests, compared to digests.before
    a digest that moved means prose work reached code — revert that file

per repo:
    the repo's own test suite   catches an edited emitted string
    a compile or build step     for languages with no AST check: a comment marker
                                landed in code will not compile
    the repo's own prose gates  any count of unresolvable references must not go UP

collect every SUSPECTED STALE for a human pass
```

**A language you cannot digest gets a stricter gate, not a looser one.** Where there is no AST to
compare, the compile step is the digest, and every diff is read by a person before the batch is
called done.

**Take the baseline before the batch, not after.** These trees carry several sessions' in-flight
work, and a repo mid-restructure is red for reasons a prose pass did not cause — moved config, a
deleted module, a lint baseline raised by another session's new code. Without the before-reading
there is no way to say so rather than guess it.

## What goes wrong

- **Emitted strings.** This is the one that will cost a suite. Tests pin literal tokens inside
  published descriptions — a capitalised word, a phrase a client must be told. An agent tidying
  those breaks tests and cannot see why. The rule is not "be careful with strings", it is *comments
  and docstrings only*.
- **A docstring that is not a comment, and is still emitted.** *Comments and docstrings only* is
  necessary but not sufficient. A web framework reaches two docstring shapes by a path no syntactic
  rule can see: a request or response model's class docstring is copied verbatim into its published
  schema, and a route handler's docstring becomes that operation's description whenever the
  decorator has no explicit one (an explicit one wins outright and the docstring goes unused).
  Confirm which behaviour your framework version has by calling it, not by memory. Either shape is
  off limits regardless of what the ranking says.
- **A file whose subject is the thing being removed.** These skill files quote a dated removal
  marker as an example of what to delete. A sweep over one deletes the instructions rather than
  following them. Exclude the skills tree, and any file that documents a pattern by showing it.
- **Line endings and alignment.** A rewrite rebuilt with a bare newline turns a CRLF file mixed one
  comment at a time, and a whitespace tidy-up applied to every line reformats aligned tables while
  removing nothing. Neither is visible to a syntax check or to a code digest. Both have shipped.
- **Concurrent sessions.** Several sessions work these trees. A staged change is a change the next
  person's commit carries, including a staged deletion. Read and write inside one script, and check
  `git status` before concluding anything about what you changed.
- **A docstring can be pinned too, not just an emitted string.** One contract docstring's shouted
  word was asserted verbatim by a test whose whole purpose was to stop that docstring drifting back
  to a prior wrong claim. De-shouting the word is exactly the edit this pass makes by default, and
  it broke the test. The tell is the test's own name or docstring naming "docstring" or quoting the
  exact prior wording — run the file's test suite after every rewrite; a green parse and a matching
  digest are not sufficient on their own, since neither reads assertion bodies.
- **A stale claim reads exactly like provenance.** One pass found four documents asserting that a
  section "was never written" when it had been present all along, and a vocabulary document accusing
  a README of printing two licences backwards when the README matched the actual licence files. Both
  had survived earlier passes because a confident, specific, internal-sounding statement looks like
  something to preserve. Before deleting a claim as stale — or acting on one — check the tree. An
  agent told a false fact will act on it faithfully.
- **Shared boilerplate must not be handed to parallel agents.** Where several documents carry an
  identical cross-reference block, independent agents produce several divergent versions of it. Fix
  a duplicated block once, centrally, and tell every agent to leave it alone.

## Report

Files touched, markers before and after, phrases you measured and dropped from the pattern, stale
facts found and who verified them, the tail left with its size, and the suite and digest results per
repo. **Leave all changes uncommitted.**
