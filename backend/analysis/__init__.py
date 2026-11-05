"""Coach-file analysis: route every upload to the right capability.

Capabilities (one module each):
  text_reader  - typed documents: TXT, MD, CSV, JSON, DOCX, PDF
  image_text   - pictures of text: photos of whiteboards, notes, scanned pages
  transcripts  - debrief / meeting transcripts: VTT, SRT, pasted text
Then tagging.py tags the text by topic and pulls out venue rules.
"""

from pathlib import Path

from . import image_text, tagging, text_reader, transcripts

DEMO_DIR = Path(__file__).resolve().parent / "demo"

BADGES = {".csv": "CSV", ".xlsx": "XLSX", ".xls": "XLS", ".gpx": "GPX", ".txt": "TXT", ".md": "TXT",
          ".pdf": "PDF", ".docx": "DOCX", ".vtt": "VTT", ".srt": "SRT", ".jpg": "JPG",
          ".jpeg": "JPG", ".png": "PNG", ".webp": "IMG", ".json": "JSON"}
UPLOAD_TYPES = sorted(suffix.lstrip(".") for suffix in BADGES)

# What the coach can upload, which tab uses it, and how we read it.
COACH_UPLOADS = [
    {"item": "Wind logs (coach boat / own station)", "formats": "CSV, XLSX", "entity": "Wind observations",
     "used_in": "Venue map, Coach brief", "capability": "structured", "required": False},
    {"item": "GPS tracks of training or races", "formats": "GPX, CSV", "entity": "Boat tracks",
     "used_in": "Strategy overview", "capability": "structured", "required": False},
    {"item": "Race results", "formats": "CSV, XLSX", "entity": "Race results",
     "used_in": "Strategy overview", "capability": "structured", "required": False},
    {"item": "Notice of Race / Sailing Instructions", "formats": "PDF, DOCX, TXT or photo",
     "entity": "Venue rules", "used_in": "Venue rules", "capability": "text / image", "required": True},
    {"item": "Coach notes & written debriefs", "formats": "TXT, MD, DOCX, PDF", "entity": "Coach notes",
     "used_in": "Coach brief, Strategy overview", "capability": "text", "required": False},
    {"item": "Photos of whiteboards, sketches, handwritten notes", "formats": "JPG, PNG",
     "entity": "Picture of text", "used_in": "Coach brief", "capability": "image", "required": False},
    {"item": "Debrief or meeting transcripts", "formats": "VTT, SRT, TXT or paste",
     "entity": "Transcript", "used_in": "Coach brief, Sailor brief", "capability": "transcript",
     "required": False},
]

_RULE_NAMES = ("rule", "instruction", "notice", "nor", "_si", "si_", "regulation")


def map_file(name):
    """(badge, common-model entity, capability) from the file name alone."""
    suffix = Path(name).suffix.lower()
    lower = name.lower()
    badge = BADGES.get(suffix, suffix.lstrip(".").upper() or "FILE")
    if suffix in transcripts.SUPPORTED or "transcript" in lower:
        return badge, "Transcript", "transcript"
    if suffix in image_text.SUPPORTED:
        return badge, "Picture of text", "image"
    if any(word in lower for word in _RULE_NAMES) and suffix in text_reader.SUPPORTED:
        return badge, "Venue rules", "text"
    if suffix in (".csv", ".xlsx", ".xls", ".gpx"):
        if "result" in lower:
            return badge, "Race results", "structured"
        if suffix == ".gpx" or "track" in lower or "gps" in lower:
            return badge, "Boat tracks", "structured"
        return badge, "Wind observations", "structured"
    if suffix in text_reader.SUPPORTED:
        return badge, "Coach notes", "text"
    return badge, None, None


def analyse(name, data):
    """Read one upload with the right capability and tag it."""
    badge, entity, capability = map_file(name)
    result = {"name": name, "badge": badge, "entity": entity, "capability": capability,
              "text": "", "method": None, "error": None, "tags": {}}
    if capability == "image":
        result.update(image_text.read_image_text(name, data))
    elif capability == "transcript":
        result.update(transcripts.parse_transcript(data.decode("utf-8", errors="replace")))
    elif capability == "text":
        result.update(text_reader.read_text(name, data))
    elif capability == "structured":
        result["method"] = "mapped (structured data)"
    else:
        result["error"] = "Unknown file type"
    if result["text"]:
        result["tags"] = tagging.tag(result["text"])
    return result


def analyse_pasted_transcript(title, text):
    result = {"name": title, "badge": "TXT", "entity": "Transcript", "capability": "transcript",
              "tags": {}}
    result.update(transcripts.parse_transcript(text))
    if result["text"]:
        result["tags"] = tagging.tag(result["text"])
    return result


def demo_documents():
    """The demo coach file set: sample texts in analysis/demo plus named structured files."""
    docs = [analyse(path.name, path.read_bytes()) for path in sorted(DEMO_DIR.iterdir()) if path.is_file()]
    for name in ("wind_log_coachboat_2025.csv", "training_tracks_week44.gpx", "race_results_2024_2026.xlsx"):
        docs.append(analyse(name, b""))
    return docs


def checklist(documents):
    """COACH_UPLOADS with a 'provided' flag based on what was analysed."""
    have = {doc["entity"] for doc in documents if doc["entity"]}
    return [{**row, "provided": row["entity"] in have} for row in COACH_UPLOADS]
