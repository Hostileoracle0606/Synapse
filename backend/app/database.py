from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
from threading import Lock
from typing import Any
from uuid import uuid4

from app.config import get_settings

try:
    from supabase import Client, create_client
except Exception:  # pragma: no cover - optional dependency
    Client = Any  # type: ignore[assignment]
    create_client = None  # type: ignore[assignment]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stored_embedding_dimension() -> int:
    """Single source of truth — reads from config so it stays in sync with the model."""
    return get_settings().embedding_dimension


def _normalize_embedding(
    embedding: Any,
    *,
    source_id: str | None = None,
    chunk_index: int | None = None,
    expected_dimension: int | None = None,
) -> list[float]:
    if embedding is None:
        location = f"source {source_id}" if source_id else "chunk"
        if chunk_index is not None:
            location += f" chunk {chunk_index}"
        raise ValueError(f"{location} embedding cannot be null")

    if isinstance(embedding, (str, bytes)):
        raise ValueError("chunk embedding must be an iterable of numeric values")

    try:
        values = [float(value) for value in embedding]
    except TypeError as exc:
        raise ValueError("chunk embedding must be an iterable of numeric values") from exc
    except ValueError as exc:
        raise ValueError("chunk embedding contains values that cannot be converted to float") from exc

    if not values:
        raise ValueError("chunk embedding cannot be empty")

    if expected_dimension is not None and len(values) != expected_dimension:
        location = f"source {source_id}" if source_id else "chunk"
        if chunk_index is not None:
            location += f" chunk {chunk_index}"
        raise ValueError(
            f"{location} embedding has dimension {len(values)}; expected {expected_dimension}"
        )

    if not all(math.isfinite(value) for value in values):
        raise ValueError("chunk embedding must contain only finite numeric values")

    return values


def _prepare_chunk_payloads(
    chunks: list[dict[str, Any]],
    *,
    expected_dimension: int | None,
    source_id: str,
) -> list[dict[str, Any]]:
    prepared_chunks: list[dict[str, Any]] = []
    inferred_dimension = expected_dimension

    for chunk in chunks:
        values = _normalize_embedding(
            chunk.get("embedding"),
            source_id=source_id,
            chunk_index=chunk.get("chunk_index"),
            expected_dimension=inferred_dimension,
        )
        if inferred_dimension is None:
            inferred_dimension = len(values)
        prepared_chunks.append({**chunk, "embedding": values})

    return prepared_chunks


class InMemoryRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        self._notebooks: dict[str, dict[str, Any]] = {}
        self._sources: dict[str, dict[str, Any]] = {}
        self._source_chunks: dict[str, dict[str, Any]] = {}
        self._edges: dict[str, dict[str, Any]] = {}
        self._messages: dict[str, dict[str, Any]] = {}

    def create_notebook(self, title: str, seed_url: str | None = None, seed_text: str | None = None) -> dict[str, Any]:
        notebook_id = str(uuid4())
        notebook = {
            "id": notebook_id,
            "title": title,
            "seed_url": seed_url,
            "seed_text": seed_text,
            "status": "discovering",
            "created_at": _utc_now(),
        }
        with self._lock:
            self._notebooks[notebook_id] = notebook
        return deepcopy(notebook)

    def get_notebook(self, notebook_id: str) -> dict[str, Any] | None:
        with self._lock:
            notebook = self._notebooks.get(notebook_id)
        return deepcopy(notebook) if notebook else None

    def update_notebook_status(self, notebook_id: str, status: str) -> None:
        with self._lock:
            if notebook_id in self._notebooks:
                self._notebooks[notebook_id]["status"] = status

    def create_source(
        self,
        notebook_id: str,
        url: str | None,
        title: str,
        source_type: str = "webpage",
        status: str = "pending",
    ) -> dict[str, Any]:
        source_id = str(uuid4())
        source = {
            "id": source_id,
            "notebook_id": notebook_id,
            "url": url,
            "title": title,
            "source_type": source_type,
            "summary": None,
            "content": None,
            "embedding": None,
            "status": status,
            "error_message": None,
            "created_at": _utc_now(),
        }
        with self._lock:
            self._sources[source_id] = source
        return deepcopy(source)

    def update_source(self, source_id: str, **fields: Any) -> dict[str, Any] | None:
        if "embedding" in fields and fields["embedding"] is not None:
            fields = dict(fields)
            fields["embedding"] = _normalize_embedding(
                fields["embedding"],
                source_id=source_id,
                expected_dimension=None,
            )

        with self._lock:
            source = self._sources.get(source_id)
            if not source:
                return None
            source.update(fields)
            updated = deepcopy(source)
        return updated

    def get_sources(self, notebook_id: str) -> list[dict[str, Any]]:
        with self._lock:
            sources = [source for source in self._sources.values() if source["notebook_id"] == notebook_id]
        return sorted((deepcopy(source) for source in sources), key=lambda item: item["created_at"])

    def replace_source_chunks(
        self,
        source_id: str,
        notebook_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prepared_chunks = _prepare_chunk_payloads(
            chunks,
            expected_dimension=None,
            source_id=source_id,
        )

        with self._lock:
            chunk_ids = [chunk_id for chunk_id, chunk in self._source_chunks.items() if chunk["source_id"] == source_id]
            for chunk_id in chunk_ids:
                del self._source_chunks[chunk_id]

            stored_chunks: list[dict[str, Any]] = []
            for chunk in prepared_chunks:
                chunk_id = str(uuid4())
                record = {
                    "id": chunk_id,
                    "source_id": source_id,
                    "notebook_id": notebook_id,
                    "chunk_index": chunk["chunk_index"],
                    "content": chunk["content"],
                    "char_start": chunk["char_start"],
                    "char_end": chunk["char_end"],
                    "embedding": chunk["embedding"],
                    "created_at": _utc_now(),
                }
                self._source_chunks[chunk_id] = record
                stored_chunks.append(deepcopy(record))

        stored_chunks.sort(key=lambda item: item["chunk_index"])
        return stored_chunks

    def get_source_chunks(self, source_id: str) -> list[dict[str, Any]]:
        with self._lock:
            chunks = [chunk for chunk in self._source_chunks.values() if chunk["source_id"] == source_id]
        return sorted((deepcopy(chunk) for chunk in chunks), key=lambda item: item["chunk_index"])

    def get_notebook_chunks(self, notebook_id: str) -> list[dict[str, Any]]:
        with self._lock:
            chunks = [chunk for chunk in self._source_chunks.values() if chunk["notebook_id"] == notebook_id]
        return sorted(
            (deepcopy(chunk) for chunk in chunks),
            key=lambda item: (item["source_id"], item["chunk_index"]),
        )

    def hybrid_search_chunks(
        self,
        notebook_id: str,
        query_text: str,
        query_embedding: list[float],
        match_count: int,
    ) -> list[dict[str, Any]]:
        """Vector-only cosine fallback — no FTS available in memory."""
        from app.services.graph import cosine_similarity

        with self._lock:
            chunks = [
                chunk for chunk in self._source_chunks.values()
                if chunk["notebook_id"] == notebook_id
            ]

        scored: list[dict[str, Any]] = []
        for chunk in chunks:
            raw = chunk.get("embedding") or []
            emb = [float(v) for v in raw]
            score = cosine_similarity(query_embedding, emb)
            scored.append({**deepcopy(chunk), "rrf_score": score})

        scored.sort(key=lambda c: c["rrf_score"], reverse=True)
        return scored[:match_count]

    def create_edge(
        self,
        notebook_id: str,
        source_a: str,
        source_b: str,
        similarity: float,
        relationship: str | None = None,
    ) -> dict[str, Any]:
        if not notebook_id:
            raise ValueError("notebook_id must be a non-null non-empty string")
        if not source_a:
            raise ValueError("source_a must be a non-null non-empty string")
        if not source_b:
            raise ValueError("source_b must be a non-null non-empty string")
        if source_a == source_b:
            raise ValueError("Self-edges are not allowed")

        with self._lock:
            for existing in self._edges.values():
                if existing["notebook_id"] != notebook_id:
                    continue
                if {existing["source_a"], existing["source_b"]} == {source_a, source_b}:
                    existing["similarity"] = similarity
                    existing["relationship"] = relationship
                    return deepcopy(existing)

            edge_id = str(uuid4())
            edge = {
                "id": edge_id,
                "notebook_id": notebook_id,
                "source_a": source_a,
                "source_b": source_b,
                "similarity": similarity,
                "relationship": relationship,
            }
            self._edges[edge_id] = edge
        return deepcopy(edge)

    def get_edges(self, notebook_id: str) -> list[dict[str, Any]]:
        with self._lock:
            edges = [edge for edge in self._edges.values() if edge["notebook_id"] == notebook_id]
        return [deepcopy(edge) for edge in edges]

    def get_sources_with_embeddings(self, notebook_id: str) -> list[dict[str, Any]]:
        return [
            source
            for source in self.get_sources(notebook_id)
            if source.get("status") == "ready" and source.get("embedding")
        ]

    def add_message(
        self,
        notebook_id: str,
        role: str,
        content: str,
        sources_cited: list[str] | None = None,
    ) -> dict[str, Any]:
        message_id = str(uuid4())
        message = {
            "id": message_id,
            "notebook_id": notebook_id,
            "role": role,
            "content": content,
            "sources_cited": sources_cited or [],
            "created_at": _utc_now(),
        }
        with self._lock:
            self._messages[message_id] = message
        return deepcopy(message)

    def get_messages(self, notebook_id: str) -> list[dict[str, Any]]:
        with self._lock:
            messages = [message for message in self._messages.values() if message["notebook_id"] == notebook_id]
        return sorted((deepcopy(message) for message in messages), key=lambda item: item["created_at"])


class SupabaseRepository:
    def __init__(self, client: Client) -> None:
        self._client = client

    def create_notebook(self, title: str, seed_url: str | None = None, seed_text: str | None = None) -> dict[str, Any]:
        result = (
            self._client.table("notebooks")
            .insert({"title": title, "seed_url": seed_url, "seed_text": seed_text, "status": "discovering"})
            .execute()
        )
        return result.data[0]

    def get_notebook(self, notebook_id: str) -> dict[str, Any] | None:
        result = self._client.table("notebooks").select("*").eq("id", notebook_id).limit(1).execute()
        return result.data[0] if result.data else None

    def update_notebook_status(self, notebook_id: str, status: str) -> None:
        self._client.table("notebooks").update({"status": status}).eq("id", notebook_id).execute()

    def create_source(
        self,
        notebook_id: str,
        url: str | None,
        title: str,
        source_type: str = "webpage",
        status: str = "pending",
    ) -> dict[str, Any]:
        result = (
            self._client.table("sources")
            .insert(
                {
                    "notebook_id": notebook_id,
                    "url": url,
                    "title": title,
                    "source_type": source_type,
                    "status": status,
                }
            )
            .execute()
        )
        return result.data[0]

    def update_source(self, source_id: str, **fields: Any) -> dict[str, Any] | None:
        if "embedding" in fields and fields["embedding"] is not None:
            fields = dict(fields)
            fields["embedding"] = _normalize_embedding(
                fields["embedding"],
                source_id=source_id,
                expected_dimension=_stored_embedding_dimension(),
            )

        result = self._client.table("sources").update(fields).eq("id", source_id).execute()
        return result.data[0] if result.data else None

    def get_sources(self, notebook_id: str) -> list[dict[str, Any]]:
        result = self._client.table("sources").select("*").eq("notebook_id", notebook_id).order("created_at").execute()
        return result.data

    def replace_source_chunks(
        self,
        source_id: str,
        notebook_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prepared_chunks = _prepare_chunk_payloads(
            chunks,
            expected_dimension=_stored_embedding_dimension(),
            source_id=source_id,
        )

        if not prepared_chunks:
            self._client.table("source_chunks").delete().eq("source_id", source_id).execute()
            return []

        self._client.table("source_chunks").delete().eq("source_id", source_id).execute()
        payload = [
            {
                "source_id": source_id,
                "notebook_id": notebook_id,
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "char_start": chunk["char_start"],
                "char_end": chunk["char_end"],
                "embedding": chunk["embedding"],
            }
            for chunk in prepared_chunks
        ]
        result = self._client.table("source_chunks").insert(payload).execute()
        return sorted(result.data, key=lambda item: item["chunk_index"])

    def get_source_chunks(self, source_id: str) -> list[dict[str, Any]]:
        result = self._client.table("source_chunks").select("*").eq("source_id", source_id).order("chunk_index").execute()
        return result.data

    def get_notebook_chunks(self, notebook_id: str) -> list[dict[str, Any]]:
        result = (
            self._client.table("source_chunks")
            .select("*")
            .eq("notebook_id", notebook_id)
            .order("source_id")
            .order("chunk_index")
            .execute()
        )
        return result.data

    def hybrid_search_chunks(
        self,
        notebook_id: str,
        query_text: str,
        query_embedding: list[float],
        match_count: int,
    ) -> list[dict[str, Any]]:
        result = self._client.rpc(
            "hybrid_search_chunks",
            {
                "p_notebook_id": notebook_id,
                "p_query_text": query_text,
                "p_query_embedding": query_embedding,
                "p_match_count": match_count,
            },
        ).execute()
        return result.data

    def create_edge(
        self,
        notebook_id: str,
        source_a: str,
        source_b: str,
        similarity: float,
        relationship: str | None = None,
    ) -> dict[str, Any]:
        if not notebook_id:
            raise ValueError("notebook_id must be a non-null non-empty string")
        if not source_a:
            raise ValueError("source_a must be a non-null non-empty string")
        if not source_b:
            raise ValueError("source_b must be a non-null non-empty string")
        if source_a == source_b:
            raise ValueError("Self-edges are not allowed")

        result = (
            self._client.table("edges")
            .insert(
                {
                    "notebook_id": notebook_id,
                    "source_a": source_a,
                    "source_b": source_b,
                    "similarity": similarity,
                    "relationship": relationship,
                }
            )
            .execute()
        )
        return result.data[0]

    def get_edges(self, notebook_id: str) -> list[dict[str, Any]]:
        result = self._client.table("edges").select("*").eq("notebook_id", notebook_id).execute()
        return result.data

    def get_sources_with_embeddings(self, notebook_id: str) -> list[dict[str, Any]]:
        result = (
            self._client.table("sources")
            .select("*")
            .eq("notebook_id", notebook_id)
            .eq("status", "ready")
            .not_.is_("embedding", "null")
            .execute()
        )
        return result.data

    def add_message(
        self,
        notebook_id: str,
        role: str,
        content: str,
        sources_cited: list[str] | None = None,
    ) -> dict[str, Any]:
        result = (
            self._client.table("messages")
            .insert(
                {
                    "notebook_id": notebook_id,
                    "role": role,
                    "content": content,
                    "sources_cited": sources_cited or [],
                }
            )
            .execute()
        )
        return result.data[0]

    def get_messages(self, notebook_id: str) -> list[dict[str, Any]]:
        result = self._client.table("messages").select("*").eq("notebook_id", notebook_id).order("created_at").execute()
        return result.data


_repository: InMemoryRepository | SupabaseRepository | None = None


def get_repository() -> InMemoryRepository | SupabaseRepository:
    global _repository
    if _repository is not None:
        return _repository

    settings = get_settings()
    if settings.has_supabase and create_client is not None:
        _repository = SupabaseRepository(create_client(settings.supabase_url, settings.supabase_key))
    else:
        _repository = InMemoryRepository()
    return _repository


async def create_notebook(title: str, seed_url: str | None = None, seed_text: str | None = None) -> dict[str, Any]:
    return get_repository().create_notebook(title=title, seed_url=seed_url, seed_text=seed_text)


async def get_notebook(notebook_id: str) -> dict[str, Any] | None:
    return get_repository().get_notebook(notebook_id)


async def update_notebook_status(notebook_id: str, status: str) -> None:
    get_repository().update_notebook_status(notebook_id, status)


async def create_source(
    notebook_id: str,
    url: str | None,
    title: str,
    source_type: str = "webpage",
    status: str = "pending",
) -> dict[str, Any]:
    return get_repository().create_source(
        notebook_id=notebook_id,
        url=url,
        title=title,
        source_type=source_type,
        status=status,
    )


async def update_source(source_id: str, **fields: Any) -> dict[str, Any] | None:
    return get_repository().update_source(source_id, **fields)


async def get_sources(notebook_id: str) -> list[dict[str, Any]]:
    return get_repository().get_sources(notebook_id)


async def replace_source_chunks(
    source_id: str,
    notebook_id: str,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return get_repository().replace_source_chunks(source_id, notebook_id, chunks)


async def get_source_chunks(source_id: str) -> list[dict[str, Any]]:
    return get_repository().get_source_chunks(source_id)


async def get_notebook_chunks(notebook_id: str) -> list[dict[str, Any]]:
    return get_repository().get_notebook_chunks(notebook_id)


async def hybrid_search_chunks(
    notebook_id: str,
    query_text: str,
    query_embedding: list[float],
    match_count: int,
) -> list[dict[str, Any]]:
    return get_repository().hybrid_search_chunks(notebook_id, query_text, query_embedding, match_count)


async def create_edge(
    notebook_id: str,
    source_a: str,
    source_b: str,
    similarity: float,
    relationship: str | None = None,
) -> dict[str, Any]:
    return get_repository().create_edge(
        notebook_id=notebook_id,
        source_a=source_a,
        source_b=source_b,
        similarity=similarity,
        relationship=relationship,
    )


async def get_edges(notebook_id: str) -> list[dict[str, Any]]:
    return get_repository().get_edges(notebook_id)


async def get_sources_with_embeddings(notebook_id: str) -> list[dict[str, Any]]:
    return get_repository().get_sources_with_embeddings(notebook_id)


async def add_message(
    notebook_id: str,
    role: str,
    content: str,
    sources_cited: list[str] | None = None,
) -> dict[str, Any]:
    return get_repository().add_message(notebook_id, role, content, sources_cited)


async def get_messages(notebook_id: str) -> list[dict[str, Any]]:
    return get_repository().get_messages(notebook_id)
