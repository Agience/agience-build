#!/usr/bin/env python3
"""A resident embedder: load the static model once, answer over a socket in milliseconds.

Why a daemon and not an import: model2vec encodes in ~3 ms and loads in ~6 s, measured from local
disk with the hub offline, so the 6 s is library and tokenizer initialisation rather than fetching.
Every hook run is a fresh process, so an inline import would pay that 6 s on every prompt: ten
times the entire recall budget, to do 3 ms of work. The load is not avoidable, only relocatable,
and this is where it goes.

Why model2vec and not a transformer encoder: not speed — determinism. An anchor's id is
`uuid5(sha256(label ‖ model_id ‖ embedding))` and that id is the cluster id: it names the cell
storage path, the HKDF key `info`, the AEAD associated data and the mesh region. Two nodes must
compute the same id from the same content or their cells never compare — and Mantle's README is
explicit that this failure is silent, answering 200 with nothing found. A static lookup table is
bit-reproducible across machines and versions; a neural encoder is not, because batching, kernel
selection and device all move the last bits. Verified here: the same sentence encodes to a
bitwise-identical vector across calls.

Mantle still embeds nothing. This is client-side, like the ranking and for the same reason:
"vectors arrive from a caller" is the contract, and the caller is where a model is allowed to
live. The daemon binds loopback only and holds no credential — it converts text to numbers and
knows nothing about the store.

    python embedder.py serve            # start it (blocks)
    python embedder.py probe            # check it, print space_id and dim

    from embedder import embed, space_id
    vecs = embed(["some text"])         # None if the daemon is not up — never raises
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mantle_common import workspace_root  # noqa: E402
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

#: The model, pinned by name here and by CONTENT in `space_id` below.
MODEL = os.environ.get("MANTLE_EMBED_MODEL", "minishlab/potion-base-8M")

#: Loopback only. This is a text-to-numbers service with no authorization of its own, so it must
#: not be reachable from anywhere that has not already got onto this machine.
HOST = "127.0.0.1"
PORT = int(os.environ.get("MANTLE_EMBED_PORT", "8199"))

#: 127.0.0.1, never "localhost". Measured: python's urllib takes 2.048s to reach
#: `http://localhost:<port>` and 0.018s to reach `http://127.0.0.1:<port>` on this box — an
#: IPv6-then-IPv4 connect fallback, paid on every call.
_URL = f"http://{HOST}:{PORT}"

#: Where the sibling repos are. The daemon is the one process that may hold them: it is resident,
#: so it pays each load once, and every hook then reaches the reads over a socket in milliseconds.
#
# A path that stops resolving here degrades silently: `embed()` returns `(None, None)` on every
# failure and never raises, so the vector arm stops contributing and `recall` falls back to the
# text-only call its own docstring calls "the weakest of the three", with nothing said. `probe` is
# the check that fires.
#
# One resolver (`workspace_root()`) rather than a hardcoded default per constant, so the root has
# one place to be wrong instead of three.
_ROOT = workspace_root()
_REPOS = str(_ROOT) if _ROOT else ""
PRISM_SRC = os.environ.get("PRISM_SRC", f"{_REPOS}/agience-prism/py/src")
ENTROPTICS_SRC = os.environ.get("ENTROPTICS_SRC", f"{_REPOS}/entroptics/src")
OPTICS_PATH = os.environ.get("OPTICS_PATH", f"{_REPOS}/agience-ember/src/ember/optics.py")

_model = None
_space_id = None
_cut = None            # prism.adaptive_cut, once the instrument is registered


def _load():
    """The model and its space id, loaded once per process."""
    global _model, _space_id
    if _model is not None:
        return _model, _space_id
    from model2vec import StaticModel
    _model = StaticModel.from_pretrained(MODEL)

    # The space id is a hash of the weights, not the model's name. `minishlab/potion-base-8M`
    # before and after a version bump are different functions producing different vectors, and
    # every anchor id is content-addressed over `(label, model_id, embedding)`. A `space_id` that
    # named only the repo would let a silent upgrade mint region ids nothing else computes: the
    # cells stop matching, recall returns nothing, and the request still answers 200. Hashing the
    # embedding matrix makes the identifier name the function, so an upgrade announces itself as
    # a different space instead of corrupting this one.
    weights = _model.embedding
    digest = hashlib.sha256(
        weights.tobytes() + str(weights.shape).encode() + str(weights.dtype).encode()
    ).hexdigest()[:16]
    _space_id = f"model2vec:{MODEL}:{digest}"
    return _model, _space_id


def _load_cut():
    """`prism.adaptive_cut`, with `ember.optics` registered as the read instrument. Once.

    Why the cut lives in the daemon: `adaptive_cut` replaces every constant a caller would
    otherwise pick -- how many results to keep, where relevance stops being signal -- with two
    derived reads: the aperture's `K_signal` (Marchenko-Pastur, parameter-free) answers whether
    there is structure, and a scale-invariant largest-relative-gap answers where it breaks.
    "Composed, the pair needs no constant at all."

    It reads through prism's injected `read` contract, and the registered instrument is
    `ember.optics` -- which exists because entering entroptics' front door applies an entropy
    fold guard that destroys a sparse carrier (measured: 256 channels folded to F_eff = 1 and
    reported as K_signal = 1, indistinguishable at the call site from one real mode). So the
    wrapper is not optional and reaching past it to entroptics is the documented way to get a
    wrong answer that looks right.

    Loaded by path, not by package: `import ember.optics` pulls `ember/__init__.py` and its
    tree -- measured at over 600s, which is why this looked impossible in a hook. `optics.py`
    itself imports only stdlib, numpy and `prism.rounding`, and loads in ~1.05s from its file.
    It must be in `sys.modules` before `exec_module`, or its dataclasses cannot resolve
    `__module__` and raise on a None lookup.
    """
    global _cut
    if _cut is not None:
        return _cut
    import importlib.util
    os.environ.setdefault("EMBER_ADAPTIVE_MODE", "on")
    for path in (PRISM_SRC, ENTROPTICS_SRC):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location("ember_optics", OPTICS_PATH)
    optics = importlib.util.module_from_spec(spec)
    sys.modules["ember_optics"] = optics
    spec.loader.exec_module(optics)
    from prism import instrument, adaptive_cut
    instrument.set_default(optics)
    _cut = adaptive_cut
    return _cut


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):                                    # noqa: N802 - stdlib naming
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n)) or {}
            model, space = _load()

            if self.path.rstrip("/").endswith("cut"):
                # The candidates' own features, in score order, are the frame `adaptive_cut`
                # asks for -- and its docstring notes no caller supplied one before. With it the
                # read is the instrument's real `k_signal` rather than an approximation of it.
                texts = [str(t) for t in (payload.get("texts") or [])]
                scores = [float(x) for x in (payload.get("scores") or [])]
                frame = model.encode(texts) if texts else None
                cut = _load_cut()
                # BM25 convention: negative, most-negative = best.
                keep = cut.cut([-s for s in scores], frame=frame)
                body = json.dumps({"keep": keep, "n": len(scores),
                                   "available": cut.is_available()}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            vectors = model.encode([str(t) for t in (payload.get("texts") or [])])
            body = json.dumps({
                "vectors": [[float(x) for x in row] for row in vectors],
                "space_id": space, "dim": int(vectors.shape[1]),
            }).encode()
            self.send_response(200)
        except Exception as exc:                          # noqa: BLE001
            body = json.dumps({"error": str(exc)[:200]}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        """Silent. One line per prompt on a service called before every prompt is noise, and the
        hook log already records what was asked and what came back."""


#: How long to spend finding out whether the daemon is there at all, before spending `timeout` on
#: asking it for anything. Loopback either answers this immediately or is not listening.
_LIVENESS_TIMEOUT = 0.15


def _listening(timeout: float = _LIVENESS_TIMEOUT) -> bool:
    """Is anything accepting on the daemon's port? One connect, then closed.

    Without this check a dead daemon costs 2.07s on every prompt: on this box the port is dropped
    rather than refused, so nothing sends an RST and a connect burns its whole timeout on SYN
    retransmits. `embed()` defaults to `timeout=5.0` and `recall` calls it in front of every
    prompt, so with the daemon down the hook would pay that full stall for a `(None, None)` it was
    always going to get — a fifth of the 10s `UserPromptSubmit` budget spent discovering that a
    service is switched off.

    "Connection refused is instant" is an assumption about the network stack rather than a property
    of loopback, and here it does not hold: 127.0.0.1 at timeout=0.1 returns in 0.105s and at 2.0
    in 2.005s. It is the timeout being measured, not the service.

    When the daemon is up this costs one loopback connect (~0.2ms) and changes nothing.
    """
    import socket
    try:
        socket.create_connection((HOST, PORT), timeout).close()
        return True
    except OSError:
        return False


def embed(texts, timeout: float = 5.0):
    """Vectors for `texts` as `(vectors, space_id)`, or `(None, None)` if unavailable.

    Never raises. Every caller is a hook running in front of a prompt, and a text-to-numbers
    service being down is not a reason to fail an edit or block a question. The absent case is
    the same one that held before any of this existed: the artifact is lexical-only.

    A vector from here is not usable against every node. `recall`'s `space_id` must equal the
    seeded AnchorSet's `model_id`, and a node ranking in a different space answers 400 naming both.
    This daemon's space is `model2vec:minishlab/potion-base-8M:<digest>`, while `71/home` seeds its
    AnchorSet from `all-MiniLM-L6-v2`, dim 384. They are different spaces, so home cannot use what
    this produces. Reconciling them is a re-seed: an anchor id is
    `uuid5(sha256(label ‖ model_id ‖ embedding))` and that id names the cell storage path, the HKDF
    `info`, the AEAD associated data and the mesh region, so changing the space re-derives every one
    of them, whichever side moves.
    """
    if not texts:
        return None, None
    if not _listening():
        return None, None
    try:
        req = urllib.request.Request(
            f"{_URL}/embed",
            data=json.dumps({"texts": list(texts)}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
        vectors = body.get("vectors")
        return (vectors, body.get("space_id")) if vectors else (None, None)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None, None


def cut(texts, scores, timeout: float = 10.0):
    """How many of `texts` to keep, derived. `None` when the daemon or instrument is absent.

    `None` is `adaptive_cut`'s own word for "defer to the caller's baseline" and it is passed
    through unchanged rather than turned into a number here -- inventing one would be exactly the
    constant this whole path removes.
    """
    if not scores:
        return None
    try:
        req = urllib.request.Request(
            f"{_URL}/cut",
            data=json.dumps({"texts": list(texts), "scores": list(scores)}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (json.loads(resp.read()) or {}).get("keep")
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def space_id(timeout: float = 5.0):
    """The daemon's space id, or None. One round trip; the caller should hold it for a run."""
    _v, space = embed(["."], timeout=timeout)
    return space


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "probe":
        vectors, space = embed(["the light cone authorizes a recall"])
        if not vectors:
            print(f"embedder not reachable at {_URL} — start it with: python embedder.py serve")
            return 1
        print(f"space_id : {space}")
        print(f"dim      : {len(vectors[0])}")
        return 0
    print(f"loading {MODEL} …", flush=True)
    _model_, space = _load()
    print(f"space_id : {space}")
    print(f"serving  : {_URL}/embed   (loopback only)", flush=True)
    HTTPServer((HOST, PORT), _Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
