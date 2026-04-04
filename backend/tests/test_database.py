from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import InMemoryRepository


def test_in_memory_repository_creates_and_reads_notebooks():
    repo = InMemoryRepository()
    notebook = repo.create_notebook("Research Notebook", seed_text="seed")

    assert notebook["title"] == "Research Notebook"
    assert notebook["status"] == "discovering"
    assert repo.get_notebook(notebook["id"])["seed_text"] == "seed"


def test_in_memory_repository_tracks_sources_edges_and_messages():
    repo = InMemoryRepository()
    notebook = repo.create_notebook("Notebook")

    source_a = repo.create_source(notebook["id"], "https://a.example", "A", status="ready")
    source_b = repo.create_source(notebook["id"], "https://b.example", "B", status="ready")
    source_c = repo.create_source(notebook["id"], "https://c.example", "C", status="processing")
    repo.update_source(source_a["id"], embedding=[1.0, 0.0], summary="alpha")
    repo.update_source(source_b["id"], embedding=[0.9, 0.1], summary="beta")

    ready = repo.get_sources_with_embeddings(notebook["id"])
    assert [item["id"] for item in ready] == [source_a["id"], source_b["id"]]

    edge = repo.create_edge(notebook["id"], source_a["id"], source_b["id"], 0.92, "related")
    duplicate = repo.create_edge(notebook["id"], source_b["id"], source_a["id"], 0.97, "updated")
    assert edge["id"] == duplicate["id"]
    assert duplicate["similarity"] == 0.97
    assert repo.get_edges(notebook["id"])[0]["relationship"] == "updated"

    message = repo.add_message(notebook["id"], "user", "Question?")
    assert message["role"] == "user"
    assert repo.get_messages(notebook["id"])[0]["content"] == "Question?"


def test_in_memory_repository_replaces_and_lists_chunks():
    repo = InMemoryRepository()
    notebook = repo.create_notebook("Notebook")
    source = repo.create_source(notebook["id"], "https://a.example", "A", status="ready")

    stored = repo.replace_source_chunks(
        source["id"],
        notebook["id"],
        [
            {
                "chunk_index": 0,
                "content": "alpha",
                "char_start": 0,
                "char_end": 5,
                "embedding": [1.0, 0.0],
            },
            {
                "chunk_index": 1,
                "content": "beta",
                "char_start": 6,
                "char_end": 10,
                "embedding": [0.0, 1.0],
            },
        ],
    )

    assert [chunk["chunk_index"] for chunk in stored] == [0, 1]
    assert [chunk["content"] for chunk in repo.get_source_chunks(source["id"])] == ["alpha", "beta"]
    assert len(repo.get_notebook_chunks(notebook["id"])) == 2

    replaced = repo.replace_source_chunks(
        source["id"],
        notebook["id"],
        [
            {
                "chunk_index": 0,
                "content": "gamma",
                "char_start": 0,
                "char_end": 5,
                "embedding": [0.5, 0.5],
            }
        ],
    )
    assert [chunk["content"] for chunk in replaced] == ["gamma"]
    assert [chunk["content"] for chunk in repo.get_source_chunks(source["id"])] == ["gamma"]


def test_in_memory_repository_chunk_replacement_is_source_scoped():
    repo = InMemoryRepository()
    notebook = repo.create_notebook("Notebook")
    source_a = repo.create_source(notebook["id"], "https://a.example", "A", status="ready")
    source_b = repo.create_source(notebook["id"], "https://b.example", "B", status="ready")

    repo.replace_source_chunks(
        source_a["id"],
        notebook["id"],
        [
            {
                "chunk_index": 0,
                "content": "alpha",
                "char_start": 0,
                "char_end": 5,
                "embedding": [1.0, 0.0],
            }
        ],
    )
    repo.replace_source_chunks(
        source_b["id"],
        notebook["id"],
        [
            {
                "chunk_index": 0,
                "content": "beta",
                "char_start": 0,
                "char_end": 4,
                "embedding": [0.0, 1.0],
            }
        ],
    )

    repo.replace_source_chunks(
        source_a["id"],
        notebook["id"],
        [
            {
                "chunk_index": 0,
                "content": "gamma",
                "char_start": 0,
                "char_end": 5,
                "embedding": [0.5, 0.5],
            }
        ],
    )

    assert [chunk["content"] for chunk in repo.get_source_chunks(source_a["id"])] == ["gamma"]
    assert [chunk["content"] for chunk in repo.get_source_chunks(source_b["id"])] == ["beta"]
    # Verify both sources' chunks are present regardless of internal storage order
    assert {chunk["source_id"] for chunk in repo.get_notebook_chunks(notebook["id"])} == {
        source_a["id"],
        source_b["id"],
    }
