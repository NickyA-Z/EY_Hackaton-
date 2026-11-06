import json
import shutil

import pytest

from backend.ingest import inbox, run
from backend.ingest.classify import Proposal, classify


@pytest.fixture
def dirs(tmp_path):
    raw, box = tmp_path / "raw", tmp_path / "inbox"
    raw.mkdir()
    return raw, box


def put(fixtures, box, fixture, name):
    return inbox.receive(name, (fixtures / fixture).read_bytes(), box)


def test_receive_sanitises_and_never_overwrites(dirs):
    _, box = dirs
    a = inbox.receive("../../evil name.csv", b"x", box)
    b = inbox.receive("../../evil name.csv", b"y", box)
    assert a.parent == box and a.name == "evil_name.csv"
    assert b.name == "evil_name_1.csv" and a.read_bytes() == b"x"


def test_target_path_and_required_fields(fixtures, dirs):
    raw, box = dirs
    src = put(fixtures, box, "coops_9410670_wind_202106.csv", "upload.csv")
    p = Proposal("coops", 0.95, "rule", "", source_id="9410670", period="202106",
                 extra={"product": "wind"})
    assert inbox.target_path(src, p, raw) == raw / "noaa_coops" / "9410670_wind_202106.csv"
    with pytest.raises(inbox.InboxError, match="period"):
        inbox.target_path(src, Proposal("coops", 1, "rule", "", source_id="9410670"), raw)
    with pytest.raises(inbox.InboxError, match="YYYYMM"):
        inbox.target_path(src, Proposal("coops", 1, "rule", "", source_id="9410670", period="2021-06"), raw)
    with pytest.raises(inbox.InboxError, match="category"):
        inbox.target_path(src, Proposal("unknown", 0, "none", ""), raw)


def test_preview_runs_the_parser(fixtures, dirs):
    _, box = dirs
    src = put(fixtures, box, "ndbc_46025_2025.txt.gz", "46025h2025.txt.gz")
    pv = inbox.preview(src, classify(src, use_llm=False), months=(6,))
    assert (pv.rows, pv.rows_in_months, pv.error, pv.problems) == (4, 2, None, [])


def test_preview_reports_parser_trouble(dirs):
    _, box = dirs
    src = inbox.receive("weird.csv", b"Date Time, Speed\nnot-a-date,abc\n", box)
    pv = inbox.preview(src, Proposal("coops", 0.5, "llm", "", source_id="1234567", period="202606"))
    assert pv.error


def test_confirm_moves_records_and_blocks_duplicates(fixtures, dirs):
    raw, box = dirs
    src = put(fixtures, box, "sailsync_track.csv", "Matt race.csv")
    dest = inbox.confirm(src, classify(src, use_llm=False), raw_dir=raw)
    assert dest == raw / "tracks" / "Matt_race.csv" and not src.exists()
    entry = json.loads((raw / "manifest.json").read_text())["tracks/Matt_race.csv"]
    assert entry["category"] == "gps_track" and entry["classified_by"] == "rule"

    again = put(fixtures, box, "sailsync_track.csv", "copy.csv")
    with pytest.raises(inbox.InboxError, match="identical"):
        inbox.confirm(again, classify(again, use_llm=False), raw_dir=raw)


def test_duplicate_of_file_stored_before_manifest(fixtures, dirs):
    raw, box = dirs
    (raw / "metar").mkdir()
    shutil.copy(fixtures / "metar_LGB.csv", raw / "metar" / "LGB_202606.csv")
    src = put(fixtures, box, "metar_LGB.csv", "again.csv")
    with pytest.raises(inbox.InboxError, match="metar/LGB_202606.csv"):
        inbox.confirm(src, classify(src, use_llm=False), raw_dir=raw)


def test_sample_flag_reaches_observations(fixtures, dirs):
    raw, box = dirs
    src = put(fixtures, box, "metar_LGB.csv", "made_up_example.csv")
    inbox.confirm(src, classify(src, use_llm=False), is_sample=True, raw_dir=raw)
    obs = run.ingest(raw, months=(6,))["observations"]
    assert len(obs) and obs["is_sample"].all()


def test_reject_keeps_file(dirs):
    _, box = dirs
    src = inbox.receive("junk.bin", b"\x00\x01", box)
    moved = inbox.reject(src, box)
    assert moved.exists() and not src.exists() and inbox.pending(box) == []
