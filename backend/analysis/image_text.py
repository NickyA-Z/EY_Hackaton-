"""Capability 2: read text from a picture (whiteboard photo, handwritten notes, scanned page).

Engines, tried in order:
1. Claude vision (needs `pip install anthropic` and ANTHROPIC_API_KEY or `ant auth login`).
2. Tesseract OCR (needs the `tesseract` binary, e.g. `brew install tesseract`).
"""

import base64
import shutil
import subprocess
from pathlib import Path

MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}
SUPPORTED = set(MEDIA_TYPES)
MODEL = "claude-opus-5-5"
PROMPT = ("Transcribe all text in this image exactly as written, keeping line breaks. "
          "If it is a sailing course sketch, also list labelled marks, arrows and notes. "
          "Return only the transcription.")


def read_image_text(name, data):
    """Return {"text", "method", "error"} for one image."""
    media_type = MEDIA_TYPES.get(Path(name).suffix.lower())
    if not media_type:
        return {"text": "", "method": None, "error": "Not a supported image type"}
    errors = []
    try:
        import anthropic  # noqa: F401
    except ImportError:
        errors.append("Claude vision: `pip install anthropic`")
    else:
        result = _claude(data, media_type)
        if not result["error"]:
            return result
        errors.append(result["error"])
    if shutil.which("tesseract"):
        return _tesseract(data)
    errors.append("Tesseract: `brew install tesseract`")
    return {"text": "", "method": None, "error": "No OCR engine available. " + " · ".join(errors)}


def _claude(data, media_type):
    import anthropic

    try:
        response = anthropic.Anthropic().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.standard_b64encode(data).decode("utf-8")}},
                {"type": "text", "text": PROMPT},
            ]}],
        )
    except anthropic.AuthenticationError:
        return {"text": "", "method": "claude", "error": "Claude vision: no API credentials"}
    except anthropic.RateLimitError:
        return {"text": "", "method": "claude", "error": "Claude vision: rate limited, try again"}
    except anthropic.APIStatusError as error:
        return {"text": "", "method": "claude", "error": f"Claude vision: API error {error.status_code}"}
    except anthropic.APIConnectionError:
        return {"text": "", "method": "claude", "error": "Claude vision: no connection"}
    if response.stop_reason == "refusal":
        return {"text": "", "method": "claude", "error": "Claude vision declined this image"}
    text = "".join(block.text for block in response.content if block.type == "text")
    return {"text": text.strip(), "method": "claude vision", "error": None}


def _tesseract(data):
    run = subprocess.run(["tesseract", "stdin", "stdout"], input=data, capture_output=True, timeout=120)
    if run.returncode != 0:
        return {"text": "", "method": "tesseract", "error": run.stderr.decode(errors="replace")[:200]}
    return {"text": run.stdout.decode(errors="replace").strip(), "method": "tesseract", "error": None}
