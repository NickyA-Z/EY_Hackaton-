"""Capability 5: read the water surface from a harbour camera snapshot and cross-check it with the numbers.

Claude vision judges the picture on its own (it is not shown the forecast), then plain code compares
that judgement with the measured wind / wave height. OpenCV (water_metrics.py) adds repeatable image numbers:
an image check (night, fog, glare), whitecap and texture shares, and a rough estimate when Claude is unavailable.
Independent sources agreeing is the evidence we show the coach; disagreement is shown too, never hidden.

Scope (team decision, 2026-11-06): this is a stand-alone, display-only check on the Live view. Its result is
NOT fed into the main analysis (live check, coach/sailor brief, strategy overview, what-if) nor into the RAG
briefing. Keep it that way unless the team decides otherwise.
Needs `pip install anthropic` and ANTHROPIC_API_KEY (or `ant auth login`).
"""

import base64
import io
import json

from . import water_metrics

MODEL = "claude-opus-5-5"
MAX_SIDE = 1568  # longer side; larger images are downscaled by the API anyway, so send less
SURFACES = ["glassy", "rippled", "choppy", "rough"]
WHITECAPS = ["none", "few", "many"]
VERDICTS = ["Calm", "Light chop", "Choppy", "Rough"]

SCHEMA = {
    "type": "object",
    "properties": {
        "water_visible": {"type": "boolean"},
        "unusable_reason": {"type": "string", "description": "Why the water can't be judged; empty if it can."},
        "surface": {"type": "string", "enum": [*SURFACES, "unknown"]},
        "whitecaps": {"type": "string", "enum": [*WHITECAPS, "unknown"]},
        "visibility": {"type": "string", "enum": ["good", "moderate", "poor"]},
        "light": {"type": "string", "enum": ["day", "dusk_or_dawn", "night"]},
        "wind_signs": {"type": "string", "description": "Flags, smoke, cat's paws, wind lanes; empty if none."},
        "notes": {"type": "string", "description": "One or two short sentences for a sailing coach."},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["water_visible", "unusable_reason", "surface", "whitecaps", "visibility", "light", "wind_signs",
                 "notes", "confidence"],
    "additionalProperties": False,
}

PROMPT = """This is a snapshot from a live camera over a harbour where Olympic sailors race.
Judge only what the picture shows about the water surface; do not guess from the place or season.
surface: glassy (mirror-like), rippled (small ripples, no breaking), choppy (short waves, some breaking),
rough (steep waves, much breaking). whitecaps: none, few (scattered), many (widespread).
If fog, darkness, glare, a lens problem or the framing stops you judging the water, set water_visible to false,
say why in unusable_reason, and use "unknown" instead of guessing."""


def assess_snapshot(image, media_type, conditions=None, band=water_metrics.WATER_BAND):
    """Return {"camera", "metrics", "numbers", "verdict", "agreement", "summary", "method", "error"}."""
    try:
        import anthropic  # noqa: PLC0415 - optional dependency
    except ImportError:
        camera, error = None, "Claude vision: `pip install anthropic`"
    else:
        camera, error = _claude(anthropic, *_prepare(image, media_type))
    return combine(camera, error, water_metrics.measure(image, band), conditions)


def combine(camera, error, metrics, conditions):
    """Claude's judgement + OpenCV numbers + forecast -> verdict. Re-run cheaply when only the water band changes."""
    if camera:
        view = {**camera, "label": "Camera"}
    elif metrics.get("estimate"):  # no Claude: fall back to the OpenCV numbers, clearly labelled as rough
        view = {**metrics["estimate"], "water_visible": True, "label": "Camera (OpenCV estimate, uncalibrated)"}
    else:  # say why there is no camera judgement
        reason = ", ".join(metrics.get("flags") or []) or "Claude vision unavailable"
        view = {"water_visible": False, "unusable_reason": reason, "surface": "unknown", "label": "Camera"}
    methods = [name for name, used in (("claude vision", camera), ("opencv", not metrics.get("error"))) if used]
    result = {"camera": camera, "metrics": metrics, "numbers": conditions, "method": " + ".join(methods) or None,
              "error": error}
    result.update(compare(view, conditions, metrics.get("flags")))
    return result


def compare(view, conditions, image_flags=None):
    """Plain rules: what surface would the measured wind produce, and does the camera show that?"""
    usable = bool(view and view["water_visible"] and view["surface"] in SURFACES)
    wind = (conditions or {}).get("wind_kt")
    expected = None if wind is None else 0 if wind < 4 else 1 if wind <= 10 else 2 if wind <= 16 else 3
    label = (view or {}).get("label", "Camera")
    if usable:
        seen = SURFACES.index(view["surface"])
        verdict = VERDICTS[seen]
        caps = "" if view["whitecaps"] == "unknown" else f", whitecaps: {view['whitecaps']}"
        camera_text = f"{label}: {view['surface']} water{caps}."
    else:
        seen, verdict = None, None
        reason = (view or {}).get("unusable_reason") or "no camera judgement"
        camera_text = f"{label}: water can't be judged ({reason})."
    if seen is None and expected is None:
        agreement = "No camera judgement and no wind data."
    elif seen is None:
        verdict = VERDICTS[expected]
        agreement = "Based on the numbers only."
    elif expected is None:
        agreement = "Based on the camera only (no wind data)."
    elif abs(seen - expected) <= 1:
        agreement = "Camera and numbers agree." if seen == expected else "Camera and numbers roughly agree."
    elif seen < expected:
        agreement = ("Camera looks calmer than the wind suggests: the camera may see sheltered water, "
                     "or the wind has dropped. Check on the water.")
    else:
        agreement = ("Camera looks rougher than the wind suggests: a gust, ship wakes or a wind shift may be on "
                     "camera. Check on the water.")
    check = f"Image check: {', '.join(image_flags)}." if image_flags else ""
    parts = (f"{verdict}." if verdict else "", camera_text, _numbers_text(conditions), agreement, check)
    return {"verdict": verdict, "agreement": agreement, "summary": " ".join(part for part in parts if part)}


def _numbers_text(conditions):
    if not conditions:
        return ""
    parts = []
    if conditions.get("wind_kt") is not None:
        gust = conditions.get("gust_kt")
        parts.append(f"wind {conditions['wind_kt']:.0f} kt" + (f" (gusts {gust:.0f})" if gust is not None else ""))
    if conditions.get("wave_height_m") is not None:
        parts.append(f"waves {conditions['wave_height_m']:.1f} m offshore (model)")
    return f"Numbers: {', '.join(parts)}." if parts else ""


def _prepare(image, media_type):
    """Downscale big frames (4K cameras) and send JPEG; small images go through unchanged."""
    try:
        from PIL import Image  # noqa: PLC0415 - Pillow ships with streamlit
    except ImportError:
        return image, media_type
    with Image.open(io.BytesIO(image)) as picture:
        if max(picture.size) <= MAX_SIDE and media_type in ("image/jpeg", "image/png"):
            return image, media_type
        picture.thumbnail((MAX_SIDE, MAX_SIDE))
        buffer = io.BytesIO()
        picture.convert("RGB").save(buffer, format="JPEG", quality=88)
    return buffer.getvalue(), "image/jpeg"


def _claude(anthropic, image, media_type):  # noqa: PLR0911 - one return per API outcome
    try:
        client = anthropic.Anthropic()
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.standard_b64encode(image).decode("utf-8")}},
                {"type": "text", "text": PROMPT},
            ]}],
        )
    except anthropic.AuthenticationError:
        return None, "Claude vision: no API credentials (set ANTHROPIC_API_KEY)"
    except anthropic.RateLimitError:
        return None, "Claude vision: rate limited, try again"
    except anthropic.APIStatusError as error:
        return None, f"Claude vision: API error {error.status_code}"
    except anthropic.APIConnectionError:
        return None, "Claude vision: no connection"
    except anthropic.AnthropicError as error:
        return None, f"Claude vision: {type(error).__name__}: {str(error)[:120]}"
    except TypeError as error:  # the SDK raises TypeError when no API key / auth token / profile is found
        if "authentication" not in str(error):
            raise
        return None, "Claude vision: no API credentials (set ANTHROPIC_API_KEY)"
    if response.stop_reason == "refusal":
        return None, "Claude vision declined this image"
    if response.stop_reason == "max_tokens":
        return None, "Claude vision: answer was cut off, try again"
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        return None, "Claude vision: unreadable answer"
