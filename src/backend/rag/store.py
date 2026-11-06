"""ChromaDB vector store with OpenAI embeddings.

Efficiency choices (each one removes work, none trades away correctness):
* Content-hash incremental sync: a chunk is re-embedded only if its text or the embedding model changed;
  a second ``index`` run makes zero API calls.
* One batched embeddings request per 256 chunks, not one per chunk.
* Vectors are passed to Chroma explicitly, so Chroma's bundled default embedder (an ONNX model download)
  is never loaded.
* One collection per embedding model: switching models cannot hit a dimension mismatch.
* Embeddings are computed before any write, so a failed API call leaves the existing index untouched.
* Query embeddings are cached in-process (a Streamlit session repeating a question pays once).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI

from backend.rag.corpus import Chunk

EMBED_BATCH = 256
QUERY_CACHE_MAX = 256

Embedder = Callable[[Sequence[str]], list[list[float]]]


class OpenAIEmbedder:
    """Batched OpenAI embeddings; ``tokens`` accumulates billed input tokens."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.tokens = 0
        # Reads OPENAI_API_KEY from the environment. ENDPOINT (if set in .env) is an OpenAI-compatible base URL.
        self._client = OpenAI(timeout=60.0, base_url=os.environ.get("ENDPOINT") or None)

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = list(texts[start : start + EMBED_BATCH])
            response = self._client.embeddings.create(model=self.model, input=batch)
            self.tokens += response.usage.total_tokens
            vectors.extend(d.embedding for d in sorted(response.data, key=lambda d: d.index))
        return vectors


@dataclass(frozen=True)
class SyncStats:
    total: int
    embedded: int
    skipped: int
    deleted: int


@dataclass(frozen=True)
class Hit:
    id: str
    doc_id: str
    title: str
    section: str
    body: str
    safety_critical: bool
    distance: float | None  # cosine distance (0 = identical); None for non-vector fetches


def _collection_name(model: str) -> str:
    return "sailing-" + re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-._")


def _to_hit(id_: str, meta: dict, body: str, distance: float | None) -> Hit:
    return Hit(
        id=id_,
        doc_id=meta["doc_id"],
        title=meta["title"],
        section=meta["section"],
        body=body,
        safety_critical=bool(meta["safety_critical"]),
        distance=distance,
    )


class Store:
    def __init__(self, chroma_dir: Path, model: str, embed: Embedder) -> None:
        self.model = model
        self._embed = embed
        self._query_cache: dict[str, list[float]] = {}
        client = chromadb.PersistentClient(path=str(chroma_dir), settings=ChromaSettings(anonymized_telemetry=False))
        self._col = client.get_or_create_collection(
            name=_collection_name(model),
            configuration={"hnsw": {"space": "cosine"}},
            embedding_function=None,  # we always supply vectors ourselves
        )

    def count(self) -> int:
        return self._col.count()

    def sync(self, chunks: list[Chunk], *, force: bool = False) -> SyncStats:
        wanted = {c.id: c for c in chunks}
        existing = self._col.get(include=["metadatas"])
        have = dict(zip(existing["ids"], (m["hash"] for m in existing["metadatas"]), strict=True))

        todo = [c for c in chunks if force or have.get(c.id) != c.content_hash(self.model)]
        stale = [i for i in have if i not in wanted]

        if todo:
            vectors = self._embed([c.embed_text for c in todo])  # may raise: nothing has been written yet
            self._col.upsert(
                ids=[c.id for c in todo],
                embeddings=vectors,
                documents=[c.body for c in todo],
                metadatas=[
                    {
                        "doc_id": c.doc_id,
                        "title": c.title,
                        "doc_type": c.doc_type,
                        "condition": c.condition,
                        "section": c.section,
                        "safety_critical": c.safety_critical,
                        "hash": c.content_hash(self.model),
                    }
                    for c in todo
                ],
            )
        if stale:
            self._col.delete(ids=stale)
        return SyncStats(total=len(chunks), embedded=len(todo), skipped=len(chunks) - len(todo), deleted=len(stale))

    def _embed_query(self, text: str) -> list[float]:
        if text not in self._query_cache:
            if len(self._query_cache) >= QUERY_CACHE_MAX:
                self._query_cache.pop(next(iter(self._query_cache)))
            self._query_cache[text] = self._embed([text])[0]
        return self._query_cache[text]

    def search(self, query: str, k: int = 6, doc_ids: Sequence[str] | None = None) -> list[Hit]:
        total = self._col.count()
        if total == 0:
            raise RuntimeError("the vector index is empty - run the 'index' command first")
        result = self._col.query(
            query_embeddings=[self._embed_query(query)],
            n_results=min(k, total),
            where={"doc_id": {"$in": list(doc_ids)}} if doc_ids else None,
            include=["documents", "metadatas", "distances"],
        )
        return [
            _to_hit(i, m, d, dist)
            for i, m, d, dist in zip(
                result["ids"][0], result["metadatas"][0], result["documents"][0], result["distances"][0], strict=True
            )
        ]

    def fetch(self, doc_ids: Sequence[str], sections: Sequence[str]) -> list[Hit]:
        """Exact metadata lookup (no embedding call, no cost)."""
        if not doc_ids or not sections:
            return []
        result = self._col.get(
            where={"$and": [{"doc_id": {"$in": list(doc_ids)}}, {"section": {"$in": list(sections)}}]},
            include=["documents", "metadatas"],
        )
        return [
            _to_hit(i, m, d, None)
            for i, m, d in zip(result["ids"], result["metadatas"], result["documents"], strict=True)
        ]
