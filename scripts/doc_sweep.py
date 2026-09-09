"""Mechanical half of the current-state documentation pass.

Applies only the deletions that are always safe, and flags everything that needs a sentence
rewritten. It never edits a string the program emits: for Python it rewrites `tokenize` COMMENT
tokens and `ast` docstring nodes and nothing else, so an OpenAPI `description=`, a log message and
an error string are all out of reach.

    python doc_sweep.py <path> [...]            report what would change, write nothing
    python doc_sweep.py --write <path> [...]    apply the safe deletions
    python doc_sweep.py --flags <path> [...]    every flagged line, as `path:line kind hit`
    python doc_sweep.py --worklist <path> [...] the ranked set worth a person's time: dated records
                                                dropped, thin tail counted rather than listed
    python doc_sweep.py --shape <file.py> [...] a digest of the file's code with docstrings blanked

`--flags` prints line numbers because that is what the rewrite is handed: one file, its flagged
lines, and nothing else to do. `--shape` is the gate on what comes back — capture it before the
rewrite, compare after, and a digest that moved means prose work reached code.

Python comments and docstrings are rewritten. C-family sources (`.ts`, `.tsx`, `.js`, `.jsx`,
`.mjs`, `.cjs`, `.cs`, `.c`, `.h`) are scanned for flags and never rewritten: their comments are
found by a scanner that tracks string literals, which is enough to rank a file for a person and not
enough to edit one safely.

The split is the point. `apply` removes emphasis glyphs, audit tags and dated attributions, which
carry no meaning a reader needs. `flag` reports ALL-CAPS shouting, change-history phrasing and bare
dates, because removing those leaves a broken sentence: "this said X until <date>" is not repaired
by deleting the date. Those are rewritten by hand.

Reads with `utf-8-sig` and writes the BOM back where one was found, because several sources in this
workspace carry one and stripping it is a change nobody asked for.
"""
from __future__ import annotations

import ast
import hashlib
import io
import os
import re
import sys
import tokenize
import warnings

GLYPHS = "⛔⚠⭐✅⛑⚑\U0001f6ab⚡"

#: A glyph and the space after it. Applied anywhere in comment or docstring text: the glyph carries
#: no information the sentence does not, so removing it is never the thing that changes a meaning.
_GLYPH_RUN = re.compile("[" + GLYPHS + "]+[ \t]*")

#: A parenthesised or dashed review-item tag: the word "audit" followed by an item identifier, with
#: or without brackets, and with further identifiers joined by "+". The identifier names an item in
#: a review that has since closed; the sentence around it stands without it.
_AUDIT = re.compile(
    r"(?:\s*[—–-]+\s*|\s*\(\s*)?"
    r"\b(?:grants\s+)?audit\s+[A-Z]{1,2}-?\d+"
    r"(?:\s*\+\s*[A-Z]{1,2}-?\d+)*"
    r"\s*\)?",
    re.I)

#: A dated ruling attribution: the word "ruled", optionally naming who ruled, followed by a date,
#: in brackets or after a dash.
_RULED = re.compile(
    r"\s*[\[(]?\s*(?:,\s*)?(?:and\s+)?ruled\s+(?:by\s+John\s+|by\s+\w+\s+)?"
    r"(?:on\s+)?\d{4}-\d{2}-\d{2}\s*[\])]?",
    re.I)
_RULED_BY = re.compile(r"\s*[\[(]\s*John\s+ruled\s+\d{4}-\d{2}-\d{2}[^\]\)]*[\])]", re.I)

#: An empty bracket pair left behind when a parenthesised tag was the whole of it. Applied only to
#: a line that had none of its own, because a call written in prose is an empty pair too: a glyph
#: removed from a line naming `psutil.net_connections()` left the cleanup free to close it up to
#: `psutil.net_connections`, turning a call into an attribute. Leaving a stray `()` behind is a
#: cosmetic miss; changing what a name means is not.
_EMPTY_PARENS = re.compile(r"\(\s*\)")

#: A run of two or more spaces between words.
_WIDE = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")

#: Flagged, never applied. Each needs the sentence rebuilt around it.
_FLAGS = [
    ("caps", re.compile(r"\b(?:[A-Z][A-Z'’]{2,}[ ,]+){2,}[A-Z][A-Z'’]{2,}")),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    #: Only phrasings that are change history nearly every time they appear. `it was`, `had been`,
    #: `corrected` and `rewritten` were on this list and are not: they are ordinary English, and
    #: between them they raised 226 files with nothing wrong — `it was measured at`, `if it was set`,
    #: `corrected for drift`. A flag list is read by someone deciding where to spend an hour, so a
    #: pattern that is wrong more often than right costs more than the cases it catches.
    #:
    #: `no longer` stays, and it is the loosest thing on this list: 235 occurrences here, of which
    #: roughly half describe a condition a checker looks FOR — "a generated file that no longer
    #: matches its source", "tests for modules that no longer exist" — rather than a change this
    #: code went through. Measured 2026-09-07, no lexical rule separates the two senses: splitting
    #: on a preceding relative clause came out 117 against 108, which is no signal at all. It is
    #: kept because the other half is real change history and a reader tells them apart at a
    #: glance, and it is recorded here so the next pass does not re-derive the same non-result.
    ("history", re.compile(
        r"\b(?:used to|previously|no longer|formerly|until \d{4}|"
        r"this (?:said|asserted|enumerated)|"
        r"the (?:first|second|old|previous|earlier) (?:version|order|draft|pass)|"
        r"re-?pinned|WHAT CHANGED)\b", re.I)),
    ("hedge", re.compile(r"\b(?:for now|hopefully|should work|probably|seems to|temporarily)\b", re.I)),
]

SKIP_DIRS = {
    "node_modules", "dist", "build", ".git", "obj", "bin", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".next", "_archive", "_ci-work", "site-packages",
    ".mypy_cache", "htmlcov", ".tox", "vendor",
    #: Lean's package tree under `entroptics-mass-gap/research/lean` — mathlib and its
    #: dependencies, vendored rather than written here.
    ".lake",
    #: The published canon. `status/` and `genesis/` are built on dated, attributed,
    #: provenance-marked claims and are exempt from the deletions this tool makes: `status/README.md`
    #: requires every claim to carry a measured, read-from-source or unverified marker, and stripping
    #: those destroys exactly the provenance the tree exists to carry. Canon is also LEDGER-gated, so
    #: a prose edit without a ledger row puts the two out of step. Clean a document up in `_scratch`
    #: before it is promoted, never after.
    "agience-pharos",
    #: Key material. It has no `.git`, and that absence is the whole protection — a tool that
    #: rewrites files there has no business being pointed at it by accident.
    "_secret",
}
SKIP_NAMES = {"CLAUDE.md", "copilot-instructions.md"}

#: Files whose subject is the thing this tool removes, and which it therefore must not read as
#: ordinary prose. `doc-current-state/SKILL.md` quotes a dated removal marker as an example of what
#: to delete and lists the emphasis glyphs by name; this directory documents the patterns below by
#: showing them. A sweep over either deletes the instructions rather than following them — the same
#: shape as a test that has to contain the literal it forbids. This file and its test document the
#: patterns below by showing them, so both exclude themselves.
SKIP_SUFFIXES = ("skills/doc-current-state/SKILL.md",)

#: Matched on filename rather than on path, so the exclusion holds however this is invoked — a
#: suffix match on the full path misses when the tool is run from inside its own repo.
SKIP_NAMES |= {"doc_sweep.py", "test_doc_sweep.py"}


def clean(text: str) -> str:
    """The safe deletions, applied to one comment or docstring body.

    Line by line, and a line the removals did not touch is returned byte for byte. That is what
    keeps this off aligned prose: a docstring holding a table, a column of aligned comments or a
    block of ASCII art is full of runs of spaces that mean something, and a tidy-up applied to
    every line would silently reformat all of it while removing nothing.

    Where a removal did happen, a run of spaces it left behind is closed up — but only if the line
    had no such run to begin with. A line that was already aligned keeps its alignment even when a
    glyph comes off the front of it.
    """
    out = []
    for line in text.splitlines(keepends=True):
        body, eol = (line[:-len(_eol(line))], _eol(line)) if _eol(line) else (line, "")
        new = _GLYPH_RUN.sub("", body)
        new = _RULED_BY.sub("", new)
        new = _AUDIT.sub("", new)
        new = _RULED.sub("", new)
        if new != body:
            if not _EMPTY_PARENS.search(body):
                new = _EMPTY_PARENS.sub("", new)
            if not _WIDE.search(body):
                new = _WIDE.sub(" ", new)
            new = new.rstrip()
        out.append(new + eol)
    return "".join(out)


def flags(text: str) -> list:
    """What this text carries that a human has to rewrite, as `(line offset, kind, hit)`.

    The offset is counted within `text`, so a caller holding a block's first line number can report
    the line the flag is actually on. A module header is eighty lines here and a flag reported at
    its opening quote sends the reader to the top of it to search by hand.
    """
    found = []
    for name, pat in _FLAGS:
        for m in pat.finditer(text):
            found.append((text.count("\n", 0, m.start()), name, m.group(0)))
    return found


def _eol(line: str) -> str:
    """The line ending this line already had.

    Rebuilding a rewritten line with a bare "\\n" turns a CRLF file into a mixed one, one comment at
    a time — invisible to a syntax check and to an AST comparison, and it shows up as a whole-file
    diff the next time anything touches it.
    """
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def code_shape(src: str) -> str:
    """The file's code with every docstring blanked, as a comparable string.

    Two sources with the same shape differ only in docstrings and comments, neither of which
    `ast.dump` records. Comparing shapes before and after a rewrite is what proves the pass touched
    no code: a rule that reached past a docstring's quotes changes the shape and the write is
    refused, rather than the damage being found later by a test suite that may not cover the file.
    """
    tree = ast.parse(src)
    for node in _docstring_nodes(tree):
        node.value = ""
    return ast.dump(tree, annotate_fields=True, include_attributes=False)


def _docstring_nodes(tree):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            yield first.value


def sweep_python(src: str):
    """Rewrite comments and docstrings only. Returns (new_src, flagged)."""
    flagged = []

    #: Docstrings first, by line range, so the comment pass below sees final line numbers only
    #: after the sizes are unchanged — every replacement keeps its own line count.
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    edits = []
    for node in _docstring_nodes(tree):
        a, b = node.lineno - 1, node.end_lineno
        block = "".join(lines[a:b])
        new = clean(block)
        for off, kind, hit in flags(block):
            flagged.append((node.lineno + off, kind, hit))
        if new != block:
            edits.append((a, b, new))
    for a, b, new in sorted(edits, reverse=True):
        lines[a:b] = [new]
    src = "".join(lines)

    #: Comments, through `tokenize`, so a `#` inside a string literal is never seen as one.
    out = []
    changed = False
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return src, flagged
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            #: `clean` returns a line it did not touch byte for byte, so a comment carrying no
            #: glyph and no tag is left exactly as it was — trailing spaces included. Tidying every
            #: comment would put lines in the diff that this pass has no reason to change.
            new = clean(tok.string)
            for off, kind, hit in flags(tok.string):
                flagged.append((tok.start[0] + off, kind, hit))
            if new != tok.string:
                changed = True
                out.append((tok.start, tok.end, new))
    if changed:
        lines = src.splitlines(keepends=True)
        for (srow, scol), (erow, ecol), new in sorted(out, reverse=True):
            ln = lines[srow - 1]
            lines[srow - 1] = ln[:scol] + new + _eol(ln)
        src = "".join(lines)
    return src, flagged


_FENCE = re.compile(r"^\s*(```|~~~)")


def sweep_markdown(src: str):
    """Prose outside fenced code blocks."""
    flagged = []
    lines = src.splitlines(keepends=True)
    infence = False
    for i, ln in enumerate(lines):
        if _FENCE.match(ln):
            infence = not infence
            continue
        if infence:
            continue
        for off, kind, hit in flags(ln):
            flagged.append((i + 1 + off, kind, hit))
        new = clean(ln)
        if new != ln:
            lines[i] = new if new.endswith("\n") or not ln.endswith("\n") else new + "\n"
    return "".join(lines), flagged


_SH_COMMENT = re.compile(r"^(\s*)#(.*)$")


def sweep_shell(src: str):
    flagged = []
    lines = src.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        m = _SH_COMMENT.match(ln.rstrip("\n"))
        if not m:
            continue
        for off, kind, hit in flags(ln):
            flagged.append((i + 1 + off, kind, hit))
        body = clean(m.group(2)).rstrip()
        new = m.group(1) + "#" + body + _eol(ln)
        if new != ln:
            lines[i] = new
    return "".join(lines), flagged


def c_comments(src: str):
    """Comment bodies in a C-family source, as `(line, text)`.

    One pass over the characters, so a quote inside a comment does not open a string and a `//`
    inside a string is not read as a comment. Covers `"`, `'` and JavaScript's backtick template
    literal, with backslash escapes.
    """
    out = []
    i, n, line = 0, len(src), 1
    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1
            i += 1
        elif ch in "\"'`":
            quote, i = ch, i + 1
            while i < n:
                if src[i] == "\\":
                    line += src[i:i + 2].count("\n")
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                if src[i] == "\n":
                    line += 1
                i += 1
        elif ch == "/" and src[i + 1:i + 2] == "/":
            end = src.find("\n", i)
            end = n if end < 0 else end
            out.append((line, src[i + 2:end]))
            i = end
        elif ch == "/" and src[i + 1:i + 2] == "*":
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            body = src[i:end]
            for offset, text in enumerate(body.splitlines()):
                out.append((line + offset, text))
            line += body.count("\n")
            i = end
        else:
            i += 1
    return out


def scan_c_family(src: str):
    """Flag prose in a C-family source. Returns the source unchanged, so nothing is ever written.

    Ranking a file needs only to find its comments; editing one needs to be certain a span is a
    comment and not a template literal or a regex. The scanner is good enough for the first and is
    not trusted with the second, so this handler reports and the rewrite is done by hand.
    """
    flagged = []
    for line, text in c_comments(src):
        for off, kind, hit in flags(text):
            flagged.append((line + off, kind, hit))
    return src, flagged


HANDLERS = {".py": sweep_python, ".md": sweep_markdown, ".sh": sweep_shell}
HANDLERS.update({ext: scan_c_family for ext in
                 (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".cs", ".c", ".h")})


def excluded(path: str) -> str:
    """Why this file is not swept, or "" if it is.

    Applied to a named file as well as to a walked one. A path given on the command line reaches
    the same exclusions as one discovered by the walk, so pointing the tool at
    `agience-pharos/status/CURRENT.md` skips it and says so rather than rewriting the canon.
    """
    posix = path.replace("\\", "/")
    parts = posix.split("/")
    name, ext = parts[-1], os.path.splitext(path)[1]
    if ext not in HANDLERS:
        return "no handler for %s" % (ext or "a file with no extension")
    if name in SKIP_NAMES:
        return "generated or self-documenting: %s" % name
    hit = set(parts[:-1]) & SKIP_DIRS
    if hit:
        return "under %s" % sorted(hit)[0]
    if any(posix.endswith(s) for s in SKIP_SUFFIXES):
        return "documents the patterns by showing them"
    return ""


def walk(paths):
    for p in paths:
        if os.path.isfile(p):
            why = excluded(p)
            if why:
                print("SKIPPED   %s (%s)" % (p, why), file=sys.stderr)
            else:
                yield p
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                if not excluded(full):
                    yield full


#: A document whose dates are its content: a ledger, a dated report, a live worksheet. The prose
#: pass does not sweep these, and a flag list that includes them sends someone to destroy a record.
#: Matched on purpose rather than on location, because the same shape appears in several trees.
_DATED_RECORD = ("tighten/LEDGER", "tighten/REPORTS", "/CURRENT/", "LEDGER.md")

#: A bench: the scripts that drive one open thread, and the index that lists them. Their dates are
#: what a measurement was taken on and their verdict strings are quoted in the documents they
#: support, so the same reasoning that protects a dated report protects these. They are also the
#: one-shot half of the workspace by construction — a script that stops being one-shot moves into
#: the repo it acts on, and it is swept there. Measured 2026-09-07: they were 45 of the 78 files
#: this ranking offered, which is a worklist sending a person to the least durable prose here.
_BENCH = ("_scratch/lab/",)

#: Below this, a file is one or two incidental matches rather than a document that needs a pass.
#: Measured on one workspace: files at or above it were 143 of 656 and carried 63% of every flag.
_WORKLIST_FLOOR = 6


def worklist(paths):
    """The ranked set worth a person's time: dated records and benches dropped, thin tail dropped.

    Reproducible rather than written to a file, because a worklist committed to a tree is a
    measurement that goes stale the first time anyone edits anything.

    Returns `(head, tail, records, benches)` — the set to work, the set to report, and a count of
    each withheld kind, so what was left out is stated rather than implied by a shorter list.
    """
    rows, records, benches = [], 0, 0
    for path in walk(paths):
        posix = path.replace("\\", "/")
        try:
            src = open(path, "rb").read().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            _new, flagged = HANDLERS[os.path.splitext(path)[1]](src)
        except (SyntaxError, ValueError):
            continue
        if not flagged:
            continue
        if any(d in posix for d in _DATED_RECORD):
            records += 1
        elif any(d in posix for d in _BENCH):
            benches += 1
        else:
            kinds = {}
            for _line, kind, _hit in flagged:
                kinds[kind] = kinds.get(kind, 0) + 1
            rows.append((len(flagged), path, kinds))
    rows.sort(key=lambda r: (-r[0], r[1]))
    head = [r for r in rows if r[0] >= _WORKLIST_FLOOR]
    tail = [r for r in rows if r[0] < _WORKLIST_FLOOR]
    return head, tail, records, benches


def kind_mix(kinds: dict) -> str:
    """The flag kinds behind a count, worst first.

    A row of eighteen dates and a row of eighteen shouted headers are not the same hour. Dates in
    a gate are usually a baseline's provenance and stay; shouting is always rewritten. Ranking on
    the total alone hides which one a reader is being sent to.
    """
    return " ".join("%s=%d" % kv for kv in sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0])))


def main(argv):
    #: A source with a bad escape sequence warns at parse time. That is a defect in the file being
    #: read, not in this pass, and printing it interleaved with a ranked list makes the list harder
    #: to act on.
    warnings.simplefilter("ignore", SyntaxWarning)
    for stream in (sys.stdout, sys.stderr):
        #: The report is written in the same prose as the trees it reads — em dashes, arrows and
        #: the glyphs it names. A Windows console defaults to a codepage that cannot encode them.
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    write = "--write" in argv
    only_flags = "--flags" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2

    if "--shape" in argv:
        for path in paths:
            if os.path.splitext(path)[1] != ".py":
                print("SKIPPED   %s (a code shape is a Python AST)" % path, file=sys.stderr)
                continue
            src = open(path, "rb").read().decode("utf-8-sig")
            try:
                digest = hashlib.sha256(code_shape(src).encode()).hexdigest()[:16]
            except SyntaxError as exc:
                print("UNPARSED  %s (%s)" % (path, exc), file=sys.stderr)
                return 1
            print("%s  %s" % (digest, path.replace("\\", "/")))
        return 0

    if "--worklist" in argv:
        head, tail, records, benches = worklist(paths)
        for n, path, kinds in head:
            print("%5d  %-72s %s" % (n, path.replace("\\", "/"), kind_mix(kinds)))
        print()
        print("%d file(s) worth a pass, carrying %d flag(s)." % (len(head),
                                                                 sum(r[0] for r in head)))
        print("%d file(s) left in the tail (under %d flags each, %d in total) — report them, "
              "do not work them." % (len(tail), _WORKLIST_FLOOR, sum(r[0] for r in tail)))
        print("%d dated record(s) skipped: their dates are their content." % records)
        print("%d bench file(s) skipped: one-shot code under %s, whose verdicts the documents "
              "quote." % (benches, ", ".join(_BENCH)))
        return 0

    touched = removed = 0
    allflags = {}
    for path in walk(paths):
        raw = open(path, "rb").read()
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            src = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            print("UNREADABLE %s" % path)
            continue
        ext = os.path.splitext(path)[1]
        handler = HANDLERS[ext]
        try:
            new, flagged = handler(src)
        except SyntaxError as exc:
            print("UNPARSED  %s (%s)" % (path, exc))
            continue
        if flagged:
            allflags[path] = flagged
        if new != src and ext == ".py":
            #: Refuse rather than trust. A rewrite that changed the code shape is a defect in a rule
            #: here, and writing it would put the damage in a tree seven sessions are working in.
            try:
                if code_shape(src) != code_shape(new):
                    print("REFUSED   %s (the rewrite changed code, not just prose)" % path)
                    continue
            except SyntaxError as exc:
                print("REFUSED   %s (result does not parse: %s)" % (path, exc))
                continue
        if new != src:
            touched += 1
            removed += len(src) - len(new)
            if write:
                open(path, "wb").write((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
            if not only_flags:
                print("%-6s %s  (-%d chars)" % ("WROTE" if write else "would", path,
                                                len(src) - len(new)))

    if only_flags:
        #: The lines themselves, because that is what a rewrite is handed: one file, its flagged
        #: lines, and nothing else to do. A count alone names a file and leaves the reader to find
        #: the blocks again.
        for path, fl in sorted(allflags.items()):
            for line, kind, hit in sorted(fl):
                print("%s:%d  %-8s %s" % (path.replace("\\", "/"), line, kind,
                                          " ".join(hit.split())[:100]))
    if only_flags or not write:
        print()
        print("blocks needing a hand rewrite, by file:")
        for path, fl in sorted(allflags.items(), key=lambda kv: -len(kv[1]))[:40]:
            kinds = {}
            for _line, kind, _hit in fl:
                kinds[kind] = kinds.get(kind, 0) + 1
            print("  %4d  %-70s %s" % (len(fl), path.replace("\\", "/"),
                                       " ".join("%s=%d" % kv for kv in sorted(kinds.items()))))
    print()
    print("%s %d file(s), %d chars of tag and glyph removed; %d file(s) carry flagged prose"
          % ("wrote" if write else "would touch", touched, removed, len(allflags)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
