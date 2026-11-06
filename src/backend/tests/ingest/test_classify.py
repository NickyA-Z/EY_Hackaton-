import json
import shutil
from types import SimpleNamespace

import anthropic
import pytest

from backend.ingest import classify
from backend.ingest.registry import CATEGORIES


def copy_as(fixtures, tmp_path, fixture, name):
    dest = tmp_path / name
    shutil.copy(fixtures / fixture, dest)
    return dest


class NeverCalled:
    """A client that fails the test if the LLM is asked."""
    @property
    def beta(self):
        raise AssertionError("LLM must not be called when a rule is confident")


class FakeClient:
    def __init__(self, text="", stop_reason="end_turn", raises=None):
        self.calls = []
        self._text, self._stop, self._raises = text, stop_reason, raises
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises:
            raise self._raises
        return SimpleNamespace(stop_reason=self._stop,
                               content=[SimpleNamespace(type="text", text=self._text)])


def answer(**kw):
    base = {"category": "gps_track", "confidence": 0.8, "reason": "lat/lon columns",
            "source_id": None, "period": None}
    return json.dumps({**base, **kw})


# --- rule stage ---------------------------------------------------------------------

@pytest.mark.parametrize("fixture, name, category, source_id, period", [
    ("metar_LGB.csv", "LGB_202606.csv", "metar", "LGB", "202606"),
    ("metar_LGB.csv", "airport_export.csv", "metar", "LGB", "202606"),   # period from content
    ("coops_9410670_wind_202106.csv", "9410670_wind_202106.csv", "coops", "9410670", "202106"),
    ("coops_9410670_air_temperature_202106.csv", "pierF_9410670_202106.csv", "coops", "9410670", "202106"),
    ("coops_9410660_predictions_202606.csv", "9410660_predictions_202606.csv", "coops_tides", "9410660", "202606"),
    ("ndbc_46025_2025.txt.gz", "46025h2025.txt.gz", "ndbc", "46025", "2025"),
    ("open_meteo_racecourse_belmont_202606.json", "racecourse_belmont_202606.json", "open_meteo",
     "racecourse_belmont", "202606"),
    ("sailsync_track.csv", "race_track.csv", "gps_track", None, None),
])
def test_rules_recognise_real_formats(fixtures, tmp_path, fixture, name, category, source_id, period):
    p = classify.classify(copy_as(fixtures, tmp_path, fixture, name), client=NeverCalled())
    assert (p.method, p.category, p.source_id, p.period) == ("rule", category, source_id, period)
    assert p.confidence >= classify.RULE_THRESHOLD


def test_coops_product_from_header(fixtures, tmp_path):
    p = classify.classify(copy_as(fixtures, tmp_path, "coops_9410670_air_temperature_202106.csv", "x_9410670.csv"),
                          use_llm=False)
    assert p.extra["product"] == "air_temperature"


def test_binary_file_has_no_sample(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x00\x01\x02" * 100)
    assert classify.read_head(p) is None


# --- LLM stage ------------------------------------------------------------------------

def test_unknown_text_goes_to_llm_with_constrained_schema(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("Day 3 debrief: left side paid in the afternoon breeze.\n")
    client = FakeClient(answer(category="coach_notes", confidence=0.9, reason="debrief text"))
    p = classify.classify(f, client=client)
    assert (p.method, p.category, p.confidence) == ("llm", "coach_notes", 0.9)

    kw = client.calls[0]
    assert kw["model"] == classify.LLM_MODEL
    schema = kw["output_config"]["format"]["schema"]
    assert set(schema["properties"]["category"]["enum"]) == set(CATEGORIES)
    assert "<file_sample>" in kw["messages"][0]["content"]
    assert "untrusted" in kw["system"]


def test_llm_answer_is_sanitised(tmp_path):
    client = FakeClient(answer(source_id="../../etc/passwd", period="June 2026", confidence=7))
    p = classify.llm_classify("x.csv", 10, "a,b\n1,2", client=client)
    assert p.source_id == "etcpasswd"      # path characters stripped
    assert p.period is None                # not YYYYMM -> dropped, user must fill in
    assert p.confidence == 1.0             # clamped


@pytest.mark.parametrize("client, note_part", [
    (FakeClient(answer(category="exfiltrate")), "unknown category"),
    (FakeClient("not json"), "invalid JSON"),
    (FakeClient(answer(), stop_reason="refusal"), "declined"),
    (FakeClient(answer(), stop_reason="max_tokens"), "cut off"),
    (FakeClient(raises=anthropic.AnthropicError("no credentials")), "not available"),
])
def test_llm_failures_become_unknown(client, note_part):
    p = classify.llm_classify("x.csv", 10, "a,b", client=client)
    assert p.category == "unknown" and note_part in p.note


def test_llm_failure_keeps_weak_rule_guess(tmp_path):
    f = tmp_path / "obs.txt"
    f.write_text("KLGB 010053Z 30009KT 10SM CLR 24/12 A2985\n")    # METAR text, but no CSV header
    p = classify.classify(f, client=FakeClient(raises=anthropic.AnthropicError("offline")))
    assert (p.category, p.method) == ("metar", "rule") and p.confidence < classify.RULE_THRESHOLD
    assert "offline" in p.note
