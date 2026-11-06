"""OpenCV measurements of a harbour camera frame: repeatable numbers next to Claude's judgement.

* Image check: too dark (night), too little contrast (fog, haze), too much white (glare) -> don't trust the frame.
* Whitecaps: share of the water area that is bright and colourless (breaking crests).
* Texture: share of the water area with edges (ripples and waves make edges; glassy water has few).
The water area is a horizontal band of the frame (WATER_BAND, adjustable per camera in the dashboard).
The numbers are uncalibrated for a given camera; they are most useful compared over time from the same camera.
Needs `pip install opencv-python-headless`.
"""

WATER_BAND = (0.55, 1.0)  # (top, bottom) as shares of the frame height; default: the lower 45 %
WIDTH = 960  # measure at a fixed size so numbers from different cameras/resolutions are comparable
DARK = 0.15  # mean brightness below this: night
FLAT = 0.06  # whole-frame contrast (grey std / 255) below this: fog or haze. Calm water still has a horizon.
BLURRED = 5.0  # Laplacian variance below this AND contrast below 2 x FLAT: milky haze (no sharp edge anywhere)
GLARE = 25.0  # whitecap % above this: sun glare or sky in the water area, not whitecaps


def measure(image, band=WATER_BAND):
    """Return {"brightness", "contrast", "sharpness", "whitecap_pct", "texture_pct", "flags", "estimate",
    "overlay", "error"}."""
    try:
        import cv2  # noqa: PLC0415 - optional dependency
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return {"error": "OpenCV: `pip install opencv-python-headless`"}
    frame = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return {"error": "OpenCV could not decode the image"}
    frame = cv2.resize(frame, (WIDTH, round(frame.shape[0] * WIDTH / frame.shape[1])), interpolation=cv2.INTER_AREA)
    top, bottom = (int(frame.shape[0] * edge) for edge in sorted(band))
    if bottom - top < 10:
        return {"error": "The water area is too thin to measure"}
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hue, saturation, value = cv2.split(cv2.cvtColor(frame[top:bottom], cv2.COLOR_BGR2HSV))

    white = ((value > 200) & (saturation < 40)).astype(np.uint8) * 255
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))  # drop single-pixel sparkle
    edges = cv2.Canny(cv2.GaussianBlur(gray[top:bottom], (5, 5), 0), 50, 150)

    result = {
        "brightness": round(float(gray.mean()) / 255, 3),
        "contrast": round(float(gray.std()) / 255, 3),
        "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1),  # info only: calm water is smooth
        "whitecap_pct": round(100 * float(np.count_nonzero(white)) / white.size, 2),
        "texture_pct": round(100 * float(np.count_nonzero(edges)) / edges.size, 2),
        "error": None,
    }
    result["flags"] = [flag for flag, on in (
        ("too dark (night?)", result["brightness"] < DARK),
        ("low contrast (fog or haze?)", result["contrast"] < FLAT
         or (result["sharpness"] < BLURRED and result["contrast"] < 2 * FLAT)),
        ("glare in the water area", result["whitecap_pct"] > GLARE),
    ) if on]
    result["estimate"] = None if result["flags"] else estimate(result["whitecap_pct"], result["texture_pct"])
    result["overlay"] = _overlay(cv2, frame, top, bottom, white)
    return result


def estimate(whitecap_pct, texture_pct):
    """Rough surface class from the numbers alone (uncalibrated; used only when Claude vision is unavailable)."""
    if whitecap_pct >= 8:
        surface, caps = "rough", "many"
    elif whitecap_pct >= 2:
        surface, caps = "choppy", "few"
    else:
        surface, caps = ("glassy" if texture_pct < 2 else "rippled" if texture_pct < 8 else "choppy"), "none"
    return {"surface": surface, "whitecaps": caps}


def _overlay(cv2, frame, top, bottom, white):
    """The measured water area outlined, detected whitecaps painted red: shows the coach what was counted."""
    shown = frame.copy()
    shown[top:bottom][white > 0] = (0, 0, 255)
    cv2.rectangle(shown, (0, top), (shown.shape[1] - 1, bottom - 1), (0, 220, 255), 2)
    cv2.putText(shown, "measured water area", (8, top + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)
    ok, encoded = cv2.imencode(".jpg", shown, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return encoded.tobytes() if ok else None
