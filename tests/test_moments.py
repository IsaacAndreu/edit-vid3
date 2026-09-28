from pipeline.render import voice_chains
from pipeline.schemas import Timeline
from pipeline.timeline import with_moments


def _timeline() -> Timeline:
    shots = [{"id": f"s{i}", "type": "broll", "from": i * 60, "durationInFrames": 60, "text": "",
              "media": {"src": f"media/s{i}.mp4", "kind": "video", "source": "youtube", "credit": "Fuente: X"}}
             for i in range(5)]
    return Timeline.model_validate({
        "slug": "x", "title": "T", "fps": 30, "width": 1920, "height": 1080, "durationInFrames": 300, "shots": shots,
        "groups": [{"id": "g", "kind": "stat", "from": 60, "durationInFrames": 60, "stat": {"value": "1", "label": "a", "sign": "neutral"}}],
        "labels": [], "audio": {"voice": "audio/voz.mp3", "speech": [[0, 150], [160, 300]]}})


def test_moment_goes_to_nearest_free_boundary_and_shifts_the_rest():
    out = with_moments(_timeline(), [("coldopen/m.mp4", 6.3, 4.0, "Fuente: Olympics", 1920, 1080)], 30)
    ids = [s.id for s in out.shots]
    assert ids == ["s0", "s1", "s2", "m01", "s3", "s4"]                # 189 → boundary 180
    m = out.shots[3]
    assert (m.from_, m.durationInFrames, m.coldOpen) == (180, 120, True)
    assert out.shots[4].from_ == 300 and out.durationInFrames == 420
    assert out.audio.voiceGaps == [(180, 120)]
    assert out.audio.speech == [(0, 150), (160, 180), (300, 420)]
    assert out.audio.clips[0].from_ == 180


def test_moment_never_cuts_a_panel():
    t = _timeline()
    t.groups[0].durationInFrames = 120                                 # panel over s1 and s2 (60-180)
    out = with_moments(t, [("coldopen/m.mp4", 4.5, 4.0, "Fuente: X", 1920, 1080)], 30)   # 135: 120 is inside it
    assert [s.id for s in out.shots].index("m01") == 3                  # → 180, after the panel
    assert out.groups[0].from_ == 60 and out.groups[0].durationInFrames == 120


def test_voice_chains_pause_the_narration():
    assert voice_chains(0, 30, [], 30, "anull") == ["[0:a]anull,adelay=1000:all=1[voice]"]
    chains = voice_chains(0, 0, [(60, 30)], 30, "anull")
    assert chains[0] == "[0:a]anull,asplit=2[vs0][vs1]"
    assert chains[1] == "[vs0]atrim=start=0.0000:end=2.0000,asetpts=PTS-STARTPTS[vp0]"
    assert chains[2] == "[vs1]atrim=start=2.0000,asetpts=PTS-STARTPTS,adelay=3000:all=1[vp1]"
    assert chains[3] == "[vp0][vp1]amix=inputs=2:normalize=0,asetpts=N/SR/TB[voice]"


def test_transition_sfx_rotate_and_keep_a_minimum_gap():
    from pipeline.timeline import transition_sfx

    t = _timeline()
    t.shots[2].type = "chapter"
    t.shots[2].chapterTitle = "X"
    out = transition_sfx(t, ["a.mp3", "b.mp3"], 0.6, min_gap=1.0)
    assert [(s.src, s.from_) for s in out] == [("a.mp3", 56), ("b.mp3", 116)]   # stat at 60, chapter at 120
    assert [s.from_ for s in transition_sfx(t, ["a.mp3"], 0.6, min_gap=4.0)] == [116]   # chapter wins, stat too close


def test_main_whoosh_most_of_the_time():
    from pipeline.timeline import transition_sfx

    t = _timeline()
    for s in t.shots[1:]:
        s.type = "chapter"
        s.chapterTitle = "X"
    out = transition_sfx(t, ["w-1-fast.mp3", "w-2-espada.mp3", "w-3-giro.mp3"], 0.6, min_gap=1.0, main="espada", other_every=4)
    assert [s.src for s in out] == ["w-2-espada.mp3"] * 3 + ["w-1-fast.mp3"]
