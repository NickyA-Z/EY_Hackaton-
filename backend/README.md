# backend

Logic behind the Location Agent views in `frontend/` (no Streamlit code here).

| Module | Job | Data |
| --- | --- | --- |
| `strategy.py` | Venue statistics, coach/sailor brief, Challenger findings, live check | `src/conditions_June_2026/data/raw` (Open-Meteo wind, NOAA tides) |
| `race_analysis.py` | Which side the winners took on beat 1 | `sailsync_api_results/` (ILCA 7, 19 Jul 2026) |
| `analysis/` | Read and tag coach uploads (see below) | uploads + `analysis/demo/` samples |

## analysis/ — coach-file capabilities

| Capability | Module | Reads | Needs |
| --- | --- | --- | --- |
| 1. Text reading | `text_reader.py` | TXT, MD, CSV, JSON, DOCX, PDF | Nothing for TXT/MD/DOCX. PDF: `pip install pypdf` |
| 2. Picture of text | `image_text.py` | JPG, PNG, WEBP, GIF (whiteboards, handwriting, scanned pages, course sketches) | Claude vision: `pip install anthropic` + `ANTHROPIC_API_KEY` (or `ant auth login`). Fallback: `brew install tesseract` |
| 3. Transcripts | `transcripts.py` | VTT, SRT, pasted text with `Speaker:` / `[hh:mm]` lines | Nothing |
| 4. Voice memos | `audio_text.py` | M4A, MP3, WAV, AAC, OGG, FLAC, WEBM, CAF, or a recording made in the upload dialog | `av` + mlx-whisper (Apple Silicon, `whisper-large-v3-turbo`); fallback faster-whisper (`small`, any CPU). Runs locally; first run downloads the model |
| 5. Live camera water check | `water_view.py` + `water_metrics.py`, snapshot from `retrieval/live_camera.py` | Any camera URL: still image (JPEG/PNG), stream (HLS `.m3u8`, RTSP, MP4), YouTube live (`yt-dlp`), or a web page with a player (stream/poster found in the page); or an uploaded screenshot. Shown on the Live view, with an adjustable water area and camera location | Claude vision (`anthropic` + `ANTHROPIC_API_KEY`) judges the water; OpenCV (`opencv-python-headless`) measures whitecaps/texture and flags night, fog, glare; both are checked against Open-Meteo wind and waves. Without Claude, the OpenCV estimate is shown, labelled uncalibrated |
| Tagging | `tagging.py` | Output of 1–4 | Nothing (keyword rules; swap for an LLM later) |

`analysis/__init__.py` routes each file: name + extension → common-model entity → capability.

## What the coach can upload

| Upload | Formats | Used in | Required |
| --- | --- | --- | --- |
| Notice of Race / Sailing Instructions | PDF, DOCX, TXT or photo | Venue rules | Yes |
| Wind logs (coach boat / own station) | CSV, XLSX | Venue map, Coach brief | No |
| GPS tracks of training or races | GPX, CSV | Strategy overview | No |
| Race results | CSV, XLSX | Strategy overview | No |
| Coach notes & written debriefs | TXT, MD, DOCX, PDF | Coach brief, Strategy overview | No |
| Photos of whiteboards, sketches, handwritten notes | JPG, PNG | Coach brief | No |
| Debrief or meeting transcripts, voice memos | VTT, SRT, TXT, paste, M4A, MP3, WAV or record | Coach brief, Sailor brief | No |

Structured uploads (wind logs, tracks, results) are mapped but not parsed yet.

## Tests

```bash
uv run --python 3.12 --with pandas python -m backend.tests.test_backend   # from the repo root
```
