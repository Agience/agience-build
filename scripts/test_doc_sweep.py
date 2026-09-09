"""What the mechanical sweep may and may not touch.

The negative cases are the point. A glyph inside an OpenAPI `description=`, a log message carrying
an audit tag, and an error string are all emitted by the program, and a tool that edits them changes
behaviour rather than prose. Each of those is pinned here against a planted instance, so a widening
of the rewrite rules fails this file before it reaches a repo.
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import doc_sweep as sweep  # noqa: E402


def test_a_glyph_goes_from_a_comment():
    src = "#: \u26d4 The rule.\nx = 1\n"
    out, _ = sweep.sweep_python(src)
    assert out == "#: The rule.\nx = 1\n", out


def test_a_glyph_goes_from_a_docstring():
    src = '"""Title.\n\n\u26a0 A caveat sentence.\n"""\n'
    out, _ = sweep.sweep_python(src)
    assert "\u26a0" not in out
    assert "A caveat sentence." in out


def test_a_glyph_survives_inside_an_emitted_description():
    """The case that decides whether this tool is safe to run at all."""
    src = 'f = Field(None, description="Label. \u26a0 Opaque, never interpreted.")\n'
    out, _ = sweep.sweep_python(src)
    assert out == src, "an emitted string literal was rewritten: %r" % out


def test_an_audit_tag_survives_inside_a_log_message():
    src = 'logger.warning("create_artifact dropped a field (audit C2)")\n'
    out, _ = sweep.sweep_python(src)
    assert out == src, "a log message was rewritten: %r" % out


def test_an_audit_tag_survives_inside_an_error_detail():
    src = 'raise HTTPException(400, detail="Refused \u26d4 (audit C3)")\n'
    out, _ = sweep.sweep_python(src)
    assert out == src, "an error message was rewritten: %r" % out


def test_a_hash_inside_a_string_is_not_read_as_a_comment():
    src = 'sha = "#: \u26d4 not a comment"\n'
    out, _ = sweep.sweep_python(src)
    assert out == src, out


def test_an_audit_tag_goes_from_a_comment():
    src = "# Refuse the body (audit R3).\nx = 1\n"
    out, _ = sweep.sweep_python(src)
    assert out == "# Refuse the body.\nx = 1\n", out


def test_a_dashed_audit_tag_goes():
    src = '"""Warm sweep \u2014 audit W2 + W3.\n"""\n'
    out, _ = sweep.sweep_python(src)
    assert "audit" not in out, out
    assert out.startswith('"""Warm sweep.'), out


def test_a_ruling_attribution_goes():
    src = "# Container-level [John ruled 2026-08-25], never per child.\nx = 1\n"
    out, _ = sweep.sweep_python(src)
    assert "John" not in out and "2026" not in out, out
    assert out == "# Container-level, never per child.\nx = 1\n", out


def test_code_is_preserved_byte_for_byte():
    src = ("#: \u26d4 A note (audit Q1).\n"
           "def f(a, b=2, *args, **kw):\n"
           "    s = 'a # b \u26a0'\n"
           "    return {**kw, 'x': a}\n")
    out, _ = sweep.sweep_python(src)
    for line in ("def f(a, b=2, *args, **kw):", "    s = 'a # b \u26a0'", "    return {**kw, 'x': a}"):
        assert line in out, "code line altered: %r" % out


def test_the_result_still_parses():
    import ast
    src = '"""M \u26d4 (audit A1)."""\n\n\nclass C:\n    """D \u26a0."""\n\n    def m(self):\n        # c \u2b50\n        return 1\n'
    out, _ = sweep.sweep_python(src)
    ast.parse(out)


def test_dates_are_flagged_and_not_deleted():
    """A bare date is load-bearing in the sentence around it, so removing it breaks the sentence."""
    src = "# This said the opposite until 2026-08-26.\nx = 1\n"
    out, flagged = sweep.sweep_python(src)
    assert "2026-08-26" in out, "a bare date was deleted rather than flagged"
    assert any(k == "date" for _l, k, _h in flagged)
    assert any(k == "history" for _l, k, _h in flagged)


def test_shouting_is_flagged_and_not_deleted():
    src = "# THE RATCHET MAY ONLY SHRINK.\nx = 1\n"
    out, flagged = sweep.sweep_python(src)
    assert "THE RATCHET MAY ONLY SHRINK" in out
    assert any(k == "caps" for _l, k, _h in flagged)


def test_markdown_leaves_fenced_code_alone():
    src = "Text \u26d4 here.\n\n```\ncode \u26d4 fenced\n```\n\nMore \u26a0 text.\n"
    out, _ = sweep.sweep_markdown(src)
    assert "code \u26d4 fenced" in out, "a fenced code block was rewritten"
    assert "Text here." in out
    assert "More text." in out


def test_shell_comments_only():
    src = '# \u26d4 A note (audit S1)\necho "\u26d4 kept"\n'
    out, _ = sweep.sweep_shell(src)
    assert out == '# A note\necho "\u26d4 kept"\n', out


def test_indentation_is_preserved():
    """A rewrite rule that reaches the start of a line re-indents the body and breaks the file.

    Collapsing runs of spaces without anchoring behind a non-space character does exactly that: a
    four-space-indented docstring closes at column 1 and the function after it is an
    `IndentationError`. Every `_DANGLING` rule is anchored for this reason.
    """
    src = 'class C:\n    """D \u26a0 here."""\n\n    def m(self):\n        # c \u2b50\n        return 1\n'
    out, _ = sweep.sweep_python(src)
    assert '    """D here."""' in out, "docstring indentation lost: %r" % out
    assert "        # c" in out, "comment indentation lost: %r" % out
    import ast
    ast.parse(out)


def test_a_multi_line_docstring_keeps_every_indent():
    src = ('def f():\n'
           '    """Title \u26d4.\n'
           '\n'
           '    \u26a0 A body line.\n'
           '        An indented continuation.\n'
           '    """\n'
           '    return 1\n')
    out, _ = sweep.sweep_python(src)
    assert "\n    A body line.\n" in out, out
    assert "\n        An indented continuation.\n" in out, out
    import ast
    ast.parse(out)


def test_an_aligned_table_in_a_docstring_is_not_reformatted():
    """The rule that broke this collapsed every run of spaces in any docstring it touched.

    A docstring holding an aligned table has runs of spaces that carry meaning, and a tidy-up
    applied to every line reformats all of them while removing nothing. Alignment survives even on
    a line a glyph came off, because the line already had a run before the removal.
    """
    src = ('"""Classes.\n'
           "\n"
           "  USERNAME   `C:/Users/x` — names a person.\n"
           "  LAYOUT     `~/Workspace/` — names a directory.\n"
           "  ⛔ INFRA      box IPs and hostnames.\n"
           '"""\n')
    out, _ = sweep.sweep_python(src)
    assert "  USERNAME   `C:/Users/x`" in out, "an untouched aligned line was reformatted: %r" % out
    assert "  LAYOUT     `~/Workspace/`" in out, out
    assert "  INFRA      box IPs" in out, "alignment lost on the line a glyph came off: %r" % out


def test_an_untouched_line_is_returned_byte_for_byte():
    src = '"""T.\n\nA    B    C\n⛔ D    E    F\n"""\n'
    out, _ = sweep.sweep_python(src)
    assert "A    B    C" in out
    assert "D    E    F" in out, out


def test_a_removal_leaves_one_space_between_words():
    src = "# A note (audit R3) here.\nx = 1\n"
    out, _ = sweep.sweep_python(src)
    assert out == "# A note here.\nx = 1\n", repr(out)


def test_alignment_wins_over_tidiness_on_a_line_that_had_it():
    """A line already carrying wide runs keeps every one of them, even after a removal.

    Closing up the gap a removal leaves is worth having; guessing which of several wide runs on an
    aligned line was the accidental one is not. The conservative answer keeps the alignment.
    """
    src = "# A note  (audit R3)  here.\nx = 1\n"
    out, _ = sweep.sweep_python(src)
    assert out == "# A note  here.\nx = 1\n", repr(out)


def test_trailing_whitespace_is_only_touched_on_a_changed_line():
    src = "# kept   \n#: ⛔ changed   \nx = 1\n"
    out, _ = sweep.sweep_python(src)
    assert "# kept   \n" in out, "an untouched comment lost its trailing space: %r" % out
    assert "#: changed\n" in out, out


def test_crlf_survives_a_rewritten_comment():
    """A bare "\\n" on a rebuilt line turns a CRLF file mixed, one comment at a time.

    Neither a syntax check nor an AST comparison can see it, so it is pinned here instead.
    """
    src = '# ⛔ note (audit A1)\r\ndef f():\r\n    """D ⚠."""\r\n    return 1\r\n'
    out, _ = sweep.sweep_python(src)
    assert out.count("\r\n") == src.count("\r\n"), "line endings changed: %r" % out
    assert "\n" not in out.replace("\r\n", ""), "a lone LF was introduced: %r" % out
    assert "# note\r\n" in out


def test_crlf_survives_a_rewritten_shell_comment():
    src = "# ⛔ a note (audit S1)\r\necho hi\r\n"
    out, _ = sweep.sweep_shell(src)
    assert out == "# a note\r\necho hi\r\n", repr(out)


def test_crlf_survives_markdown():
    src = "Text ⛔ here.\r\nMore ⚠ text.\r\n"
    out, _ = sweep.sweep_markdown(src)
    assert out == "Text here.\r\nMore text.\r\n", repr(out)


def test_lf_files_stay_lf():
    src = "# ⛔ note\nx = 1\n"
    out, _ = sweep.sweep_python(src)
    assert "\r" not in out, repr(out)


def test_code_shape_ignores_prose():
    a = 'def f():\n    """One ⛔."""\n    # c\n    return 1\n'
    b = 'def f():\n    """Another thing entirely."""\n    return 1\n'
    assert sweep.code_shape(a) == sweep.code_shape(b)


def test_code_shape_notices_a_code_change():
    a = "def f():\n    return 1\n"
    b = "def f():\n    return 2\n"
    assert sweep.code_shape(a) != sweep.code_shape(b)


def test_a_rule_that_de_indents_is_refused_not_written(tmp_path, monkeypatch, capsys):
    """The guard is only worth having if it fires, so this plants the bug that was actually found.

    `clean` is replaced with one that strips leading whitespace — the shape an unanchored
    whitespace-collapse rule takes, and the real defect this file caught. The result does not
    parse, so the file on disk must be untouched and the run must say so.
    """
    p = tmp_path / "m.py"
    original = 'class C:\n    """D ⛔.\n\n    More.\n    """\n\n    def m(self):\n        return 1\n'
    p.write_text(original, encoding="utf-8")

    monkeypatch.setattr(sweep, "clean", lambda t: "\n".join(ln.lstrip() for ln in t.splitlines()))
    sweep.main(["--write", str(p)])

    assert p.read_text(encoding="utf-8") == original, "a corrupting rewrite reached disk"
    assert "REFUSED" in capsys.readouterr().out


def test_a_rule_that_injects_code_is_refused_not_written(tmp_path, monkeypatch, capsys):
    """A rewrite that adds a statement parses cleanly, so only the shape check can catch it."""
    p = tmp_path / "n.py"
    original = 'def f():\n    """D ⛔."""\n    return 1\n'
    p.write_text(original, encoding="utf-8")

    monkeypatch.setattr(sweep, "clean", lambda t: '    """D."""\n    raise SystemExit(1)')
    sweep.main(["--write", str(p)])

    assert p.read_text(encoding="utf-8") == original, "an injected statement reached disk"
    assert "REFUSED" in capsys.readouterr().out


def test_a_bom_survives(tmp_path):
    p = tmp_path / "b.py"
    p.write_bytes(b"\xef\xbb\xbf" + "# \u26d4 note\nx = 1\n".encode("utf-8"))
    sweep.main(["--write", str(p)])
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "the BOM was stripped"
    assert "\u26d4" not in raw.decode("utf-8-sig")


def test_a_file_with_a_bom_is_read_not_skipped(tmp_path):
    p = tmp_path / "c.py"
    p.write_bytes(b"\xef\xbb\xbf" + '"""D \u26a0."""\n'.encode("utf-8"))
    out = sweep.main([str(p)])
    assert out == 0


def test_the_published_canon_is_never_walked(tmp_path):
    """`status/` and `genesis/` are built on the provenance markers this tool strips.

    Pointed at the workspace root the tool would otherwise sweep canon, which is exempt from these
    deletions and is LEDGER-gated besides. Pinned here because the exemption is invisible at the
    call site: nothing about `doc_sweep.py ..` says which trees it will open.
    """
    canon = tmp_path / "agience-pharos" / "status"
    canon.mkdir(parents=True)
    (canon / "AUDIT.md").write_text("⚑ Measured 2026-08-25 — a claim.\n", encoding="utf-8")
    other = tmp_path / "agience-mantle"
    other.mkdir()
    (other / "README.md").write_text("⚑ Measured 2026-08-25 — a claim.\n", encoding="utf-8")

    walked = [str(p) for p in sweep.walk([str(tmp_path)])]
    assert not any("agience-pharos" in p for p in walked), "canon was walked: %s" % walked
    assert any("agience-mantle" in p for p in walked), "the sweep walked nothing at all"


def test_ordinary_english_is_not_flagged_as_change_history():
    """`it was` and its neighbours are not change history, and flagging them buries the real ones.

    Measured across the workspace: `it was` alone raised 195 files, `corrected` 19 and `rewritten`
    12, nearly all of them ordinary sentences. A flag list is read by someone deciding where to
    spend an hour, so precision matters more here than recall.
    """
    for ordinary in ("# it was measured at 4.47s\nx = 1\n",
                     "# if it was set, the caller wins\nx = 1\n",
                     "# corrected for drift before comparison\nx = 1\n",
                     "# the reading is rewritten each pass\nx = 1\n",
                     "# it had been normalised already\nx = 1\n"):
        _out, flagged = sweep.sweep_python(ordinary)
        assert not [f for f in flagged if f[1] == "history"], \
            "ordinary English flagged as history: %r -> %r" % (ordinary, flagged)


def test_real_change_history_is_still_flagged():
    """The mirror of the test above: a pattern loosened until it stops matching would pass that one."""
    for real in ("# this used to compare code points\nx = 1\n",
                 "# no longer applies to a member\nx = 1\n",
                 "# previously the container was in the body\nx = 1\n",
                 "# the first version spread the return\nx = 1\n",
                 "# re-pinned upward, with reasons\nx = 1\n"):
        _out, flagged = sweep.sweep_python(real)
        assert [f for f in flagged if f[1] == "history"], \
            "real change history was NOT flagged: %r" % real


def test_a_c_family_comment_is_flagged():
    src = "// this PREVIOUSLY read the OTHER SHAPE, 2026-08-25\nconst x = 1;\n"
    out, flagged = sweep.scan_c_family(src)
    assert out == src, "a C-family source was rewritten: %r" % out
    assert {f[1] for f in flagged} >= {"history", "date"}, flagged


def test_a_c_family_string_is_not_read_as_a_comment():
    """The reason this handler only flags. A comment marker inside a literal is not a comment."""
    for literal in ('const u = "https://host/path"; // real 2026-08-25\n',
                    "const t = `a // b`;\n",
                    "const s = 'a /* b */ c';\n"):
        _out, flagged = sweep.scan_c_family(literal)
        assert all("http" not in f[2] for f in flagged), flagged
    _out, flagged = sweep.scan_c_family("const t = `a // b 2026-08-25`;\n")
    assert not flagged, "a template literal was read as a comment: %r" % flagged


def test_a_c_family_block_comment_reports_the_line_it_is_on():
    src = "const a = 1;\n/*\n * 2026-08-25 was the day.\n */\n"
    _out, flagged = sweep.scan_c_family(src)
    assert flagged == [(3, "date", "2026-08-25")], flagged


def test_an_escaped_quote_does_not_swallow_the_rest_of_the_file():
    src = 'const s = "he said \\"no\\"";\n// PREVIOUSLY THE OTHER WAY\n'
    _out, flagged = sweep.scan_c_family(src)
    assert [f for f in flagged if f[1] == "history"], flagged


def test_a_named_file_in_the_canon_is_refused_not_swept(tmp_path):
    """A path on the command line reaches the same exclusions as one the walk discovered."""
    canon = tmp_path / "agience-pharos" / "status"
    canon.mkdir(parents=True)
    doc = canon / "CURRENT.md"
    doc.write_text("\u26d4 MEASURED 2026-08-25.\n", encoding="utf-8")
    assert sweep.excluded(str(doc)), "a canon file named directly was not excluded"
    assert list(sweep.walk([str(doc)])) == []


def test_a_named_file_with_no_handler_is_refused_not_crashed(tmp_path):
    odd = tmp_path / "notes.rst"
    odd.write_text("\u26d4 anything\n", encoding="utf-8")
    assert list(sweep.walk([str(odd)])) == []
    assert sweep.main([str(odd)]) == 0


def test_an_ordinary_named_file_is_still_swept(tmp_path):
    """The mirror: an exclusion wide enough to catch everything would pass the tests above."""
    src = tmp_path / "thing.py"
    src.write_text("#: \u26d4 The rule.\nx = 1\n", encoding="utf-8")
    assert sweep.excluded(str(src)) == ""
    assert list(sweep.walk([str(src)])) == [str(src)]


def test_shape_moves_only_when_code_moves(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text('"""Old prose, 2026-08-25."""\nx = 1\n', encoding="utf-8")
    sweep.main(["--shape", str(src)])
    before = capsys.readouterr().out.split()[0]
    src.write_text('"""New prose."""\nx = 1\n', encoding="utf-8")
    sweep.main(["--shape", str(src)])
    assert capsys.readouterr().out.split()[0] == before, "prose moved the shape"
    src.write_text('"""New prose."""\nx = 2\n', encoding="utf-8")
    sweep.main(["--shape", str(src)])
    assert capsys.readouterr().out.split()[0] != before, "a code change did not move the shape"


def test_flags_prints_the_line_numbers_a_rewrite_is_handed(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text("x = 1\n#: THE FIRST SHOUTED LINE\ny = 2\n", encoding="utf-8")
    sweep.main(["--flags", str(src)])
    assert ":2  caps" in capsys.readouterr().out


def test_a_bench_is_reported_not_worked(tmp_path):
    """`_scratch/lab` is one-shot code whose verdicts its document quotes."""
    bench = tmp_path / "_scratch" / "lab" / "thread"
    bench.mkdir(parents=True)
    (bench / "audit.py").write_text(
        "#: MEASURED ON 2026-08-25, AND USED TO read the other way\nx = 1\n" * 8, encoding="utf-8")
    head, tail, _records, benches = sweep.worklist([str(tmp_path)])
    assert (head, tail, benches) == ([], [], 1), (head, tail, benches)


def test_the_ranking_says_which_kind_of_flag_a_row_is(tmp_path):
    """Eighteen dates and eighteen shouted headers are not the same hour of work."""
    (tmp_path / "dated.py").write_text(
        "".join("#: pinned 2026-08-%02d\n" % d for d in range(10, 20)) + "x = 1\n",
        encoding="utf-8")
    head, _tail, _records, _benches = sweep.worklist([str(tmp_path)])
    assert sweep.kind_mix(head[0][2]) == "date=10", head


def test_a_call_written_in_prose_keeps_its_parentheses():
    """A glyph coming off a line must not turn a call into an attribute.

    `_EMPTY_PARENS` exists to close up the bracket a parenthesised tag left behind. Applied to
    every changed line it also closed `psutil.net_connections()`, which reads as a different thing
    from `psutil.net_connections`. Found by a rewrite agent reading the diff, after the pass had
    already written the file.
    """
    src = '"""\u26d4 Reads psutil.net_connections() rather than asking WMI."""\n'
    out, _ = sweep.sweep_python(src)
    assert "net_connections()" in out, out
    assert "\u26d4" not in out


def test_a_tag_that_was_the_whole_bracket_still_closes_up():
    """The mirror: a guard wide enough to skip every line would pass the test above."""
    src = "# Refuse the body (audit R3).\nx = 1\n"
    out, _ = sweep.sweep_python(src)
    assert out == "# Refuse the body.\nx = 1\n", out


def test_a_flag_reports_the_line_it_is_on_not_the_block_it_is_in():
    """A module header here is eighty lines; a flag at its opening quote is not a location.

    Every flag inside a docstring reported `node.lineno`, so `--flags` sent the reader to the top
    of the block to find the sentence by hand.
    """
    src = '"""Title.\n\nOrdinary prose.\n\nTHIS SHOUTS LOUDLY here.\n"""\nx = 1\n'
    _out, flagged = sweep.sweep_python(src)
    assert [f for f in flagged if f[1] == "caps"][0][0] == 5, flagged


def test_a_flag_in_a_markdown_line_keeps_its_own_number():
    """The mirror: an offset added twice would move a single-line hit off its line."""
    src = "one\ntwo\nTHIS SHOUTS LOUDLY\nfour\n"
    _out, flagged = sweep.sweep_markdown(src)
    assert flagged == [(3, "caps", "THIS SHOUTS LOUDLY")], flagged
