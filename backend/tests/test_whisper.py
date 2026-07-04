from unittest.mock import patch, MagicMock

from app.video import Cue
from app.whisper import extract_audio, transcribe_audio


# extract_audio calls `_run` (which lives in app.video), so patch subprocess
# in app.video's namespace — that is where the call resolves.
@patch("app.video.subprocess.run")
def test_extract_audio_invokes_ffmpeg(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    extract_audio("/data/1/1/source.mp4", "/data/1/1/audio.wav")
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "-ac" in args and "1" in args        # mono
    assert "-ar" in args and "16000" in args     # 16 kHz
    assert "-vn" in args                          # drop video
    assert "/data/1/1/audio.wav" in args


def test_transcribe_audio_maps_segments_to_cues(monkeypatch):
    seg1 = MagicMock(start=0.0, end=4.0, text=" Hello world ")
    seg2 = MagicMock(start=4.0, end=8.0, text="Second line")
    info = MagicMock(language="en")

    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([seg1, seg2], info)
    monkeypatch.setattr("app.whisper._get_model", lambda: fake_model)

    language, cues = transcribe_audio("/data/1/1/audio.wav")
    assert language == "en"
    assert cues == [Cue(0.0, 4.0, "Hello world"), Cue(4.0, 8.0, "Second line")]
    fake_model.transcribe.assert_called_once_with("/data/1/1/audio.wav")
