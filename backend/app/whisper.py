from app.config import settings
from app.video import Cue, _run

# Loaded lazily, once per worker process. The faster_whisper import is heavy
# and is deferred so the module (and its non-model functions) import without
# the package present, and tests can mock _get_model.
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(settings.whisper_model, compute_type=settings.whisper_compute_type)
    return _model


def extract_audio(video_path: str, dest_wav: str) -> None:
    _run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            dest_wav,
        ]
    )


def transcribe_audio(wav_path: str) -> tuple[str | None, list[Cue]]:
    model = _get_model()
    segments, info = model.transcribe(wav_path)
    cues = [Cue(seg.start, seg.end, (seg.text or "").strip()) for seg in segments]
    return getattr(info, "language", None), cues
