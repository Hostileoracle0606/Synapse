"""Graph computation — keyword-overlap edges with no LLM calls.

The previous implementation used per-chunk embeddings + cosine similarity for
edges and a Gemini call per edge for labels. The hybrid architecture skips
embeddings entirely, so edges are now computed from shared keyword overlap on
summaries + titles. This is ~free, deterministic, and good enough for a
research-graph view; precise relationship labels happen on demand at chat time.
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from typing import Dict, List

logger = logging.getLogger(__name__)


# A small English stopword list — enough to filter the worst noise without
# pulling in NLTK. Keyword overlap is robust to the long tail of stopwords
# leaking through, since shared content words dominate the score.
_STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are as at be because been before being
    below between both but by could did do does doing down during each few for from further had
    has have having he her here hers herself him himself his how i if in into is it its itself
    just me more most my myself nor not now of off on once only or other our ours ourselves out
    over own same she should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was we were what when where which
    while who whom why will with would you your yours yourself yourselves
    can may might must shall should also however therefore thus
    """.split()
)

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]{2,}")


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [
        match.group(0).lower()
        for match in _TOKEN_RE.finditer(text)
        if match.group(0).lower() not in _STOPWORDS
    ]


def _doc_signature(doc: Dict) -> Counter:
    """Build a token-frequency Counter from title + summary + (optional) content."""
    parts = [
        doc.get("title") or "",
        doc.get("summary") or "",
        # Content is sometimes huge — cap to keep edge computation fast.
        (doc.get("content") or "")[:4000],
    ]
    tokens = _tokenize(" ".join(parts))
    return Counter(tokens)


def _jaccard_weighted(a: Counter, b: Counter) -> float:
    """Weighted Jaccard similarity over token Counters.

    More forgiving than plain Jaccard for short text — token frequency
    contributes to overlap, so a token shared 3-times-by-3-times scores
    higher than a token shared 1-by-1.
    """
    if not a or not b:
        return 0.0
    shared_keys = set(a.keys()) & set(b.keys())
    if not shared_keys:
        return 0.0
    intersection = sum(min(a[k], b[k]) for k in shared_keys)
    union = sum((a | b).values())
    if union == 0:
        return 0.0
    return intersection / union


def _shared_keywords(a: Counter, b: Counter, top_n: int = 3) -> List[str]:
    """Pick the strongest shared tokens to use as a relationship label."""
    shared = [(k, min(a[k], b[k])) for k in a.keys() & b.keys()]
    shared.sort(key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in shared[:top_n]]


def compute_edges(
    docs: List[Dict],
    threshold: float = 0.05,
) -> List[Dict]:
    """Compute edges by weighted Jaccard overlap on token signatures.

    Two-pass strategy:
    1. **Threshold pass** — emit one edge for every pair scoring >= threshold.
       Typical "related" pairs land in the 0.05–0.20 range with our keyword
       Jaccard; this captures the bulk of the graph.
    2. **Connectivity pass** — for any source that ended up with zero edges
       after pass 1, add a single edge to its highest-similarity peer (even
       if that score is below threshold). This guarantees no orphan nodes
       in the graph view, without flooding densely-related corpora with
       weak edges.
    """
    logger.info("Computing keyword-overlap edges for %d documents (threshold=%.2f)", len(docs), threshold)
    t0 = time.monotonic()

    if len(docs) < 2:
        return []

    signatures = {doc["id"]: _doc_signature(doc) for doc in docs}

    # ---------- Pass 1: threshold edges ------------------------------------
    edges: List[Dict] = []
    seen_pairs: set[frozenset] = set()
    # Per-source best peer (used for the connectivity pass below)
    best_peer: Dict[str, tuple[str, float]] = {}

    total_pairs = 0
    for index, doc in enumerate(docs):
        sig_a = signatures[doc["id"]]
        for other in docs[index + 1 :]:
            total_pairs += 1
            sig_b = signatures[other["id"]]
            similarity = _jaccard_weighted(sig_a, sig_b)

            # Track the best peer for both endpoints (used by pass 2)
            for a, b in ((doc["id"], other["id"]), (other["id"], doc["id"])):
                cur = best_peer.get(a)
                if cur is None or similarity > cur[1]:
                    best_peer[a] = (b, similarity)

            if similarity >= threshold:
                shared = _shared_keywords(sig_a, sig_b)
                relationship = (
                    "shared: " + ", ".join(shared) if shared else "related topics"
                )
                edges.append(
                    {
                        "source_a": doc["id"],
                        "source_b": other["id"],
                        "similarity": round(similarity, 4),
                        "relationship": relationship,
                    }
                )
                seen_pairs.add(frozenset((doc["id"], other["id"])))

    # ---------- Pass 2: connectivity for orphan nodes ----------------------
    connected: set[str] = set()
    for edge in edges:
        connected.add(edge["source_a"])
        connected.add(edge["source_b"])

    orphan_edges_added = 0
    for doc in docs:
        if doc["id"] in connected:
            continue
        peer = best_peer.get(doc["id"])
        if not peer:
            continue
        peer_id, peer_sim = peer
        pair_key = frozenset((doc["id"], peer_id))
        if pair_key in seen_pairs:
            continue
        sig_a = signatures[doc["id"]]
        sig_b = signatures[peer_id]
        shared = _shared_keywords(sig_a, sig_b)
        relationship = (
            "shared: " + ", ".join(shared) if shared else "related topics"
        )
        edges.append(
            {
                "source_a": doc["id"],
                "source_b": peer_id,
                "similarity": round(max(peer_sim, 0.001), 4),
                "relationship": relationship,
            }
        )
        seen_pairs.add(pair_key)
        connected.add(doc["id"])
        connected.add(peer_id)
        orphan_edges_added += 1

    logger.info(
        "Edge computation done in %.2fs - %d threshold + %d connectivity edges (%d/%d pairs scored)",
        time.monotonic() - t0, len(edges) - orphan_edges_added, orphan_edges_added, len(edges), total_pairs,
    )
    return edges
