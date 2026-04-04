from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import InMemoryRepository


def test_edge_upsert_isolation():
    """Edges in different notebooks with the same source pair must not overwrite each other."""
    repo = InMemoryRepository()

    notebook_1 = repo.create_notebook("Notebook 1")
    notebook_2 = repo.create_notebook("Notebook 2")

    source_a = repo.create_source(notebook_1["id"], "https://a.example", "A", status="ready")
    source_b = repo.create_source(notebook_1["id"], "https://b.example", "B", status="ready")

    repo.create_edge(notebook_1["id"], source_a["id"], source_b["id"], similarity=0.9)
    repo.create_edge(notebook_2["id"], source_a["id"], source_b["id"], similarity=0.5)

    edges_1 = repo.get_edges(notebook_1["id"])
    assert len(edges_1) == 1
    assert edges_1[0]["similarity"] == 0.9, (
        f"notebook-1 edge similarity was overwritten: expected 0.9, got {edges_1[0]['similarity']}"
    )

    edges_2 = repo.get_edges(notebook_2["id"])
    assert len(edges_2) == 1
    assert edges_2[0]["similarity"] == 0.5


def test_self_edge_rejected():
    """upsert_edge with source_a == source_b must raise ValueError before any DB call."""
    repo = InMemoryRepository()
    notebook = repo.create_notebook("Notebook")
    source = repo.create_source(notebook["id"], "https://a.example", "A", status="ready")

    with pytest.raises(ValueError, match="Self-edges are not allowed"):
        repo.create_edge(notebook["id"], source["id"], source["id"], similarity=1.0)


def test_missing_notebook_id_rejected():
    """upsert_edge with notebook_id=None or empty string must raise ValueError."""
    repo = InMemoryRepository()
    notebook = repo.create_notebook("Notebook")
    source_a = repo.create_source(notebook["id"], "https://a.example", "A", status="ready")
    source_b = repo.create_source(notebook["id"], "https://b.example", "B", status="ready")

    with pytest.raises(ValueError, match="notebook_id"):
        repo.create_edge(None, source_a["id"], source_b["id"], similarity=0.8)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="notebook_id"):
        repo.create_edge("", source_a["id"], source_b["id"], similarity=0.8)
