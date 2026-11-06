"""Incremental sync, search, and prompt building - with a fake embedder, so no API calls."""

from __future__ import annotations

import hashlib
import shutil

import pytest

from backend.rag.config import load_settings
from backend.rag.corpus import indexable_chunks, load_documents
from backend.rag.generate import build_brief_prompt
from backend.rag.store import Store
from backend.rag.triggers import Conditions, select_documents

DIM = 32


class FakeEmbedder:
    """Deterministic hash-based vectors; counts how many texts it was asked to embed."""

    def __init__(self) -> None:
        self.texts_embedded = 0
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        self.texts_embedded += len(texts)
        out = []
        for t in texts:
            digest = hashlib.sha256(t.encode()).digest()
            out.append([(b - 127.5) / 127.5 for b in digest[:DIM]])
        return out


@pytest.fixture
def corpus_copy(tmp_path):
    dest = tmp_path / "corpus"
    shutil.copytree(load_settings().corpus_dir, dest)
    return dest


def test_second_sync_makes_no_embedding_calls(tmp_path, corpus_copy):
    embed = FakeEmbedder()
    store = Store(tmp_path / "db", "fake-model", embed)
    chunks = indexable_chunks(load_documents(corpus_copy))

    first = store.sync(chunks)
    assert first.embedded == len(chunks) and first.skipped == 0
    assert embed.calls == 1  # one batched request, not one per chunk

    calls_before = embed.calls
    second = store.sync(chunks)
    assert (second.embedded, second.skipped, second.deleted) == (0, len(chunks), 0)
    assert embed.calls == calls_before  # zero API calls when nothing changed


def test_edit_reembeds_only_the_changed_chunk(tmp_path, corpus_copy):
    embed = FakeEmbedder()
    store = Store(tmp_path / "db", "fake-model", embed)
    store.sync(indexable_chunks(load_documents(corpus_copy)))

    path = corpus_copy / "TS-03_strong_wind.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Conservative start", "Very conservative start"), encoding="utf-8"
    )
    stats = store.sync(indexable_chunks(load_documents(corpus_copy)))
    assert (stats.embedded, stats.deleted) == (1, 0)


def test_deleted_document_is_removed_from_index(tmp_path, corpus_copy):
    store = Store(tmp_path / "db", "fake-model", FakeEmbedder())
    chunks = indexable_chunks(load_documents(corpus_copy))
    store.sync(chunks)
    (corpus_copy / "TS-09_waves_swell.md").unlink()
    remaining = indexable_chunks(load_documents(corpus_copy))
    stats = store.sync(remaining)
    assert stats.deleted == len(chunks) - len(remaining) > 0
    assert store.count() == len(remaining)


def test_failed_embedding_leaves_index_untouched(tmp_path, corpus_copy):
    store = Store(tmp_path / "db", "fake-model", FakeEmbedder())
    chunks = indexable_chunks(load_documents(corpus_copy))
    store.sync(chunks)

    def boom(_texts):
        raise RuntimeError("api down")

    broken = Store(tmp_path / "db", "fake-model", boom)
    with pytest.raises(RuntimeError):
        broken.sync(chunks, force=True)
    assert store.count() == len(chunks)


def test_model_change_uses_separate_collection(tmp_path, corpus_copy):
    chunks = indexable_chunks(load_documents(corpus_copy))
    Store(tmp_path / "db", "model-a", FakeEmbedder()).sync(chunks)
    other = Store(tmp_path / "db", "model-b", FakeEmbedder())
    assert other.count() == 0
    assert other.sync(chunks).embedded == len(chunks)


def test_search_filters_by_doc_ids_and_fetch_needs_no_embedding(tmp_path, corpus_copy):
    embed = FakeEmbedder()
    store = Store(tmp_path / "db", "fake-model", embed)
    store.sync(indexable_chunks(load_documents(corpus_copy)))
    hits = store.search("anything", k=10, doc_ids=["TS-03", "TS-06"])
    assert hits and {h.doc_id for h in hits} <= {"TS-03", "TS-06"}

    before = embed.calls
    fetched = store.fetch(["TS-03"], ["Coach actions", "Plan B"])
    assert {h.section for h in fetched} == {"Coach actions", "Plan B"}
    assert embed.calls == before
    assert store.fetch([], ["Plan B"]) == []


def test_brief_prompt_caches_stable_prefix_and_sends_only_selected_docs():
    docs = load_documents(load_settings().corpus_dir)
    cond = Conditions(wind_mean_kt=22, gust_kt=27, current_kt=1.0)
    sel = select_documents(cond)
    system, user = build_brief_prompt(docs, cond, sel)

    assert system[0]["cache_control"] == {"type": "ephemeral"}
    prefix = system[0]["text"]
    for stable in ("TS-01", "TS-10", "TS-11"):
        assert f"### {stable} " in prefix
    assert "### TS-03 " in user and "### TS-06 " in user
    assert "### TS-04 " not in user and "### TS-04 " not in prefix  # light-wind doc not sent
    assert "Not provided" in user  # unknown inputs are stated, not assumed
    # same prefix for a different day => cache hit
    other_system, _ = build_brief_prompt(docs, Conditions(wind_mean_kt=6), select_documents(Conditions(wind_mean_kt=6)))
    assert other_system[0]["text"] == prefix


def test_embeddings_base_url_handles_azure_and_the_old_variable_name(monkeypatch):
    from backend.rag.store import embeddings_base_url

    for name in ("OPENAI_ENDPOINT", "ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    assert embeddings_base_url() is None  # api.openai.com
    monkeypatch.setenv("OPENAI_ENDPOINT", "https://lab.services.ai.azure.com/")
    assert embeddings_base_url() == "https://lab.services.ai.azure.com/openai/v1/"
    monkeypatch.setenv("OPENAI_ENDPOINT", "https://lab.openai.azure.com/openai/v1/")
    assert embeddings_base_url() == "https://lab.openai.azure.com/openai/v1"  # already has the path: left alone
    monkeypatch.delenv("OPENAI_ENDPOINT")
    monkeypatch.setenv("ENDPOINT", "http://localhost:8000/v1")
    assert embeddings_base_url() == "http://localhost:8000/v1"
