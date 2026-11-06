"""Live harbour camera snapshot + the measured conditions to check it against.

The user pastes any camera URL; one current frame is taken from it (check the camera's terms first):
* a still image URL (JPEG/PNG);
* an HLS stream (.m3u8): the newest ~2 s segment is downloaded and its first frame decoded with PyAV;
* other video URLs (RTSP, RTMP, MP4) opened directly with PyAV;
* a YouTube live URL: yt-dlp finds the HLS stream (optional dependency);
* an uploaded video file (MP4, MOV, ...): one frame from the middle (frame_from_video);
* a web page with a player: the page and its own scripts are searched for the stream or the poster image
  (works for common players such as datarhei Restreamer / video.js).
"""

import io
import re
from urllib.parse import urljoin, urlparse

import requests

STREAM_SUFFIXES = (".mpd", ".mp4", ".ts")
STREAM_SCHEMES = ("rtsp", "rtmp")
YOUTUBE_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be")
MAX_HEIGHT = 1080
MAX_DECODE = 3000  # frames decoded after a seek before giving up on the exact middle (~100 s at 30 fps)
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 20
HEADERS = {"User-Agent": "LocationAgent/0.1 (hackathon demo)"}
_QUOTED = r"""["']([^"'\s]+?\.{ext}(?:\?[^"'\s]*)?)["']"""
_STREAM_IN_PAGE = re.compile(_QUOTED.format(ext="m3u8"))
_POSTER_IN_PAGE = re.compile(r"""(?:poster|thumbnail_url|snapshot)["']?\s*[:=]\s*["']([^"']+\.(?:jpe?g|png)[^"']*)["']""",
                             re.IGNORECASE)
_SCRIPT_SRC = re.compile(r"""<script[^>]+src=["']([^"']+)["']""", re.IGNORECASE)
_YOUTUBE_EMBED = re.compile(r"""(?:youtube\.com/embed/|youtu\.be/)([\w-]{11})""")


class SnapshotError(Exception):
    """The camera URL did not give us an image."""


def grab_snapshot(url):  # noqa: PLR0911 - one return per kind of camera URL
    """Return (image bytes, media type) for one current frame from a camera URL."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", *STREAM_SCHEMES):
        raise SnapshotError("Enter an http(s), rtsp or rtmp camera URL")
    if (parsed.hostname or "").lower() in YOUTUBE_HOSTS:
        return _from_youtube(url)
    if parsed.scheme in STREAM_SCHEMES or parsed.path.lower().endswith(STREAM_SUFFIXES):
        return _frame_from_stream(url)
    if parsed.path.lower().endswith(".m3u8"):
        return _frame_from_hls(url)
    response = _get(url)
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type.startswith("image/"):
        return response.content, content_type
    if "mpegurl" in content_type:
        return _frame_from_hls(url, response.text)
    if content_type.startswith("video/"):
        return _frame_from_stream(url)
    if "html" in content_type:
        return _from_page(url, response.text)
    raise SnapshotError(f"The URL returned {content_type or 'no content type'}, not an image, stream or web page.")


def _get(url):
    try:
        response = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        response.raise_for_status()
    except requests.RequestException as error:
        raise SnapshotError(f"Camera did not answer ({type(error).__name__})") from None
    return response


def _from_page(url, html):
    """A page with an embedded player: look in the page and its same-site scripts for a stream or poster."""
    embed = _YOUTUBE_EMBED.search(html)
    if embed:
        return _from_youtube(f"https://www.youtube.com/watch?v={embed.group(1)}")
    texts = [(url, html)]
    host = urlparse(url).hostname
    for src in _SCRIPT_SRC.findall(html)[:15]:
        script_url = urljoin(url, src)
        if urlparse(script_url).hostname == host and "/dist/" not in script_url:  # skip player libraries
            try:
                texts.append((script_url, requests.get(script_url, timeout=TIMEOUT, headers=HEADERS).text))
            except requests.RequestException:
                continue
    streams = [urljoin(url, m) for _base, text in texts for m in _STREAM_IN_PAGE.findall(text)]
    posters = [urljoin(url, m) for _base, text in texts for m in _POSTER_IN_PAGE.findall(text)]
    errors = []
    for candidate in streams:  # a live frame is fresher than a poster image
        try:
            return _frame_from_hls(candidate)
        except SnapshotError as error:
            errors.append(str(error))
    for candidate in posters:
        response = _get(candidate)
        if response.headers.get("Content-Type", "").startswith("image/"):
            return response.content, response.headers["Content-Type"].split(";")[0]
    detail = f" ({errors[0]})" if errors else ""
    raise SnapshotError("No video stream or camera image found in this page" + detail +
                        ". Use the player's direct stream (.m3u8) or image URL.")


def _from_youtube(url):
    try:
        import yt_dlp  # noqa: PLC0415 - optional dependency, only for YouTube URLs
    except ImportError:
        raise SnapshotError("YouTube URLs need yt-dlp: `pip install yt-dlp`") from None
    options = {"quiet": True, "no_warnings": True, "skip_download": True,
               "format": f"bv*[height<={MAX_HEIGHT}]/b[height<={MAX_HEIGHT}]/bv*/b"}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as error:
        raise SnapshotError(f"YouTube: {str(error).replace('ERROR: ', '')[:160]}") from None
    stream = info.get("url")
    if not stream:
        raise SnapshotError("YouTube did not give a video stream for this URL")
    return _frame_from_hls(stream) if "m3u8" in (info.get("protocol") or "") else _frame_from_stream(stream)


def _frame_from_hls(url, playlist=None):
    """Live HLS: pick a variant up to MAX_HEIGHT, download only the newest segment, decode its first frame."""
    playlist = playlist if playlist is not None else _get(url).text
    if "#EXT-X-STREAM-INF" in playlist:
        url = urljoin(url, _pick_variant(playlist))
        playlist = _get(url).text
    if "#EXT-X-KEY:METHOD=AES" in playlist or "#EXT-X-KEY:METHOD=SAMPLE" in playlist:
        raise SnapshotError("The stream is encrypted")
    segments = [line.strip() for line in playlist.splitlines() if line.strip() and not line.startswith("#")]
    if not segments:
        raise SnapshotError("The stream playlist has no video segments")
    init = re.search(r'#EXT-X-MAP:URI="([^"]+)"', playlist)  # fragmented MP4 streams need their init segment
    data = (_get(urljoin(url, init.group(1))).content if init else b"") + _get(urljoin(url, segments[-1])).content
    return _decode_first_frame(io.BytesIO(data))


def _pick_variant(master):
    """Highest resolution not above MAX_HEIGHT (else the smallest), from a master playlist."""
    variants, lines = [], master.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF") and index + 1 < len(lines):
            match = re.search(r"RESOLUTION=\d+x(\d+)", line)
            variants.append((int(match.group(1)) if match else 0, lines[index + 1].strip()))
    fitting = [v for v in variants if v[0] <= MAX_HEIGHT]
    return (max(fitting) if fitting else min(variants))[1]


def frame_from_video(data, position=0.5):
    """One frame from an uploaded video file (MP4, MOV, WEBM...), by default from the middle:
    the start of a phone video is often shaky."""
    try:
        import av  # noqa: PLC0415 - optional dependency, only needed for video
    except ImportError:
        raise SnapshotError("Video needs PyAV: `pip install av`") from None
    try:
        with av.open(io.BytesIO(data)) as container:
            if not container.streams.video:
                raise SnapshotError("The file has no video")
            target = container.duration * position / 1_000_000 if container.duration else 0  # seconds
            if target > 0:
                container.seek(int(container.duration * position))  # lands on the keyframe before the target
            frame = None
            for index, decoded in enumerate(container.decode(container.streams.video[0])):
                frame = decoded  # decode forward from the keyframe up to the target time
                if decoded.time is None or decoded.time >= target or index >= MAX_DECODE:
                    break
            if frame is not None:
                buffer = io.BytesIO()
                frame.to_image().save(buffer, format="JPEG", quality=90)
                return buffer.getvalue(), "image/jpeg"
    except SnapshotError:
        raise
    except Exception as error:  # noqa: BLE001 - PyAV raises many FFmpeg error types; report one line
        raise SnapshotError(f"Could not read the video file ({type(error).__name__})") from None
    raise SnapshotError("No frame could be decoded from the video file")


def _frame_from_stream(url):
    return _decode_first_frame(url)


def _decode_first_frame(source):
    try:
        import av  # noqa: PLC0415 - optional dependency, only needed for video
    except ImportError:
        raise SnapshotError("Video needs PyAV: `pip install av`") from None
    try:
        with av.open(source, timeout=TIMEOUT) if isinstance(source, str) else av.open(source) as container:
            if not container.streams.video:
                raise SnapshotError("The stream has no video")
            frame = next(container.decode(container.streams.video[0]), None)  # first decodable frame
            if frame is not None:
                buffer = io.BytesIO()
                frame.to_image().save(buffer, format="JPEG", quality=90)
                return buffer.getvalue(), "image/jpeg"
    except SnapshotError:
        raise
    except Exception as error:  # noqa: BLE001 - PyAV raises many FFmpeg error types; report one line
        raise SnapshotError(f"Could not read the video ({type(error).__name__})") from None
    raise SnapshotError("No frame could be decoded from the video")


def current_conditions(latitude, longitude):
    """Measured/modelled conditions right now from Open-Meteo. Missing values come back as None, never 0."""
    out = {"wave_height_m": None, "wave_period_s": None, "wind_kt": None, "gust_kt": None, "time": None,
           "error": None}
    try:
        marine = requests.get(MARINE_URL, timeout=TIMEOUT, params={
            "latitude": latitude, "longitude": longitude, "cell_selection": "sea",
            "current": "wave_height,wave_period", "timezone": "America/Los_Angeles"}).json().get("current", {})
        wind = requests.get(FORECAST_URL, timeout=TIMEOUT, params={
            "latitude": latitude, "longitude": longitude, "wind_speed_unit": "kn",
            "current": "wind_speed_10m,wind_gusts_10m", "timezone": "America/Los_Angeles"}).json().get("current", {})
    except (requests.RequestException, ValueError) as error:
        out["error"] = f"Open-Meteo unavailable ({type(error).__name__})"
        return out
    out.update(wave_height_m=marine.get("wave_height"), wave_period_s=marine.get("wave_period"),
               wind_kt=wind.get("wind_speed_10m"), gust_kt=wind.get("wind_gusts_10m"),
               time=wind.get("time") or marine.get("time"))
    return out
