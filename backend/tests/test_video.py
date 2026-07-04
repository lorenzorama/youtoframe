import os
import re  # noqa: F401  (may already be needed)
from unittest.mock import patch, MagicMock

import pytest

from app.video import get_video_duration, download_video, extract_frame, compute_timestamps
from app.video import (
    Cue,
    get_video_info,
    pick_caption_language,
    parse_vtt,
    caption_for_timestamp,
)


def test_compute_timestamps_interval_only():
    result = compute_timestamps(duration=10.0, interval_seconds=5.0, manual_timestamps=None)
    assert result == [0.0, 5.0, 9.5]


def test_compute_timestamps_merges_manual_and_dedupes():
    result = compute_timestamps(duration=10.0, interval_seconds=5.0, manual_timestamps=[5.0, 7.5])
    assert result == [0.0, 5.0, 7.5, 9.5]


def test_compute_timestamps_rejects_out_of_range():
    with pytest.raises(ValueError):
        compute_timestamps(duration=10.0, interval_seconds=None, manual_timestamps=[15.0])


def test_compute_timestamps_requires_interval_or_manual():
    with pytest.raises(ValueError):
        compute_timestamps(duration=10.0, interval_seconds=None, manual_timestamps=None)


def test_compute_timestamps_never_samples_at_or_past_duration():
    # ffmpeg cannot reliably decode a frame exactly at (or past) a video's
    # reported duration -- no frame exists there, so extraction fails.
    # Regression test for a real job failure: seeking to a video's exact
    # reported duration (62.98s) produced zero frames and a hard ffmpeg
    # encoder error, while seeking to 62.9s succeeded.
    result = compute_timestamps(duration=62.98, interval_seconds=None, manual_timestamps=[62.98])
    assert result == [62.48]
    assert result[-1] < 62.98


def test_compute_timestamps_interval_final_timestamp_capped_below_duration():
    result = compute_timestamps(duration=10.0, interval_seconds=5.0, manual_timestamps=None)
    assert result[-1] < 10.0


def test_compute_timestamps_very_short_duration_does_not_go_negative():
    result = compute_timestamps(duration=0.2, interval_seconds=5.0, manual_timestamps=None)
    assert result == [0.0]


@patch("app.video.subprocess.run")
def test_get_video_duration_parses_yt_dlp_json(mock_run):
    mock_run.return_value = MagicMock(stdout='{"duration": 123.4}', returncode=0)
    duration = get_video_duration("https://youtube.com/watch?v=abc")
    assert duration == 123.4
    assert mock_run.called


@patch("app.video.subprocess.run")
def test_get_video_duration_passes_no_playlist(mock_run):
    # Regression test: a URL with a playlist parameter
    # (?v=abc&list=PLxxx) made yt-dlp -j dump one JSON object per playlist
    # video (100 lines observed against a real playlist), and json.loads()
    # raised "Extra data" trying to parse more than the first object.
    # --no-playlist forces yt-dlp to treat the URL as a single video.
    mock_run.return_value = MagicMock(stdout='{"duration": 123.4}', returncode=0)
    get_video_duration("https://youtube.com/watch?v=abc&list=PLxxx")
    args = mock_run.call_args[0][0]
    assert "--no-playlist" in args


@patch("app.video.subprocess.run")
def test_download_video_invokes_yt_dlp(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    download_video("https://youtube.com/watch?v=abc", "/data/1/1/source.mp4")
    args = mock_run.call_args[0][0]
    assert "yt-dlp" in args
    assert "/data/1/1/source.mp4" in args
    assert "--merge-output-format" in args
    assert "mp4" in args
    assert "-f" in args
    assert "bv*+ba/b" in args
    assert "--no-playlist" in args


@patch("app.video.subprocess.run")
def test_extract_frame_invokes_ffmpeg(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    extract_frame("/data/1/1/source.mp4", 5.0, "/data/1/1/frames/5.0.jpg")
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "-q:v" in args
    assert "3" in args


def test_pick_caption_language_prefers_english():
    info = {"subtitles": {"fr": [{}], "en": [{}]}, "automatic_captions": {}}
    assert pick_caption_language(info) == "en"


def test_pick_caption_language_prefers_english_variant():
    info = {"subtitles": {}, "automatic_captions": {"es": [{}], "en-US": [{}]}}
    assert pick_caption_language(info) == "en-US"


def test_pick_caption_language_falls_back_to_first_available():
    info = {"subtitles": {"de": [{}]}, "automatic_captions": {}}
    assert pick_caption_language(info) == "de"


def test_pick_caption_language_none_available():
    assert pick_caption_language({"subtitles": {}, "automatic_captions": {}}) is None
    assert pick_caption_language({}) is None


def test_parse_vtt_well_formed(tmp_path):
    vtt = tmp_path / "cap.en.vtt"
    vtt.write_text(
        "WEBVTT\n\n"
        "1\n"
        "00:00:01.000 --> 00:00:04.000\n"
        "Hello world\n\n"
        "2\n"
        "00:00:04.500 --> 00:00:08.000\n"
        "Second line\n"
    )
    cues = parse_vtt(str(vtt))
    assert cues == [Cue(1.0, 4.0, "Hello world"), Cue(4.5, 8.0, "Second line")]


def test_parse_vtt_strips_tags_and_dedupes_and_handles_cue_settings(tmp_path):
    vtt = tmp_path / "auto.en.vtt"
    vtt.write_text(
        "WEBVTT\n\n"
        "NOTE this is a note block\n\n"
        "00:00:01.000 --> 00:00:03.000 align:start position:0%\n"
        "Hello<00:00:01.500><c> there</c>\n\n"
        "00:00:03.000 --> 00:00:05.000\n"
        "Hello there\n\n"
        "00:00:05.000 --> 00:00:07.000\n"
        "next\n"
    )
    cues = parse_vtt(str(vtt))
    # tags stripped -> "Hello there"; the immediately-repeated identical line is collapsed
    assert cues == [Cue(1.0, 3.0, "Hello there"), Cue(5.0, 7.0, "next")]


def test_caption_for_timestamp_covering_nearest_and_none():
    cues = [Cue(1.0, 4.0, "a"), Cue(4.5, 8.0, "b")]
    assert caption_for_timestamp(cues, 2.0) == "a"        # covered
    assert caption_for_timestamp(cues, 4.2) == "a"        # gap -> nearest preceding
    assert caption_for_timestamp(cues, 6.0) == "b"        # covered
    assert caption_for_timestamp(cues, 0.5) is None       # before first cue
    assert caption_for_timestamp([], 3.0) is None         # no cues
