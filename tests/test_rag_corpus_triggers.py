"""Corpus parsing and trigger selection, run against the real rag-system/ files (no network)."""

from __future__ import annotations

import pytest

from ey_hackathon.rag.config import load_settings
from ey_hackathon.rag.corpus import indexable_chunks, load_documents
from ey_hackathon.rag.triggers import PRIORITY, RULES, Conditions, select_documents


@pytest.fixture(scope="module")
def docs():
    return load_documents(load_settings().corpus_dir)


def test_corpus_shape(docs):
    assert len(docs) == 12  # 11 strategy documents + the index
    assert docs["TS-03"].safety_critical and docs["TS-05"].safety_critical
    chunks = indexable_chunks(docs)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    assert all(c.body.strip() for c in chunks)
    assert not any(c.doc_id == "TS-00" for c in chunks)  # index document is not searchable


def test_banner_removed_from_chunks_and_text(docs):
    assert not any("SYNTHETIC DATA" in c.embed_text for c in indexable_chunks(docs))
    assert "SYNTHETIC DATA" not in docs["TS-03"].text()


def test_every_document_has_a_rule_and_a_priority(docs):
    strategy_ids = {d for d, doc in docs.items() if doc.doc_type != "index"}
    assert set(RULES) == strategy_ids
    assert {d for d, _ in PRIORITY} == strategy_ids


def test_strong_wind_is_safety_tier_and_first():
    sel = select_documents(Conditions(wind_mean_kt=22, gust_kt=27, current_kt=0.2))
    assert sel.doc_ids[0] == "TS-03"
    assert "TS-02" not in sel.doc_ids
    assert {"TS-01", "TS-10", "TS-11"} <= set(sel.doc_ids)


def test_gust_alone_triggers_strong_wind():
    assert "TS-03" in select_documents(Conditions(wind_mean_kt=12, gust_kt=25)).doc_ids


def test_current_outranks_wind_type_documents():
    ids = select_documents(Conditions(wind_mean_kt=6, current_kt=1.2)).doc_ids
    assert ids.index("TS-06") < ids.index("TS-04")


def test_sea_breeze_day():
    ids = select_documents(
        Conditions(wind_mean_kt=6, cloud_cover_pct=10, land_sea_temp_diff_c=6, gradient_wind_kt=8)
    ).doc_ids
    assert "TS-04" in ids and "TS-07" in ids


def test_no_gap_between_moderate_and_strong():
    for wind in (7.99, 8, 12, 17, 17.5, 17.99, 18):
        ids = select_documents(Conditions(wind_mean_kt=wind)).doc_ids
        assert {"TS-02", "TS-03", "TS-04"} & set(ids), f"no wind-strength document for {wind} kt"


def test_rain_blocks_moderate_and_triggers_squall_doc():
    ids = select_documents(Conditions(wind_mean_kt=12, precipitation_mm_h=2.0)).doc_ids
    assert "TS-05" in ids and "TS-02" not in ids


def test_missing_inputs_are_reported_not_assumed_zero():
    sel = select_documents(Conditions(wind_mean_kt=12))
    assert "current_kt" in sel.missing
    assert "TS-06" not in sel.doc_ids


def test_other_venue_drops_venue_playbook():
    assert "TS-10" not in select_documents(Conditions(venue="somewhere_else", wind_mean_kt=12)).doc_ids


def test_unknown_condition_key_is_rejected():
    with pytest.raises(ValueError, match="unknown condition keys"):
        Conditions.from_dict({"wind_kt": 20})
