"""Capability 3: insert transcripts (debriefs, meetings, voice notes already transcribed).

Accepts WebVTT (.vtt), SubRip (.srt) and plain text with optional
"[hh:mm:ss] Speaker: text" or "Speaker: text" lines. Audio files are not
transcribed here; run them through a speech-to-text tool first.
"""

import re

SUPPORTED = {".vtt", ".srt"}
_CUE_TIME = re.compile(r"^(\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}\s*-->")
_STAMP = re.compile(r"^\[?((?:\d{1,2}:)?\d{1,2}:\d{2})\]?\s*")
_SPEAKER = re.compile(r"^([A-Z][\w .'-]{0,30}):\s+(.*)")
_VTT_VOICE = re.compile(r"^<v\s+([^>]+)>(.*?)(</v>)?$")


def parse_transcript(text):
    """Return {"text", "segments": [{"time", "speaker", "text"}], "method", "error"}."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    method = "vtt" if lines and lines[0].upper().startswith("WEBVTT") else (
        "srt" if any(_CUE_TIME.match(line) and "," in line.split("-->")[0] for line in lines) else "plain")
    segments = []
    time = None
    for line in lines:
        if not line or line.upper().startswith(("WEBVTT", "NOTE")) or line.isdigit():
            continue
        if _CUE_TIME.match(line):
            time = line.split("-->")[0].strip().replace(",", ".").split(".")[0]
            continue
        stamp = _STAMP.match(line)
        if stamp and method == "plain":
            time, line = stamp.group(1), line[stamp.end():]
        speaker = None
        voice = _VTT_VOICE.match(line)
        if voice:
            speaker, line = voice.group(1), voice.group(2)
        else:
            named = _SPEAKER.match(line)
            if named:
                speaker, line = named.group(1), named.group(2)
        if segments and speaker is None and segments[-1]["time"] == time:
            segments[-1]["text"] += " " + line  # continuation of the same cue
        else:
            segments.append({"time": time, "speaker": speaker, "text": line})
    if not segments:
        return {"text": "", "segments": [], "method": method, "error": "Transcript is empty"}
    body = "\n".join(f"{s['speaker'] + ': ' if s['speaker'] else ''}{s['text']}" for s in segments)
    return {"text": body, "segments": segments, "method": f"transcript ({method})", "error": None}
