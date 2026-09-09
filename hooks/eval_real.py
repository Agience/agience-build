#!/usr/bin/env python3
"""A retrieval evaluation over REAL documents, that checks its own ground truth first.

IT VERIFIES THE ANSWER IS IN THE CORPUS BEFORE SCORING THE RANKER. An earlier eval in this
project reported a confident, well-evidenced, entirely wrong diagnosis — tables and all — because
four of its six questions asked about files that were never stored. The ranker was returning the
nearest thing it had. So every case here names a probe term, this asserts the probe is actually
present in the target document on disk, and a case whose ground truth does not hold is reported
as BROKEN rather than counted as a miss.

The controls matter as much as the questions. An eval made only of questions cannot see a gate,
because it never asks something that has no answer — and a change that deletes the quiet gate
scores BETTER on questions alone. Two control sets run here: conversational turns, which must
return nothing, and off-corpus questions, which have no answer in this store.

    python eval_real.py
"""
from __future__ import annotations

import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mantle_common import recall, workspace_root  # noqa: E402

# Both of these are derived rather than hardcoded. They were once absolute paths that went dead
# when the tree moved, and the eval went on scoring recall against files that were not there —
# which makes every case it reports a measurement of nothing. See `mantle_common.workspace_root`.
_ROOT = workspace_root()
SCRATCH = str(_ROOT / "_scratch") if _ROOT else ""
REPO = str(_ROOT / "agience-mantle") if _ROOT else ""

#: (question, target file, a phrase that must appear in that file)
#:
#: The phrase is the ground-truth check. It is a distinctive span from the document, so a case
#: whose file no longer says what the question asks stops being scored instead of quietly
#: becoming a failure of the ranker.
CASES = [
    # ── answerable from the TITLE: the lexical arm's job ──────────────────────────────────
    ("what did we find about the read path", f"{SCRATCH}/READ-PATH-FINDINGS.md", "read"),
    ("why does it keep forgetting things already figured out",
     f"{SCRATCH}/WHY-IT-KEEPS-FORGETTING.md", "forget"),
    ("what is the mantle audit", f"{SCRATCH}/MANTLE-AUDIT-2026-08-09.md", "audit"),
    ("operator runbook", f"{SCRATCH}/OPERATOR-RUNBOOK-2026-08-11.md", "runbook"),
    ("search architecture", f"{SCRATCH}/SEARCH-ARCHITECTURE.md", "search"),

    # ── answerable only from the BODY: the vector arm's job ───────────────────────────────
    ("when should I use mantle instead of local memory", f"{REPO}/CLAUDE.md", "local memory"),
    ("how is authorization done in this store", f"{REPO}/README.md", "authorization"),
    ("what is banned from retrieval and why",
     f"{SCRATCH}/RETRIEVAL-THE-ENTROPTICS-WAY.md", "Cosine similarity"),
    ("what did we decide about stemming",
     f"{SCRATCH}/RETRIEVAL-THE-ENTROPTICS-WAY.md", "stemmer"),
    ("how does an artifact's content get stored",
     f"{REPO}/src/mantle/services/content_service.py", "content"),
    ("what keeps content out of the lattice document",
     f"{REPO}/src/mantle/db/doc_boundary.py", "content_ref"),
    ("how are blind tokens narrowed to artifacts",
     f"{REPO}/src/mantle/search/mantle/sse/narrowing.py", "blind_token"),
    ("how is a posting list encrypted",
     f"{REPO}/src/mantle/search/mantle/sse/posting.py", "posting"),
    ("how does the anchor set get loaded",
     f"{REPO}/src/mantle/search/anchors/repo.py", "AnchorSet"),
    ("what happens when an artifact is indexed",
     f"{REPO}/src/mantle/search/ingest/pipeline_unified.py", "index"),
]

#: Must return NOTHING. A conversational turn has no question in it.
CHATTER = ["thanks, looks good", "ok", "nice", "yes continue", "go on",
           "this is good.. continue", "sounds right", "perfect"]

#: Have no answer in this store. Returning a few nearest neighbours is not a failure; returning
#: them confidently at the top of a page the model will read is.
OFF_CORPUS = ["how do I make sourdough bread", "what is the capital of Peru",
              "how does react useEffect work", "best way to roast a chicken"]


def _ground_truth_holds(path: str, probe: str) -> bool:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return probe.lower() in fh.read().lower()
    except OSError:
        return False


def _rank_of(hits, target_basename: str) -> int:
    for i, hit in enumerate(hits, 1):
        name = str(hit.get("title") or hit.get("name") or "")
        if target_basename.lower() in os.path.basename(name).lower():
            return i
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

    print("=" * 96)
    print("GROUND TRUTH — is the answer actually in the corpus?")
    print("=" * 96)
    live = []
    for question, path, probe in CASES:
        holds = _ground_truth_holds(path, probe)
        if not holds:
            print("  BROKEN  %-52s %s lacks %r" % (question[:52], os.path.basename(path), probe))
        else:
            live.append((question, path, probe))
    print("  %d of %d cases have verified ground truth" % (len(live), len(CASES)))

    print()
    print("=" * 96)
    print("RETRIEVAL — real questions against real documents")
    print("=" * 96)
    print("  %-52s %-6s %-5s %s" % ("question", "rank", "n", "top hit"))
    print("  " + "-" * 92)
    ranks, times, bodies = [], [], 0
    for question, path, _probe in live:
        target = os.path.basename(path)
        t0 = time.time()
        hits = recall(question)
        times.append((time.time() - t0) * 1000)
        bodies += sum(1 for h in hits if (h.get("content") or "").strip())
        rank = _rank_of(hits, target)
        ranks.append(rank)
        top = os.path.basename(str(hits[0].get("title") or hits[0].get("name") or "")) if hits else "(none)"
        print("  %-52s %-6s %-5d %s" % (question[:52], ("#%d" % rank) if rank else "--",
                                        len(hits), top[:30]))

    at1 = sum(1 for r in ranks if r == 1)
    at3 = sum(1 for r in ranks if 1 <= r <= 3)
    found = sum(1 for r in ranks if r)
    print("  " + "-" * 92)
    print("  hit@1 %d/%d   hit@3 %d/%d   found-anywhere %d/%d   median %.0f ms   hits with a body %d"
          % (at1, len(ranks), at3, len(ranks), found, len(ranks),
             statistics.median(times) if times else 0, bodies))

    print()
    print("=" * 96)
    print("CONTROL — conversational turns MUST return nothing")
    print("=" * 96)
    silent = 0
    for turn in CHATTER:
        n = len(recall(turn))
        silent += (n == 0)
        print("  %-30s %s" % (repr(turn), "silent" if n == 0 else "RETURNED %d" % n))
    print("  silent on %d/%d" % (silent, len(CHATTER)))

    print()
    print("=" * 96)
    print("CONTROL — questions with no answer in this store")
    print("=" * 96)
    for question in OFF_CORPUS:
        hits = recall(question)
        top = os.path.basename(str(hits[0].get("title") or hits[0].get("name") or "")) if hits else "(none)"
        print("  %-40s n=%-3d %s" % (question[:40], len(hits), top[:34]))

    print()
    print("VERDICT: hit@3 %d/%d, gate silent %d/%d" % (at3, len(ranks), silent, len(CHATTER)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
