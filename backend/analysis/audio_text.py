"""Capability 4: transcribe a voice memo (uploaded audio file or a recording made in the dashboard).

Runs on the laptop; no audio leaves the machine. Engines, tried in order:
1. mlx-whisper (Apple Silicon only): `pip install mlx-whisper`.
2. faster-whisper (any CPU, slower): `pip install faster-whisper`.
Audio is decoded with PyAV (`pip install av`), so no ffmpeg install is needed.
The first run of each engine downloads its model from Hugging Face (mlx turbo model: about 1.6 GB).
"""

import functools
import io
import platform
import sys

SUPPORTED = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".oga", ".opus", ".flac", ".webm", ".caf"}
SAMPLE_RATE = 16000  # what Whisper expects
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FASTER_MODEL = "small"  # CPU fallback: much faster than large-v3-turbo on an Intel laptop


def transcribe_audio(data):
    """Return {"text", "segments": [{"time", "speaker", "text"}], "method", "error"} for one audio file."""
    try:
        audio = decode_audio(data)
    except ImportError:
        return _failed("Audio decoding: `pip install av`")
    except Exception as error:  # noqa: BLE001 - corrupt or unknown container: report, don't crash the upload
        return _failed(f"Could not read the audio ({type(error).__name__})")
    if audio.size < SAMPLE_RATE // 2:
        return _failed("Recording is empty or shorter than half a second")
    errors = []
    for engine in (_mlx, _faster):
        try:
            return engine(audio)
        except _UnavailableError as reason:
            errors.append(str(reason))
        except Exception as error:  # noqa: BLE001 - e.g. model download failed offline: try the next engine
            errors.append(f"{engine.__name__.lstrip('_')}: {type(error).__name__}: {str(error)[:120]}")
    return _failed("Could not transcribe. " + " · ".join(errors))


def decode_audio(data):
    """Any audio container (m4a, mp3, wav, webm, ...) -> mono float32 numpy array at 16 kHz."""
    import av  # noqa: PLC0415 - optional dependency, imported only when audio arrives
    import numpy as np  # noqa: PLC0415

    chunks = []
    with av.open(io.BytesIO(data)) as container:
        if not container.streams.audio:
            raise ValueError("no audio stream")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(container.streams.audio[0]):
            chunks += [out.to_ndarray() for out in resampler.resample(frame)]
        chunks += [out.to_ndarray() for out in resampler.resample(None)]  # flush
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks, axis=1).reshape(-1).astype(np.float32) / 32768.0


def to_result(segments, method):
    """Whisper segments ({"start" seconds, "text"}) -> the same shape transcripts.parse_transcript returns."""
    rows = [{"time": _clock(s["start"]), "speaker": None, "text": s["text"].strip()}
            for s in segments if s["text"].strip()]
    if not rows:
        return {"text": "", "segments": [], "method": method, "error": "No speech recognised"}
    return {"text": "\n".join(r["text"] for r in rows), "segments": rows, "method": method, "error": None}


class _UnavailableError(Exception):
    """This engine cannot run here; try the next one."""


def _mlx(audio):
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise _UnavailableError("mlx-whisper: needs an Apple Silicon Mac")
    try:
        import mlx_whisper  # noqa: PLC0415 - optional, Apple Silicon only
    except ImportError:
        raise _UnavailableError("mlx-whisper: `pip install mlx-whisper`") from None
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=MLX_MODEL)
    return to_result(result["segments"], f"whisper (mlx, {MLX_MODEL.rsplit('/', maxsplit=1)[-1]})")


def _faster(audio):
    try:
        import faster_whisper  # noqa: PLC0415 - optional fallback engine
    except ImportError:
        raise _UnavailableError("faster-whisper: `pip install faster-whisper`") from None
    segments, _info = _faster_whisper_model(faster_whisper).transcribe(audio)
    return to_result([{"start": s.start, "text": s.text} for s in segments], f"whisper (faster-whisper, {FASTER_MODEL})")


@functools.cache
def _faster_whisper_model(faster_whisper):
    """Load once per process (a few seconds), not once per memo."""
    return faster_whisper.WhisperModel(FASTER_MODEL, device="cpu", compute_type="int8")


def _clock(seconds):
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _failed(error):
    return {"text": "", "segments": [], "method": None, "error": error}
