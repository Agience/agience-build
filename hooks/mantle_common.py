"""Shared plumbing for the mantle-integration Claude Code hooks in this directory.

Every hook here is best-effort: mantle being down, slow, or misconfigured must never block a
prompt, a file edit, or a session ending. Every network call in this module is wrapped so a
failure returns None/empty instead of raising, and callers are expected to no-op on that.

Which node these hooks talk to
------------------------------
One source of truth, because there are two consumers: Claude Code reaches mantle through the
`mcpServers.mantle` entry in `~/.claude.json` (a static bearer), and these hooks reach it through
this module (an OAuth refresh grant). Those are separate paths to the same node, and nothing
connects them — so pointing one at `home` while the other still answers from `dev` gives a session
whose recalled context comes from one store while its writes land in another, silently, with no
error on either side.

`~/.claude/mantle-target.json` is that single source of truth, and `mantle_target.py` is what
rewrites BOTH from it. Shape:

    {"active": "dev",
     "targets": {"dev":  {"mcp_url": ..., "token_url": ..., "client_id": ...,
                          "refresh_token_file": ..., "mcp_bearer": ...},
                 "home": {...}}}

Resolution order per value, most specific first:

    1. an explicit environment variable   — a deliberate one-off override, always wins
    2. the active target in that file     — the ordinary case
    3. the built-in default               — this machine's `71/dev` node

An absent or broken file is not a failure: it resolves to the defaults, which is exactly what
this module did before the file existed. A capture layer must not stop capturing because a config
file was mistyped.

Switching targets switches identity. Each node is its own authority with its own principals, so
the same person is a different `sub` on each — artifacts do not follow you across a switch. That is
the whole reason a promote path exists, and it is a property of the design rather than a gap in it.

The refresh token lives in a file OUTSIDE this repo (the user's home `.claude` dir) precisely so
it is never something `git add .` can pick up. Access tokens are short-lived (about 4 hours) and
are never cached to disk here -- each call mints a fresh one from the refresh token, which
Origin does not rotate (see agience-origin's `_grant_refresh_token`), so the same file keeps
working indefinitely without any hook here needing to write back to it. A token file is per target:
dev's refresh token is meaningless to home's Origin, so the two must never share a path.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

#: The switch file. Read once at import — a hook is a short-lived process, so re-reading per call
#: would buy nothing but a race with `mantle_target.py` rewriting it mid-run.
MANTLE_TARGET_FILE = Path(os.environ.get(
    "MANTLE_TARGET_FILE", str(Path.home() / ".claude" / "mantle-target.json")))


def _active_target() -> Dict[str, Any]:
    """The active target's settings, or {} when there is no usable file.

    Silent on every failure, by the same rule as the rest of this module: a missing, unreadable or
    malformed switch file must degrade to the built-in defaults rather than take the hooks down.
    Returning {} makes every lookup below fall through to its default with no branch of its own.
    """
    try:
        data = json.loads(MANTLE_TARGET_FILE.read_text(encoding="utf-8"))
        target = (data.get("targets") or {}).get(data.get("active") or "")
        return target if isinstance(target, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError, AttributeError, TypeError):
        return {}


_TARGET = _active_target()


def _setting(env_var: str, key: str, default: str) -> str:
    """One config value, resolved env → active target → default (see the module docstring)."""
    from_env = os.environ.get(env_var)
    if from_env:
        return from_env
    value = _TARGET.get(key)
    return value if isinstance(value, str) and value else default


MANTLE_MCP_URL = _setting("MANTLE_MCP_URL", "mcp_url", "http://localhost:8182/mcp")
MANTLE_TOKEN_URL = _setting("MANTLE_TOKEN_URL", "token_url", "http://localhost:8180/auth/token")
MANTLE_CLIENT_ID = _setting("MANTLE_CLIENT_ID", "client_id", "dcr_gnnC5SZ17BvrW1UpEeBvwjM8jg7nMbru")
MANTLE_REFRESH_TOKEN_FILE = os.path.expanduser(_setting(
    "MANTLE_REFRESH_TOKEN_FILE", "refresh_token_file",
    str(Path.home() / ".claude" / "mantle-refresh-token")))

#: Which target these values came from — recorded on every `log_event` line so the hook log says
#: which store it was talking to. Without it, two runs against different nodes are indistinguishable
#: in the log, and "the recall came back empty" cannot be told from "it came back empty over there".
MANTLE_TARGET_NAME = _TARGET.get("name") or os.environ.get("MANTLE_TARGET") or "default"


# ── where the workspace is ───────────────────────────────────────────────────────────────────────
# One resolver, and no machine-specific literal anywhere in the repo. Local configuration — where
# this operator keeps their trees, what the cron schedule is — stays out of a tree that publishes.
#
# It exists as a function rather than a rule in a comment because the failure is silent. A hook
# carrying its own hard-coded absolute path keeps working until the tree moves, and then
# `embed()` returns `(None, None)` rather than raising, so the vector arm stops contributing and
# nothing says so. Three hooks held such a path, every one of them naming a directory a workspace
# merge had already removed:
#
#     capture_commits.DEFAULT_REPOS   the commit-capture arm had nothing to read
#     embedder._REPOS                 PRISM_SRC/ENTROPTICS_SRC/OPTICS_PATH all derive from it
#     eval_real.SCRATCH / .REPO       the recall eval scored against files that were not there
#
# Resolution order, most specific first — the same shape `_setting` already uses:
#
#   1. `AGIENCE_REPOS`                       a deliberate one-off override, always wins
#   2. `repos_root` in the switch file       the ordinary case, and LOCAL — `~/.claude/`, never the repo
#   3. walking up from this file             works for the copy that lives inside the workspace
#   4. None, said out loud                   never a guess, and never a path from this machine
#
# `repos_root` is top-level in the switch file, not inside a target. A target is a mantle node;
# the workspace is the same tree whichever node you talk to. Nested per-target it would have to be
# repeated, and the copies would drift the first time someone switched with `mantle_target.py`.
def _top_level(key: str) -> str:
    """A setting that belongs to the machine rather than to a target. Silent on every failure,
    by the same rule as `_active_target`: a broken switch file degrades, it does not raise."""
    try:
        data = json.loads(MANTLE_TARGET_FILE.read_text(encoding="utf-8"))
        value = data.get(key)
        return value if isinstance(value, str) and value else ""
    except (OSError, json.JSONDecodeError, ValueError, AttributeError, TypeError):
        return ""


def workspace_root() -> Optional[Path]:
    """The `Repos/agience` directory, or None — never a guess.

    Returns None rather than raising, because `import mantle_common` runs inside every hook and a
    raise here would take the whole capture layer down over a config value most hooks never read.
    It is loud on the way out: callers get a reason on stderr, which is the half that was missing
    when the old hard-coded paths silently addressed nothing.
    """
    from_env = os.environ.get("AGIENCE_REPOS")
    if from_env:
        p = Path(os.path.expanduser(from_env))
        if p.is_dir():
            return p
        # An override that is set and wrong is a mistake worth naming. Falling through to discovery
        # would honour a path the operator did not ask for while their own setting was ignored.
        print("mantle hooks: AGIENCE_REPOS=%s is not a directory" % from_env, file=sys.stderr)
        return None

    configured = _top_level("repos_root")
    if configured:
        p = Path(os.path.expanduser(configured))
        if p.is_dir():
            return p
        print("mantle hooks: repos_root=%s in %s is not a directory"
              % (configured, MANTLE_TARGET_FILE), file=sys.stderr)
        return None

    # There is no discovery fallback. Walking up for a marker file guesses at a layout, and the
    # guess is wrong for anyone whose checkout is not shaped like the author's — it either finds
    # nothing and reports a config error, or finds a lookalike and addresses the wrong tree. The
    # location is configuration, so it is stated once rather than inferred on every hook run.
    print("mantle hooks: cannot locate the agience workspace. Set it once, locally:\n"
          "  python ~/.claude/hooks/mantle_target.py --repos-root <path-to-Repos/agience>\n"
          "  (or export AGIENCE_REPOS=<path> for a one-off)", file=sys.stderr)
    return None

#: Reads. `recall_context` runs before every prompt, so this is latency the user waits through
#: and it should be as short as it can be WITHOUT being shorter than the work.
#:
#: The budget must clear the work, not merely approach it. Measured against a node with 98
#: artifacts, a recall takes 4.47s at size=5 and 5.15s at size=30, so a 5s budget sits below some
#: ordinary calls. A read that overruns returns None, `recall()` turns that into `[]`, and the
#: hook logs `no-hits` — the same line it logs when the store genuinely had nothing. A budget set
#: too low therefore does not degrade the recall, it makes a slow recall indistinguishable from an
#: empty one.
#:
#: 12s is chosen against the HOOK budget, not against taste: `UserPromptSubmit` is registered at
#: 10s in settings.json, so anything at or above that is unreachable and the HTTP layer would
#: never be the thing that gave up. Under it, a genuinely dead service still fails fast enough
#: to be invisible, and a merely slow one now completes.
#:
#: The 4.5s itself is fixed overhead, not per-hit: size 5, 15 and 30 cost 4.47s, 4.99s and 5.15s.
#: Asking for fewer hits therefore saves nothing, and asking for more is nearly free — which is
#: what makes a wide candidate set for client-side re-ranking affordable. Why an empty-ish store
#: costs 4.5s at all is a Mantle question, not this file's, and it is worth asking.
_HTTP_TIMEOUT_SECONDS = 12

#: Writes. A create/update carries the whole document and the server does content encryption, SSE
#: indexing and the density pass before it answers -- seconds for anything substantial. At the
#: read timeout a 15KB write completed server-side and then timed out waiting for the reply, so
#: the hook recorded a failure, never cached the returned id, and would have created a second
#: copy on the next write of the same file. A write that succeeds must not be reported as failed:
#: that is how duplicates get made by the very code meant to prevent them.
#:
#: The same bug returns at a larger size, which is why this is 150 and not 60. A rendered
#: session transcript capped at the then-800_000-char limit measured 64.2s to write -- over a 60s
#: budget -- so every large transcript archived server-side and reported failure client-side,
#: with `archive_transcript` never once recording an id. Note what does not
#: reproduce it: `'x '*400000` at the same byte count writes fine, because cost here is SSE
#: indexing over distinct terms, not bytes. Probe this path with real prose or it reads as healthy.
#:
#: 150 buys headroom, but the durable fix is that callers must treat a timeout as unknown rather
#: than failed and reconcile against the store -- see `_find_by_title` and its use in
#: `archive_transcript.py`. A timeout can always be provoked by a big enough document; only the
#: reconcile makes it non-damaging.
_HTTP_WRITE_TIMEOUT_SECONDS = 150


def _post_json(url: str, payload: Dict[str, Any] = None, *, form: Dict[str, str] = None,
                headers: Optional[Dict[str, str]] = None,
                timeout: int = _HTTP_TIMEOUT_SECONDS) -> Optional[Dict[str, Any]]:
    """POST JSON or form-encoded data; return the parsed JSON response, or None on any failure."""
    try:
        if form is not None:
            data = urllib.parse.urlencode(form).encode("ascii")
            req_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        else:
            data = json.dumps(payload or {}).encode("utf-8")
            req_headers = {"Content-Type": "application/json"}
        req_headers.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError, ValueError):
        return None


def get_access_token() -> Optional[str]:
    """A bearer for the active target: a static one if it has one, else minted from the refresh token.

    Two ways in, because the two nodes are authenticated differently. `dev` sits behind an Origin
    with dynamic client registration, so it has a `dcr_` client and a refresh token, and this mints
    a short-lived access token per call. `home` is its own authority whose mantle verifies a token
    signed by the keyset in its own `KEYS_DIR` — measured 2026-08-13: a 30-day token minted by
    `dev_mint_token.py --keys-dir <home>/keys` is accepted by `mantle.home.agience.ai` and resolves
    to the subject the keyset derives. So home needs no OAuth round trip, no registered client and
    no password, and the same bearer serves both this and Claude Code's `mcpServers` header.

    A static bearer is preferred when present rather than used as a fallback: reaching for a refresh
    grant against an Origin that has no client registered for it would fail slowly, once per hook
    run, to arrive at a token the target already holds.

    It expires: 30 days is long enough to forget and short enough to strand a node — re-mint with
    the same command and rewrite the target file. That is the cost of not running an OAuth client
    here, and it is the honest trade: the alternative is a refresh token that never expires at all.
    """
    static = _TARGET.get("mcp_bearer")
    if isinstance(static, str) and static.strip():
        return static.strip()
    try:
        refresh_token = Path(MANTLE_REFRESH_TOKEN_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not refresh_token:
        return None

    body = _post_json(MANTLE_TOKEN_URL, form={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": MANTLE_CLIENT_ID,
    })
    if not body:
        return None
    return body.get("access_token")


#: Tools that carry a document and index it. Everything else is a read.
_WRITE_TOOLS = {"create_artifact", "update_artifact", "delete_artifact"}


def mcp_call(tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call a mantle MCP tool; return its `structuredContent`, or None on any failure.

    A tool-level error (`isError: true` -- a 4xx/5xx the REST handler raised) also returns
    None: every caller here treats "mantle refused" the same as "mantle unreachable" -- nothing
    a best-effort hook can act on differently.
    """
    token = get_access_token()
    if not token:
        return None
    resp = _post_json(
        MANTLE_MCP_URL,
        {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        },
        timeout=(_HTTP_WRITE_TIMEOUT_SECONDS if tool_name in _WRITE_TOOLS
                 else _HTTP_TIMEOUT_SECONDS),
    )
    if not resp or "result" not in resp:
        return None
    result = resp["result"]
    if result.get("isError"):
        return None
    return result.get("structuredContent")


def recall(query_text: str, *, size: int = 5) -> List[Dict[str, Any]]:
    """The union of both arms, ordered by the vector arm, cut to the extent the signal supports.

    The arms are complementary rather than redundant. Measured on seven questions whose answers
    are verified present in the store:

        text only     hit@1 1/7    hit@3 2/7
        vector only   hit@1 4/7    hit@3 6/7
        UNION         hit@1 4/7    hit@3 7/7

    Their misses do not coincide. Text alone takes "why does it keep forgetting" at #1 where the
    vector arm misses it outright; the vector arm takes the other six. Either arm alone is the
    weaker of the three.

    No fusion constant, and none is needed. There is no weight, no interleave ratio and no RRF
    `k` here, because nothing compares a score across two scales:

        both arms contribute CANDIDATES
        the vector arm ORDERS them           one metric applied to everything, not a blend
        text-only survivors append in order  nothing is discarded
        adaptive_cut decides HOW MANY        derived per query, per the aperture

    A fusion weight exists to reconcile two incomparable score scales. Not comparing them removes
    the need for one rather than tuning it.

    Degrades, never fails. With the embedder daemon down there is no vector and no cut, and this
    is the text-only call: weaker, and still an answer. Every caller is a hook running in front of
    a prompt, so nothing here may raise.
    """
    # The vector arm is off by default, and the reason is canon rather than breakage.
    #
    # `agience-pharos/genesis/RETRIEVAL-THE-ENTROPTICS-WAY.md` (state: CANON) bans cosine by name:
    # "A chosen metric. Assumes the space is isotropic and that angle is nearness. Nothing derives
    # it." A client embedder exists for exactly one purpose - to feed `ORDER_SEMANTIC`, the cosine
    # arm - so keeping it means running the one ranker the design forbids.
    #
    # There is a model-free arm that does the same job. `mantle.search.ranking` orders by REACH:
    # how far each survivor's own position reaches toward what the question is about, propagated
    # through the ontology, cut by the aperture's `k_signal`. No vector, no model, no chosen
    # metric. `71/home` exports `MANTLE_ONTOLOGY_HOST=ember`, so that arm is already on and the
    # server selects it without being asked - see `router_accessor._order`.
    #
    # Text-only is a measured mode rather than a new degraded one: a period when `embed()` returned
    # `(None, None)` on every call ran 183 context-injecting recalls text-only, and the arm being
    # off is that same mode chosen deliberately instead of by a dead path.
    #
    # What the vector arm bought is not nothing, and is recorded below: the lexical index covers
    # the offer only (title/description/tags), so a question sharing no words with an artifact's
    # offer cannot reach it, and cosine escaped that cap. Whether reach escapes it on this node is
    # measurable and unmeasured, and that is the experiment to run before arguing the vector arm
    # back. It must be scored against reach rather than against coverage, which is what the
    # 4/7-vs-1/7 figure above compares and why that number does not settle it.
    #
    # `MANTLE_HOOK_VECTOR_ARM=1` restores it. That also needs the daemon's space to equal the
    # node's AnchorSet `model_id`. They differ today (client `model2vec:minishlab/potion-base-8M`,
    # home `all-MiniLM-L6-v2`), so it would send vectors home rejects.
    if os.environ.get("MANTLE_HOOK_VECTOR_ARM") == "1":
        try:                                # local import: hooks that never recall never load it
            import embedder
            vectors, space = embedder.embed([query_text])
        except Exception:                   # noqa: BLE001 - a text-to-numbers service, never fatal
            vectors, space = None, None
    else:
        vectors, space = None, None

    def _hits(extra: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        args: Dict[str, Any] = {"query_text": query_text, "size": size}
        args.update(extra or {})
        return (mcp_call("recall", args) or {}).get("hits") or []

    if not vectors:
        return _hits()

    # The two arms run concurrently, because neither reads the other's answer. Measured, 1204 ms
    # back-to-back against 739 ms overlapped for the same two calls and the same results, on one
    # `ThreadPoolExecutor`. Both are network waits, so the GIL is released for essentially the
    # whole of each.
    #
    # The time is on the server, not here: embedding costs 0-2 ms and the cut 2-4 ms, so all of
    # this hook's client-side work is ~6 ms against text ~435 ms and vector ~580-770 ms.
    # Optimising anything on this side is rounding error, and the only lever is refusing to pay
    # the two latencies in series.
    #
    # The text arm is the gate and the vector arm is the reach. Kept apart, both properties hold.
    #
    # Supplying `query_text` alongside the vector makes the server rank the vector arm WITHIN the
    # lexical candidates. That is what produced the free quiet gate — but it also caps the vector
    # arm at what the lexical arm admits, and the lexical arm indexes the OFFER only (title,
    # description, tags — see `pipeline_unified._OFFER_FIELDS`). So a question whose words appear
    # nowhere in an artifact's title or tags cannot reach it AT ALL, however close the meaning is.
    #
    # Measured: `how does authorization work in the lattice` cannot reach `README.md` through the
    # lexical arm, because nothing in that title matches the question. A baseline measured against
    # legacy postings written before indexing became offer-only rests on index entries the current
    # write path does not produce.
    #
    # Separating them keeps the gate without the cap: the TEXT call decides whether this prompt
    # has anything in the store at all, and the VECTOR call searches the whole corpus by meaning.
    # A conversational turn still injects nothing, because the gate is evaluated on the text arm
    # exactly as before — see `_text_arm_is_silent` below.
    #
    # This must not become the vector arm alone. Nearest neighbours always exist, so a pure vector
    # recall can never answer "nothing here": asked about `thanks, looks good` it returns the
    # three closest things in the store.
    #
    # The vector call carries `query_text`, and dropping it is a trap that measures well. Sending
    # the vector alone is ~2x faster server-side (text 355 ms, vector 201 ms, both 498 ms — they
    # run in series, so supplying both repeats the lexical arm) and it
    # delivers the same 6/7 on the eval. It is still wrong, because it deletes the quiet gate:
    #
    #     prompt                 text only   PURE vector   text+vector
    #     'thanks, looks good'       0            3             0
    #     'ok' / 'nice'              0           2-3            0
    #
    # The gate is the lexical arm. Nearest neighbours always exist, so a pure vector query can
    # never answer "nothing here" -- it returns the closest three things in the store to "thanks,
    # looks good". The lexical arm answers nothing when no offer term matches, and `text+vector`
    # means "lexical supplies the candidates, the vector orders them". That composition is what
    # makes a conversational turn inject nothing with no threshold anywhere, which is the property
    # six separate calibrated constructions failed to produce.
    #
    # The extra latency is the price of the gate and it is worth paying. An eval scored on
    # questions cannot see this, because it never asks a question that has no answer.
    _vector_args = {"query_text": "", "vector": vectors[0], "space_id": space}
    import concurrent.futures as _cf
    try:
        with _cf.ThreadPoolExecutor(max_workers=2) as pool:
            fut_text = pool.submit(_hits)
            fut_vec = pool.submit(_hits, _vector_args)
            text_hits, vector_hits = fut_text.result(), fut_vec.result()
    except Exception:                       # noqa: BLE001 - fall back to plain sequential calls
        text_hits, vector_hits = _hits(), _hits(_vector_args)

    # Never cut across two scales. Handing `adaptive_cut` one list holding cosine (~0.28) from the
    # vector arm followed by BM25 (~6.0) from the text arm puts the largest relative gap at the
    # scale boundary rather than at a signal boundary, so the cut lands there and keeps only the
    # vector block. That reads well while the vector arm is strong and fails the moment it is not:
    # with the vector arm returning 1-2 hits it keeps 1-2 and discards every text hit, including a
    # right answer at text rank #2 — 7/7 down to 3/7 with nothing about the ranking changed.
    #
    # A cut is a reading of one measurement. Each arm's scores are self-consistent and the two are
    # not comparable, which is the same fact that makes a fusion weight unnecessary above. Each
    # arm is cut against its own frame and its own scores, and the survivors are unioned: no
    # constant appears, and no score is compared across arms.
    #
    # The gate: the text arm answers nothing when no offer term matches, which is what makes a
    # conversational turn inject nothing with no threshold anywhere. It is evaluated here, on the
    # text arm alone, so the vector arm's unconditional nearest-neighbours can never open it.
    if not text_hits:
        return []

    kept: List[Dict[str, Any]] = []
    for arm in (vector_hits, text_hits):
        if not arm:
            continue
        kept.extend(_cut_one_arm(list(arm)))

    seen: set = set()
    union: List[Dict[str, Any]] = []
    for hit in kept:
        key = hit.get("id")
        if key and key not in seen:
            seen.add(key)
            union.append(hit)
    return union


def _cut_one_arm(arm: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The part of ONE arm's ranking that its own signal supports.

    The frame is each candidate's content in score order — the hit's entropy-cut densest span,
    which is what `recall` already returns and what `adaptive_cut` asks for. `None` is the cut's
    own word for "no read available" and is passed through as "keep this arm whole" rather than
    turned into a number here.
    """
    try:
        import embedder
        keep = embedder.cut(
            [" ".join(str(h.get("content") or h.get("preview")
                          or h.get("title") or h.get("name") or "").split())
             for h in arm],
            [float(h.get("score") or 0.0) for h in arm],
        )
    except Exception:                       # noqa: BLE001
        keep = None
    return arm[:keep] if isinstance(keep, int) and keep > 0 else arm

def find_by_title(title: str) -> Optional[str]:
    """The id of an artifact whose title is EXACTLY `title`, or None.

    This is the timeout reconciler, and it exists because a write that times out is unknown,
    not failed. The server finishes encrypting and indexing regardless of whether the client is
    still listening, so `create_artifact` returning None covers two opposite outcomes: nothing was
    stored, or something was stored and we do not know its id. Treating both as failure is what
    turns one slow write into an unbounded pile of duplicates -- the caller re-creates next time
    because its index still shows nothing tracked.

    Matching is on the exact title rather than on relevance: `recall` scores, so its top hit for a
    session title is whatever scored best, which on a store holding several transcripts is not
    reliably the one just written. The caller's titles are deterministic (`store_file` uses the
    relative path, `archive_transcript` a session-derived string), so exact equality is available
    and is the only comparison that cannot adopt the wrong artifact.
    """
    for hit in recall(f'title:"{title}"', size=10):
        if isinstance(hit, dict) and hit.get("title") == title:
            artifact_id = hit.get("id")
            if isinstance(artifact_id, str) and artifact_id:
                return artifact_id
    return None


def _artifact_id_of(data: Optional[Dict[str, Any]]) -> Optional[str]:
    """The stored artifact's id out of a create/update response, or None.

    The write tools answer with the artifact object itself; `result` is checked too so a
    response that ever grows an envelope does not silently start returning None here.
    """
    if not data:
        return None
    if isinstance(data.get("id"), str):
        return data["id"]
    inner = data.get("result")
    if isinstance(inner, dict) and isinstance(inner.get("id"), str):
        return inner["id"]
    return None


#: The one collection every hook artifact is filed in. Its own identity, so creating it is
#: idempotent and no id has to be hardcoded or configured — which matters because these hooks
#: switch between the `dev` and `home` targets and each node mints its own ids.
_CONTAINER_IDENTITY = "container:claude-code"

#: Resolved once per process. A hook is short-lived, so this costs at most one extra call per
#: WRITE hook run; `recall_context` never calls it, so nothing is added to the prompt path.
_container_id: Optional[str] = None
_container_looked_up = False


def _claude_code_container() -> Optional[str]:
    """The collection id for hook artifacts, creating it on first use. ``None`` if unavailable.

    Why a collection at all: Mantle keys its encrypted index per origin root, and a top-level
    artifact is its own origin root — so every artifact stored this way was a separately keyed
    owner that a recall had to read individually. Measured on 71/dev: 115 self-rooted artifacts,
    4,520 file probes for a ten-term query. One shared container makes them one owner.

    Never raises, and a failure degrades to storing top-level rather than dropping the write:
    without a container the artifact is stored top-level exactly as before — slower to recall
    across, never lost. That ordering matters, because a capture hook that refused to capture
    when a collection could not be resolved would trade a performance property for a data one.
    """
    global _container_id, _container_looked_up
    if _container_looked_up:
        return _container_id
    _container_looked_up = True
    data = mcp_call("create_artifact", {
        "identity": _CONTAINER_IDENTITY,
        "name": "Claude Code",
        "content_type": "application/vnd.agience.collection+json",
        "description": "Artifacts captured by the Claude Code hooks.",
        "content": "Files, transcripts and commits captured from Claude Code sessions.",
        "context": json.dumps({"title": "Claude Code", "tags": ["claude-code"]}),
    })
    artifact_id = _artifact_id_of(data)
    _container_id = artifact_id if isinstance(artifact_id, str) and artifact_id else None
    return _container_id


def store_artifact(*, identity: str, content: str, name: str, content_type: str,
                   description: str = "",
                   context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Store a thing under a stable NAME, creating or updating as needed. Returns its id.

    The idempotent write, and the reason these hooks no longer keep an id index.

    `identity` names the thing -- `file:c:/repo/README.md`, `session:7c7bcb7b` -- and Mantle
    derives the artifact id from it (`services/artifact_identity`). Calling this twice with one
    identity therefore leaves one artifact holding the newer content, on every path: whether the
    first call's reply arrived, whether this process ever saw it, whether two hook processes
    raced each other.

    That property is worth stating against what it replaces. Minting the id per write instead
    would leave remembering it locally as the only way to update rather than duplicate -- and a
    write whose reply is lost still succeeds on the server, leaving the client with nothing recorded
    and the next write creating a second root that nothing would ever reconcile. Measured before
    this landed: one README as two artifacts three minutes apart, one session as five. None of
    those failure modes has a target here, because there is no remembered id to lose and no
    create-or-update decision for a race to get wrong.

    A `None` return is now genuinely just "the call did not come back". Retrying is safe and
    lands on the same artifact, which is what makes the timeout question uninteresting.
    """
    args = {
        "identity": identity, "content": content, "name": name,
        "content_type": content_type, "description": description,
    }
    if context is not None:
        args["context"] = json.dumps(context)

    # Every hook artifact goes in one collection, and this is a recall-cost decision rather
    # than tidiness. Mantle keys its encrypted index per origin root
    # (`search/mantle/principal.resolve_cell_principal`), and a top-level artifact is its own
    # origin root — so 115 top-level artifacts were 115 separately keyed owners, each needing
    # its own read on every recall. Filing them in one collection gives them one shared root,
    # which is one owner: the fan-out stops tracking how much has been stored.
    #
    # `identity` still applies inside a collection (Mantle change, 2026-08-16): it names the
    # root there, and the member is written committed and overwritten in place rather than
    # forking a draft — so a mirror of a file that just changed is what `recall` answers with.
    container = _claude_code_container()
    if container:
        args["container_id"] = container

    # The vector rides the write that produced the content. Mantle never embeds -- "vectors
    # arrive from a caller" -- so the only moment this artifact can acquire one is here, on the
    # write that knows what it says. Embedding it later would mean re-reading every artifact and
    # guessing which model each was stored under.
    #
    # Best-effort and silent, like everything else in this module: with the embedder down the
    # write still happens and the artifact is lexical-only, which is exactly what every write
    # was before the semantic arm existed. A text-to-numbers service being unavailable is not a
    # reason to lose a document.
    try:
        from embedder import embed as _embed
        joined = chr(10).join([name or '', description or '', content or ''])
        # No truncation: a `[:20000]` cut here would mean a long artifact's vector represents only
        # its opening -- silently, with nothing downstream able to tell that the rest of the
        # document had no bearing on where it sits in the space. model2vec mean-pools and encodes
        # 100 texts in ~2.6ms, so a cut would buy nothing and cost the tail of every long document.
        vectors, space = _embed([joined])
        if vectors and space:
            args["vector"] = vectors[0]
            args["space_id"] = space
    except Exception:  # noqa: BLE001
        pass

    return _artifact_id_of(mcp_call("create_artifact", args))


def create_artifact(*, content: str, name: str, content_type: str,
                    description: str = "", context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Store a NEW artifact under a fresh id; return that id, or None on any failure.

    Prefer :func:`store_artifact` for anything that might be written more than once. This one
    mints a new artifact per call by construction, so two calls about one thing leave two copies
    and `recall` answers with whichever scored best -- which may be either of them.
    """
    args = {
        "content": content, "name": name, "content_type": content_type,
        "description": description,
    }
    if context is not None:
        args["context"] = json.dumps(context)
    return _artifact_id_of(mcp_call("create_artifact", args))


def update_artifact(artifact_id: str, *, content: Optional[str] = None,
                    name: Optional[str] = None, content_type: Optional[str] = None,
                    description: Optional[str] = None,
                    context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Rewrite an EXISTING artifact in place; return its id, or None on any failure.

    None on failure covers the case that matters to a caller holding a remembered id: the
    artifact was deleted server-side, so the id is stale. Treat it as "not there" and create
    instead -- that is what keeps a local id cache self-healing rather than permanently broken
    against a store someone cleaned up.
    """
    args: Dict[str, Any] = {"artifact_id": artifact_id}
    if content is not None:
        args["content"] = content
    if name is not None:
        args["name"] = name
    if content_type is not None:
        args["content_type"] = content_type
    if description is not None:
        args["description"] = description
    if context is not None:
        args["context"] = json.dumps(context)
    return _artifact_id_of(mcp_call("update_artifact", args))


#: Append-only record of what each hook did, one JSON object per line.
#:
#: These hooks are best-effort by design: every failure path returns quietly so a dead service
#: can never block a prompt or an edit. That is right, and it also means a hook that has stopped
#: working looks EXACTLY like a hook with nothing to say. Two separate faults hid behind that
#: this way -- a hook reading the wrong payload field, and a hook whose file did not exist -- and
#: both were invisible until someone went looking. This is the difference between "silently did
#: nothing" and "reported that it did nothing", and it is the only durable evidence that the
#: pipeline is running on every turn rather than merely configured to.
MANTLE_HOOK_LOG = Path(
    os.environ.get("MANTLE_HOOK_LOG", str(Path.home() / ".claude" / "mantle-hook.log"))
)

_LOG_MAX_BYTES = 2_000_000


def log_event(event: str, **fields: Any) -> None:
    """Record one hook firing. Never raises -- observability must not become a failure mode."""
    try:
        from datetime import datetime, timezone
        line = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            # Which store this line is about. Two runs against different nodes are otherwise
            # identical in the log, and "recall came back empty" cannot be distinguished from
            # "it came back empty on the other node".
            "target": MANTLE_TARGET_NAME,
            **fields,
        })
        MANTLE_HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
        # Cheap bound: when it gets large, keep the recent half rather than growing forever.
        try:
            if MANTLE_HOOK_LOG.stat().st_size > _LOG_MAX_BYTES:
                kept = MANTLE_HOOK_LOG.read_text(encoding="utf-8").splitlines()[-1000:]
                MANTLE_HOOK_LOG.write_text("\n".join(kept) + "\n", encoding="utf-8")
        except OSError:
            pass
        with MANTLE_HOOK_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def read_stdin_json() -> Dict[str, Any]:
    """The hook's input payload from stdin. {} if it is missing or not valid JSON -- a hook
    that cannot parse its own input has nothing safe to do but no-op."""
    import sys
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}
