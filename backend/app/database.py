from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
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


class InMemoryRepository:
    """In-process repository for notebooks/sources/edges/messages.

    Used in single-process dev and on Render-style PaaS deploys where we
    don't want to manage a separate Postgres. State is lost on restart —
    that's intentional given Synapse's "one notebook, one session" UX.
    For persistence, plug in SupabaseRepository via SUPABASE_URL/KEY env.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._notebooks: dict[str, dict[str, Any]] = {}
        self._sources: dict[str, dict[str, Any]] = {}
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
            "status": status,
            "error_message": None,
            "created_at": _utc_now(),
        }
        with self._lock:
            self._sources[source_id] = source
        return deepcopy(source)

    def update_source(self, source_id: str, **fields: Any) -> dict[str, Any] | None:
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

    def delete_source(self, source_id: str) -> bool:
        """Remove a source and cascade to any edges that reference it."""
        with self._lock:
            if source_id not in self._sources:
                return False
            del self._sources[source_id]
            edge_ids = [
                edge_id
                for edge_id, edge in self._edges.items()
                if edge["source_a"] == source_id or edge["source_b"] == source_id
            ]
            for edge_id in edge_ids:
                del self._edges[edge_id]
            return True

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
    """Postgres-backed repository via Supabase. Drop-in replacement for
    InMemoryRepository — same surface, persistent storage.

    Activated when SUPABASE_URL + SUPABASE_KEY are set in the environment.
    The schema is defined in ``supabase_schema.sql`` at the repo root.
    """

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
        result = self._client.table("sources").update(fields).eq("id", source_id).execute()
        return result.data[0] if result.data else None

    def get_sources(self, notebook_id: str) -> list[dict[str, Any]]:
        result = self._client.table("sources").select("*").eq("notebook_id", notebook_id).order("created_at").execute()
        return result.data

    def delete_source(self, source_id: str) -> bool:
        """Cascade to edges. Assumes ON DELETE CASCADE on the schema's
        edges → sources foreign keys; falls back to explicit deletes."""
        try:
            self._client.table("edges").delete().or_(
                f"source_a.eq.{source_id},source_b.eq.{source_id}"
            ).execute()
        except Exception:
            pass
        result = self._client.table("sources").delete().eq("id", source_id).execute()
        return bool(result.data)

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


# ── Async wrappers — sole entry point used by the rest of the app ─────────


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


async def delete_source(source_id: str) -> bool:
    return get_repository().delete_source(source_id)


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


async def add_message(
    notebook_id: str,
    role: str,
    content: str,
    sources_cited: list[str] | None = None,
) -> dict[str, Any]:
    return get_repository().add_message(notebook_id, role, content, sources_cited)


async def get_messages(notebook_id: str) -> list[dict[str, Any]]:
    return get_repository().get_messages(notebook_id)
