"""The resolution wins over the frame rate and the codec: a 60 fps source gives its 720p (at 30 fps if there is one),
never 480p; and a 720p in another codec beats the only avc1, a 360p."""

from __future__ import annotations

from pipeline.sourcing.youtube import YouTubeSource, cap_fps, cap_height, selectable

DEFAULT = "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]/b[height<=1080]"


def _v(fid, height, fps, vcodec):
    return {"format_id": fid, "protocol": "https", "ext": "mp4", "vcodec": vcodec, "acodec": "none",
            "height": height, "width": height * 16 // 9, "fps": fps, "tbr": height * fps / 10, "url": f"https://x/{fid}"}


def _pick(tmp_path, formats, request):
    data = {"id": "abcdefghijk", "extractor": "youtube", "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "formats": formats}
    yt = YouTubeSource(root=tmp_path, cache_dir=tmp_path, config={"min_interval": 0, "cookies": "never"})
    with yt._ydl({"format": request, "simulate": True, "quiet": True}) as ydl:
        chosen = ydl.process_ie_result(selectable(data), download=False)
    return chosen["format_id"]


def request():
    return cap_fps(cap_height(DEFAULT, 720), 30, resolution_first=True)


def test_a_60fps_source_gives_its_720p_not_480p(tmp_path):
    formats = [_v("298", 720, 60, "avc1.4d4020"), _v("135", 480, 30, "avc1.4d401f"), _v("134", 360, 30, "avc1.4d401e")]
    assert _pick(tmp_path, formats, request()) == "298"


def test_at_the_same_resolution_30fps_first(tmp_path):
    formats = [_v("298", 720, 60, "avc1.4d4020"), _v("136", 720, 30, "avc1.4d401f"), _v("135", 480, 30, "avc1.4d401f")]
    assert _pick(tmp_path, formats, request()) == "136"


def test_a_720p_in_another_codec_beats_the_only_avc1_at_360p(tmp_path):
    formats = [_v("247", 720, 30, "vp9"), _v("134", 360, 30, "avc1.4d401e")]
    assert _pick(tmp_path, formats, request()) == "247"


def test_at_the_same_resolution_avc1_first(tmp_path):
    formats = [_v("247", 720, 30, "vp9"), _v("136", 720, 30, "avc1.4d401f")]
    assert _pick(tmp_path, formats, request()) == "136"



def test_off_by_default_as_before(tmp_path):
    formats = [_v("298", 720, 60, "avc1.4d4020"), _v("135", 480, 30, "avc1.4d401f")]
    assert _pick(tmp_path, formats, cap_fps(cap_height(DEFAULT, 720), 30)) == "135"     # fewer bytes, as always
