r"""Is the Mantle memory lane actually working? Read the log and say so, with numbers.

    python ~/.claude/hooks/mantle_hook_health.py              # last 3 days
    python ~/.claude/hooks/mantle_hook_health.py --days 14
    python ~/.claude/hooks/mantle_hook_health.py --quiet      # exit code only, for a scheduler

Exit 0 healthy · 1 degraded · 2 broken. Non-zero is the point: this is meant to be run on a
schedule and to be capable of complaining.

## Why this exists

The memory lane was dead for eleven days and nothing said so. Measured 2026-08-24 over
`~/.claude/mantle-hook.log`: 4,112 hook firings, every one addressed to `71/dev`, a node that had
been switched off — while Claude Code's own MCP tools were pointed at `71/home`. Two lanes, one
of them writing into a closed socket. The log recorded it faithfully the whole time. Nobody read
the log, because reading it was nobody's job and there was nothing to read it with.

The failure is structural, not careless. Every hook here is **best-effort by design** — the
module docstrings are explicit that a hook must never fail an edit or block a prompt — so every
failure path returns quietly. That is correct behaviour and it has one cost: **a broken hook is
indistinguishable from a quiet one.** `mantle-hook.log` exists to close exactly that gap, and a
log nothing reads closes nothing. This is the reader.

## What each outcome means, and which ones are bad

Not every non-`stored` outcome is a fault, and treating them alike would make this instrument
cry wolf until it was ignored:

    stored/created/updated  the write landed and the id came back.
    skipped                 the capture rule declined the file. Correct, and usually the majority.
    injected                a recall found hits and put them in front of the prompt.
    no-hits                 the recall completed and the store had nothing.  Ambiguous - see below
    unconfirmed             the reply was lost. The write may have landed.   Watch the rate
    failed                  a real error, named.

`unconfirmed` is **not** data loss. Both writers key on a stable `identity`, so the next write of
the same path or session lands on the same artifact — a lost reply costs one stale artifact until
the next edit, never a duplicate. It is the rate that carries information: a few mean slow writes,
a sustained majority means the node is unreachable or slower than the timeout, which is precisely
what was invisible for those eleven days.

`no-hits` is the ambiguous one and `mantle_common` says why: a recall that overruns its timeout
returns `None`, becomes `[]`, and logs the same `no-hits` as a recall that genuinely found nothing.
So a high no-hit rate is a question, not a verdict — this reports it as one, and probes the node so
the reader can tell the two apart.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import io
import json
import os
import sys
from pathlib import Path

LOG = Path(os.path.expanduser("~/.claude/mantle-hook.log"))
TARGET_FILE = Path(os.path.expanduser("~/.claude/mantle-target.json"))
CLAUDE_CONFIG = Path(os.path.expanduser("~/.claude.json"))

#: Thresholds. Chosen against measured behaviour rather than taste, and stated so they can be
#: argued with: on a healthy node most `store_file` firings are `skipped` (the capture rule is
#: prose-only), so the ratio that matters is unconfirmed against ATTEMPTED writes, not against all
#: firings. 25% of attempted writes losing their reply is already a sick node.
UNCONFIRMED_WARN = 0.25
UNCONFIRMED_FAIL = 0.60
#: A recall corpus that answers nothing 90% of the time is either empty or unreachable. Below that
#: it is a corpus question, not a health question, so it is reported and not judged.
NOHIT_FAIL = 0.90

_WRITE_EVENTS = ("store_file", "archive_transcript")


def _read(days: int):
    if not LOG.exists():
        return None, "no log at %s — the hooks have never run" % LOG
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    rows = []
    for line in io.open(LOG, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            ts = datetime.datetime.fromisoformat(d["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        if ts >= cutoff:
            rows.append(d)
    return rows, None


def _configured_targets():
    """What the two halves are each pointed at. They must agree; nothing else reconciles them.

    This is the check that would have caught the original fault on day one. `mantle_target.py`
    writes both halves together and refuses to write one, but it is only authoritative for
    switches made THROUGH it — either file can still be hand-edited, and the MCP half in
    particular is a plain URL in Claude Code's own config that anything may rewrite.
    """
    hooks_url = mcp_url = None
    active = None
    try:
        cfg = json.load(io.open(TARGET_FILE, encoding="utf-8"))
        active = cfg.get("active")
        hooks_url = ((cfg.get("targets") or {}).get(active or "") or {}).get("mcp_url")
    except (OSError, ValueError):
        pass
    try:
        cc = json.load(io.open(CLAUDE_CONFIG, encoding="utf-8"))
        mcp_url = ((cc.get("mcpServers") or {}).get("mantle") or {}).get("url")
    except (OSError, ValueError):
        pass
    return active, hooks_url, mcp_url


def _probe(url: str, timeout: float = 8.0):
    """Does the node answer? `/status` on the origin of the MCP url."""
    if not url:
        return None, "no url"
    import urllib.error
    import urllib.request
    base = url.rsplit("/mcp", 1)[0]
    try:
        with urllib.request.urlopen(base + "/status", timeout=timeout) as r:
            body = json.loads(r.read().decode())
            return True, "HTTP %s · %s vertices" % (
                r.status, "{:,}".format(body.get("vertices", 0)))
    except urllib.error.HTTPError as e:
        return False, "HTTP %s" % e.code
    except Exception as e:  # noqa: BLE001 — a probe reports, it does not raise
        return False, type(e).__name__


def _probe_recall(url: str):
    """Time one real `recall`. Returns `(within_hook_timeout, detail, seconds)`.

    WHY THIS EXISTS, and why `/status` is not a substitute. Measured 2026-08-27 on `71/home`:
    `/status` answered in **0.03s** while `recall` took **34s to return zero hits** — so the node
    was, by every probe the tool had, healthy, while the read lane the tool exists to watch had
    been dead for two days. `_probe` above asks whether the node is UP. Nothing asked whether it
    ANSWERS. Those are different questions and only the second one is the lane.

    THE THRESHOLD IS NOT CHOSEN. It is `mantle_common._HTTP_TIMEOUT_SECONDS` — the timeout the
    hooks themselves give a recall. A recall slower than that is not "slow", it is a recall the
    hook can NEVER receive, whatever the store holds. Deriving it this way is deliberate:
    `recall_context.py` records ten fitted constants that all failed, and a latency budget picked
    by hand here would be the eleventh. If the hook's timeout changes, this moves with it.

    The probe term is deliberately a NON-WORD. It measures the FLOOR — what a recall costs before
    it matches, ranks or hydrates anything — which is the quantity that decides whether the lane
    can work at all, and it is the cheapest question the node can be asked. A term with hits would
    measure the floor plus this corpus's ranking cost and confound the two.

    The ceiling is a multiple of the hook's timeout rather than equal to it, so that a floor which
    has already crossed the line is REPORTED with its size instead of coming back as a bare
    timeout. Knowing it is 34s and not 13s is the difference between a tuning problem and this one.
    """
    if not url:
        return None, "no url", 0.0
    import time
    import urllib.request
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from mantle_common import _HTTP_TIMEOUT_SECONDS as hook_timeout
        from mantle_common import get_access_token
    except Exception:  # noqa: BLE001 — without the hook's own number there is nothing to compare
        return None, "mantle_common not importable", 0.0

    ceiling = hook_timeout * 4
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "recall",
                                  "arguments": {"query_text": "zzzqqxnonsense", "size": 1}}})
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    try:
        bearer = get_access_token()
    except Exception:  # noqa: BLE001 — an unauthenticated probe still measures the floor
        bearer = None
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(url, data=body.encode(), headers=headers)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=ceiling) as r:
            r.read()
        secs = time.time() - started
    except Exception as e:  # noqa: BLE001 — a probe reports, it does not raise
        secs = time.time() - started
        if secs >= ceiling - 1:
            return False, ("no answer in %ds — over %dx the hook's own %ds timeout"
                           % (ceiling, ceiling // max(hook_timeout, 1), hook_timeout)), secs
        return False, "%s after %.1fs" % (type(e).__name__, secs), secs
    if secs > hook_timeout:
        return False, ("%.1fs to return NOTHING — the hooks give recall %ds, so every hook "
                       "recall times out and logs `no-hits`" % (secs, hook_timeout)), secs
    return True, "%.1fs floor (hook timeout %ds)" % (secs, hook_timeout), secs


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Health of the Mantle hook lane.")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    ap.add_argument("--quick", action="store_true",
                    help="config + log only, no network probe. For a SessionStart hook.")
    args = ap.parse_args()

    out = [] if args.quiet else None

    def say(s=""):
        if out is None:
            print(s)

    rows, err = _read(args.days)
    if err:
        say("⛔ " + err)
        return 2

    verdict = 0
    say("=" * 74)
    say("Mantle hook lane — last %d day(s), %d firing(s)" % (args.days, len(rows)))
    say("=" * 74)

    # ---- the split-brain check ----------------------------------------------------------
    active, hooks_url, mcp_url = _configured_targets()
    say("\nCONFIGURED TARGET")
    say("  hooks (mantle-target.json '%s') : %s" % (active, hooks_url))
    say("  MCP   (.claude.json mcpServers) : %s" % mcp_url)
    if hooks_url and mcp_url and hooks_url != mcp_url:
        say("  ⛔ THE TWO HALVES DISAGREE. Recall reads one store and the tools write another;")
        say("     neither side errors. Fix with: python ~/.claude/hooks/mantle_target.py <name>")
        verdict = max(verdict, 2)
    elif hooks_url and mcp_url:
        say("  ✅ agree")

    # The probe is the only slow part, and `--quick` is why that matters. This runs as a
    # SessionStart hook, in front of a person waiting to type. The two checks that actually caught
    # the eleven-day outage — the halves disagreeing, and the unconfirmed rate in the log — are both
    # local and instant. The probe adds up to 8s of network to confirm what the write outcomes
    # already imply, so it is skipped where latency is the constraint rather than dropped from the
    # tool that a human runs deliberately.
    if args.quick:
        say("  node /status                    : (skipped — --quick)")
    else:
        ok, detail = _probe(hooks_url)
        say("  node /status                    : %s" % ("✅ " + detail if ok else "⛔ " + detail))
        if ok is False:
            say("     Every hook write is going into a node that is not answering.")
            verdict = max(verdict, 2)

        # `/status` answers the WRITE lane's question. This one answers the READ lane's, and on
        # 2026-08-27 they disagreed by three orders of magnitude — 0.03s against 34s. See
        # `_probe_recall`. It runs after the status line so a node that is simply down is already
        # reported, and it is never reached under `--quick`.
        if ok is not False:
            r_ok, r_detail, _secs = _probe_recall(hooks_url)
            if r_ok is None:
                say("  recall floor                    : (not measured — %s)" % r_detail)
            else:
                say("  recall floor                    : %s"
                    % ("✅ " + r_detail if r_ok else "⛔ " + r_detail))
                if r_ok is False:
                    say("     The store may be full and every recall still arrive as `no-hits`.")
                    verdict = max(verdict, 2)

    # ---- what the log actually says -------------------------------------------------------
    if not rows:
        say("\nNo firings in the window. Either Claude Code has not run, or the hooks are not")
        say("registered in ~/.claude/settings.json.")
        return max(verdict, 1)

    tgt = collections.Counter(r.get("target") for r in rows)
    say("\nTARGET ACTUALLY USED (from the log)")
    for t, n in tgt.most_common():
        flag = ""
        if active and t not in (active, None) and t != "default":
            flag = "  ⚠ not the configured target"
        say("  %-10s %6d%s" % (t, n, flag))

    # ── the verdict is scored on the configured target, and only on it ───────────────────────────
    # Scoring every row in the window instead makes this tool lie. Measured 2026-08-24: 1,720
    # firings against `dev` and 177 against `home`, in one 3-day window spanning a
    # `mantle_target.py home` switch at 15:00. `dev` is `127.0.0.1:8182` — a node that was not
    # running — so 90% of its writes were unconfirmed, correctly. Averaged in with `home`'s, those
    # failures would print broken, while `home` alone was 117 stored against 4 unconfirmed: 97%
    # confirmed, and healthy.
    #
    # That would be the worst failure a diagnostic can have. This is the file you run to find out
    # whether the lane works — `CLAUDE.md` sends you here before concluding the store is empty —
    # and reporting a fault that had already been fixed teaches an operator to disbelieve it, so
    # the next real outage would read exactly like this one.
    #
    # Writes to a target you have since left are history: they cannot be retried, they say nothing
    # about the lane you are on now, and they must not be able to condemn it.
    #
    # With one exception, which is the case this tool exists for: if the most recent firing is
    # off-target, the hooks are writing somewhere other than where they are configured right now —
    # the split-brain `mantle_target.py` exists to prevent, and the eleven-day outage this file was
    # written after. That stays fatal, and is checked before anything is scored.
    def _is_current(row):
        t = row.get("target")
        return (not active) or t in (active, None, "default")

    if active and rows and not _is_current(rows[-1]):
        say("\n⛔ THE MOST RECENT FIRING WENT TO '%s', NOT THE CONFIGURED '%s'."
            % (rows[-1].get("target"), active))
        say("   The hooks are writing to a different store than the one configured — recall and")
        say("   capture would be on different nodes, with no error on either side. Fix with:")
        say("     python ~/.claude/hooks/mantle_target.py %s" % active)
        verdict = max(verdict, 2)

    scored = [r for r in rows if _is_current(r)]
    stale = [r for r in rows if not _is_current(r)]
    if stale:
        say("\n%d firing(s) in this window went to an earlier target and are NOT scored below."
            % len(stale))
        say("  History: writes to a node you have left cannot be retried, and say nothing about")
        say("  the lane you are on now.")

    by = collections.defaultdict(collections.Counter)
    for r in scored:
        by[r.get("event")][r.get("outcome")] += 1

    if not by:
        say("\nNo firings against the configured target '%s' in this window." % (active or "?"))
        say("  Nothing here measures the lane you are on. Run a session, or widen --days.")
        return max(verdict, 1)

    say("\nOUTCOMES  (configured target '%s' only)" % (active or "all"))
    for ev in sorted(by):
        outs = by[ev]
        say("  %s" % ev)
        for o, n in outs.most_common():
            say("      %-14s %6d" % (o, n))

        if ev in _WRITE_EVENTS:
            attempted = sum(n for o, n in outs.items() if o != "skipped")
            unc = outs.get("unconfirmed", 0)
            if attempted:
                rate = unc / attempted
                mark = "✅"
                if rate >= UNCONFIRMED_FAIL:
                    mark, verdict = "⛔", max(verdict, 2)
                elif rate >= UNCONFIRMED_WARN:
                    mark, verdict = "⚠", max(verdict, 1)
                say("      %s unconfirmed %.0f%% of %d attempted write(s)"
                    % (mark, rate * 100, attempted))

        if ev == "recall":
            done = outs.get("injected", 0) + outs.get("no-hits", 0)
            if done:
                rate = outs.get("no-hits", 0) / done
                mark = "✅"
                if rate >= NOHIT_FAIL:
                    mark, verdict = "⚠", max(verdict, 1)
                say("      %s no-hits %.0f%% of %d completed recall(s)" % (mark, rate * 100, done))
                if rate >= NOHIT_FAIL:
                    say("         AMBIGUOUS: an empty store and a recall that overran its timeout")
                    say("         log the same word. The node probe above tells them apart.")

    say("\n" + "=" * 74)
    say({0: "✅ HEALTHY", 1: "⚠ DEGRADED", 2: "⛔ BROKEN"}[verdict])
    say("=" * 74)
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
