#!/usr/bin/env python3
"""UserPromptSubmit hook: recall what the store has for this prompt, and put it in front of the model.

NO THRESHOLDS, NO BUDGETS, NO EXCLUSIONS, NO RE-RANKING. All of it was here and all of it is gone.
Over one session this file accumulated ten fitted constants -- a score floor, a relative floor, a
candidate budget, a content budget, an operator exclusion, a false-alarm rate, a null draw count,
a transcript tail, a verbatim span width, a seed -- plus a BM25 ranker carrying two more. Every one
was added because something looked wrong and a number made the symptom go away.

They did not work, and the record is worth keeping:

- `_MIN_TOP_SCORE = 5.0` was fitted when the chatter maximum was 4.40. Hours later, after the
  corpus grew by a handful of documents, chatter reached 4.91 and a real question ("what is the
  attenuation operator") began injecting NOTHING. It failed in both directions inside a day.
- `_CANDIDATE_BUDGET` tuned 25 -> 15 bought 0.28s and LOST THREE OF FIVE ANSWERS.
- The operator exclusion kept transcripts out of every recall. A transcript is often the only
  record of why something was done; excluding it decides in advance what may be known.
- Six principled replacements for the score floor were tried and all six failed, each for its own
  reason. See `entroptics-discipline` in local memory before retrying any of them.

None of that is a tuning problem. Deciding HOW MUCH to return is the aperture's job: its window is
"a MINIMUM, not a clock -- it keeps at least that many frames and MORE while the signal is still
coherent." The signal sets its own extent. A constant chosen against last week's corpus is a guess
standing where a measurement belongs, and it drifts the moment the corpus does.

So this hook does the one thing it can do honestly today: ask, and pass on what came back. That is
noisier than the version with ten knobs. The noise is REAL -- it is what the store actually returns
-- and it belongs in view rather than hidden behind a threshold that silently starts dropping
answers. The fix is the aperture over a vector frame, not another number here.

Best-effort: any failure prints nothing and exits 0. A store being down must never block a prompt.
"""
from __future__ import annotations

import sys

from mantle_common import log_event, read_stdin_json, recall


def main() -> int:
    # The console is not UTF-8 on Windows, and the content is. Artifacts carry em dashes,
    # arrows and quotes; the default cp1252 stdout raises UnicodeEncodeError on the first one and
    # the hook dies mid-print, having already emitted a partial block. It did not surface while a
    # content budget and a prose-only filter were trimming what got this far -- removing those
    # forcings is what let real text reach the terminal.  so one exotic
    # codepoint degrades to a glyph instead of losing the whole recall.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    payload = read_stdin_json()

    # Both spellings. The field name is the host's to choose, and getting it wrong is invisible:
    # this hook's failure mode is indistinguishable from "nothing was found".
    prompt = ""
    for key in ("prompt", "user_input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            prompt = value.strip()
            break
    if not prompt:
        log_event("recall", outcome="no-prompt", keys=sorted(payload.keys()))
        return 0

    hits = recall(prompt)
    if not hits:
        log_event("recall", outcome="no-hits", prompt=prompt)
        return 0

    lines = ["[mantle recall - artifacts that may be relevant to this prompt]"]
    for hit in hits:
        lines.append(f"- {hit.get('title') or hit.get('id')} (id: {hit.get('id')}, score: {hit.get('score')})")
        content = (hit.get("content") or "").strip()
        if content:
            lines.append(f"  {content}")
    print(chr(10).join(lines))

    # The prompt and the hits, whole. A count says the machinery ran; it says nothing about
    # whether what came back was worth reading, which is the only question left once the plumbing
    # works -- and judging that later needs the query and the titles side by side.
    log_event("recall", outcome="injected", hits=len(hits), prompt=prompt,
              returned=[{"title": h.get("title"), "score": h.get("score")} for h in hits])
    return 0


if __name__ == "__main__":
    sys.exit(main())
