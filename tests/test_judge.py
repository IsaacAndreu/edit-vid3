from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from pipeline import judge as J
from pipeline.context import RunContext
from pipeline.schemas import Option, Selection


def opt(cid: str, total: float, *, source: str = "youtube", start: float | None = 10.0, end: float | None = 13.0,
        discarded: str | None = None, phash: str | None = None) -> Option:
    kind = "video" if source == "youtube" else "image"
    return Option.model_validate({
        "candidateId": cid, "source": source, "kind": kind, "pass": "fine",
        "start": start if kind == "video" else None, "end": end if kind == "video" else None,
        "scores": {"clip": total}, "total": total, "discarded": discarded, "phash": phash,
    })


def sel(cid: str, start: float | None = 10.0, end: float | None = 13.0, phash: str | None = None) -> Selection:
    kind = "video" if cid.startswith("yt") else "image"
    return Selection.model_validate({
        "shotId": "s001", "status": "selected", "decidedBy": "score", "candidateId": cid,
        "source": "youtube" if kind == "video" else "wikimedia", "kind": kind,
        "start": start if kind == "video" else None, "end": end if kind == "video" else None,
        "url": "u", "credit": "Fuente: X", "phash": phash,
    })


class PolicyTests(unittest.TestCase):
    def test_ranking_applies_source_bonus_and_drops_discarded(self) -> None:
        options = [opt("wm:1", 0.35, source="wikimedia"), opt("yt:a", 0.34), opt("yt:b", 0.9, discarded="texto")]
        order = [o.candidateId for _, o in J.ranked(options, {"youtube": 0.02})]
        self.assertEqual(order, ["yt:a", "wm:1"])

    def test_doubt_rules(self) -> None:
        self.assertTrue(J.is_doubtful([0.35, 0.34], margin=0.02, min_score=0.30))     # too close
        self.assertTrue(J.is_doubtful([0.28], margin=0.02, min_score=0.30))           # too low
        self.assertFalse(J.is_doubtful([0.40, 0.33], margin=0.02, min_score=0.30))   # clear winner
        self.assertFalse(J.is_doubtful([], margin=0.02, min_score=0.30))

    def test_repeats_by_timestamp_overlap_and_phash(self) -> None:
        used = [sel("yt:a", 10, 13, phash="ffff000000000000"), sel("wm:1")]
        self.assertTrue(J.is_repeat(opt("yt:a", 0.3, start=12, end=15), used, 6))     # overlaps 10-13
        self.assertFalse(J.is_repeat(opt("yt:a", 0.3, start=20, end=23), used, 6))    # same video, other moment
        self.assertTrue(J.is_repeat(opt("wm:1", 0.3, source="wikimedia"), used, 6))
        self.assertTrue(J.is_repeat(opt("yt:z", 0.3, phash="ffff000000000001"), used, 6))  # re-upload look-alike
        self.assertFalse(J.is_repeat(opt("yt:z", 0.3, phash="0000ffff00000000"), used, 6))

    def test_selection_enforces_cap_and_credit(self) -> None:
        with self.assertRaises(ValidationError):
            sel("yt:a", 10, 15.5)
        bad = sel("yt:a").model_dump()
        bad["credit"] = "Canal X"
        with self.assertRaises(ValidationError):
            Selection.model_validate(bad)
        Selection.model_validate({"shotId": "s1", "status": "fallback", "decidedBy": "fallback"})


class RunTests(unittest.TestCase):
    """End-to-end over fake stage outputs, with the vision call mocked."""

    def _write(self, root: Path, shots: list[dict], candidates: dict, scores: dict, hook: float = 0) -> RunContext:
        ctx = RunContext.create("t", root=root, config={"judge": {"margin": 0.02, "min_score": 0.30, "min_accept": 0.22,
                                                                  "hook_seconds": hook}})
        ctx.write_json("shots.json", {"slug": "t", "title": "T", "durationSeconds": 2.0 * len(shots), "context": "Casinos in Spain",
                                      "chapters": [{"title": "X", "startWord": 0, "fromScript": False}], "shots": shots})
        for sid, cands in candidates.items():
            ctx.write_json(f"candidates/{sid}.json", {"shotId": sid, "specHash": "h", "queries": {}, "candidates": cands})
        for sid, options in scores.items():
            ctx.write_json(f"scores/{sid}.json", {"shotId": sid, "inputsHash": "h", "needed": 2.0, "prompts": ["p"],
                                                  "options": [o.model_dump(by_alias=True, exclude_none=True) for o in options]})
        return ctx

    def test_clear_shots_skip_judge_and_fragments_are_not_reused(self) -> None:
        broll = {"visualIntent": "roulette", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}
        shots = [{"id": f"s00{i}", "type": "broll", "startWord": i, "endWord": i, "start": 2.0 * i, "end": 2.0 * i + 2,
                  "text": "t", "chapter": 0, "broll": broll} for i in range(3)]
        board = {"sheets": ["x.jpg"], "columns": 1, "rows": 1, "tileWidth": 1, "tileHeight": 1, "interval": 5, "frames": 1}
        video = {"id": "yt:a", "source": "youtube", "kind": "video", "url": "https://y/a", "title": "t", "channel": "Canal A",
                 "license": "l", "credit": "Fuente: Canal A", "attribution": "a", "query": "q", "rankScore": 1,
                 "durationSeconds": 100, "storyboard": board}
        photo = {**video, "id": "wm:1", "source": "wikimedia", "kind": "image", "storyboard": None, "imagePath": "p.jpg",
                 "credit": "Fuente: Ana / Wikimedia Commons", "url": "https://c/1"}
        scores = {
            "s000": [opt("yt:a", 0.40, start=10, end=12), opt("wm:1", 0.30, source="wikimedia")],   # clear → yt:a
            "s001": [opt("yt:a", 0.40, start=11, end=13), opt("wm:1", 0.41, source="wikimedia")],   # doubtful (0.42 vs 0.41)
            "s002": [opt("yt:a", 0.15, start=50, end=52)],                                          # below min_accept
        }
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._write(Path(tmp), shots, {s: [video, photo] for s in scores}, scores)
            calls = []

            def fake_judge(ctx, shot, sheet, letters, *args):
                calls.append(shot.id)
                return {"ranking": ["A", "B", "C"], "score": 0.8, "reason": "ok", "confidence": 0.9}  # C: not on the sheet

            with patch.object(J, "call_judge", side_effect=fake_judge), patch.object(J, "contact_sheet", return_value=__import__("numpy").zeros((10, 10, 3), "uint8")):
                J.run(ctx)
            result = json.loads((ctx.work_dir / "selection.json").read_text())["selections"]
        self.assertEqual(calls, ["s001"])
        self.assertEqual([r["status"] for r in result], ["selected", "selected", "fallback"])
        self.assertEqual(result[0]["candidateId"], "yt:a")
        self.assertEqual(result[0]["decidedBy"], "score")
        self.assertEqual(result[0]["credit"], "Fuente: Canal A")                  # copied from the manifest
        # judge preferred yt:a 11-13, but it overlaps the fragment used by s000 → its 2nd choice
        self.assertEqual(result[1]["candidateId"], "wm:1")
        self.assertEqual(result[1]["decidedBy"], "judge")

    def test_second_round_then_fallback_never_blind_pick(self) -> None:
        broll = {"visualIntent": "roulette", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}
        shots = [{"id": "s000", "type": "broll", "startWord": 0, "endWord": 0, "start": 0.0, "end": 2.0,
                  "text": "t", "chapter": 0, "broll": broll}]
        board = {"sheets": ["x.jpg"], "columns": 1, "rows": 1, "tileWidth": 1, "tileHeight": 1, "interval": 5, "frames": 1}
        video = {"id": "yt:a", "source": "youtube", "kind": "video", "url": "https://y/a", "title": "t", "channel": "A",
                 "license": "l", "credit": "Fuente: A", "attribution": "a", "query": "q", "rankScore": 1,
                 "durationSeconds": 500, "storyboard": board}
        options = [opt("yt:a", 0.30 - i * 0.001, start=10.0 * i + 10, end=10.0 * i + 12) for i in range(8)]
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._write(Path(tmp), shots, {"s000": [video]}, {"s000": options})
            sheets = []

            def reject_all(ctx, shot, sheet, letters, *args):
                sheets.append(letters)
                return {"ranking": [], "score": 0, "reason": "nothing fits", "confidence": 0.9}

            with patch.object(J, "call_judge", side_effect=reject_all), patch.object(J, "contact_sheet", return_value=__import__("numpy").zeros((10, 10, 3), "uint8")):
                J.run(ctx)
            result = json.loads((ctx.work_dir / "selection.json").read_text())["selections"]
        self.assertEqual(len(sheets), 2)                       # two rounds of 3, not all 8
        self.assertEqual(result[0]["status"], "fallback")      # no blind pick of option 7


    def test_hook_shots_are_always_judged_with_the_topic(self) -> None:
        broll = {"visualIntent": "roulette", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}
        shots = [{"id": f"s00{i}", "type": "broll", "startWord": i, "endWord": i, "start": 2.0 * i, "end": 2.0 * i + 2,
                  "text": "t", "chapter": 0, "broll": broll} for i in range(2)]
        board = {"sheets": ["x.jpg"], "columns": 1, "rows": 1, "tileWidth": 1, "tileHeight": 1, "interval": 5, "frames": 1}
        video = {"id": "yt:a", "source": "youtube", "kind": "video", "url": "https://y/a", "title": "t", "channel": "A",
                 "license": "l", "credit": "Fuente: A", "attribution": "a", "query": "q", "rankScore": 1,
                 "durationSeconds": 500, "storyboard": board}
        scores = {"s000": [opt("yt:a", 0.45, start=10, end=12)], "s001": [opt("yt:a", 0.45, start=100, end=102)]}  # both clear
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._write(Path(tmp), shots, {s: [video] for s in scores}, scores, hook=1.0)
            calls = []

            def fake_judge(ctx, shot, sheet, letters, topic, hook, *rest):
                calls.append((shot.id, topic, hook))
                return {"ranking": ["A"], "score": 0.8, "reason": "ok", "confidence": 0.9}

            with patch.object(J, "call_judge", side_effect=fake_judge), patch.object(J, "contact_sheet", return_value=__import__("numpy").zeros((10, 10, 3), "uint8")):
                J.run(ctx)
        self.assertEqual(calls, [("s000", "Casinos in Spain", True)])   # s001 (2 s) is clear and outside a 1 s hook

    def test_brief_carries_topic_and_hook(self) -> None:
        from pipeline.schemas import Shot
        shot = Shot.model_validate({"id": "s000", "type": "broll", "startWord": 0, "endWord": 0, "start": 0, "end": 2,
                                    "text": "hola", "chapter": 0,
                                    "broll": {"visualIntent": "roulette", "queries": ["a", "b", "c"], "queriesLocal": ["d"]}})
        brief = J.shot_brief(shot, "Casinos in Spain", True)
        self.assertTrue(brief.startswith("Video topic: Casinos in Spain\nHOOK"))
        self.assertNotIn("HOOK", J.shot_brief(shot))
        shot.broll.event = "Carlos Yulo floor final 2019 Stuttgart"
        brief = J.shot_brief(shot, "Gymnastics", False, "Carlos Yulo · artistic gymnastics")
        self.assertIn("VIDEO SUBJECT: Carlos Yulo · artistic gymnastics", brief)
        self.assertIn("EVENT of this shot: Carlos Yulo floor final 2019 Stuttgart", brief)


class ContactSheetTests(unittest.TestCase):
    def test_tile_outside_a_short_storyboard_sheet_is_skipped(self) -> None:
        import numpy as np
        import cv2
        from pipeline.schemas import Candidate, Option
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cv2.imwrite(str(root / "sb.jpg"), np.full((90, 160, 3), 120, np.uint8))   # one 160x90 tile, grid says 2x2
            board = {"sheets": ["sb.jpg"], "columns": 2, "rows": 2, "tileWidth": 160, "tileHeight": 90,
                     "interval": 1, "frames": 4}
            candidate = Candidate.model_validate({
                "id": "yt:a", "source": "youtube", "kind": "video", "url": "https://y/a", "title": "t", "channel": "A",
                "license": "l", "credit": "Fuente: A", "attribution": "a", "query": "q", "rankScore": 1,
                "durationSeconds": 20, "storyboard": board})
            option = Option.model_validate(opt("yt:a", 0.3, start=0.0, end=5.0).model_dump(by_alias=True, exclude_none=True))
            sheet = J.contact_sheet([option], {"yt:a": candidate}, root)
        self.assertEqual(sheet.shape[0], J.TILE[1])


class UsableTests(unittest.TestCase):
    def test_flagged_candidates_never_survive_the_ranking(self) -> None:
        verdict = {"ranking": ["B", "A", "C", "B", "D"], "score": 0.8, "reason": "r", "confidence": 0.9, "candidates": [
            {"letter": "A", "shows": "casino floor", "screenOrText": False, "onTopic": True},
            {"letter": "B", "shows": "speed test website", "screenOrText": True, "onTopic": False},
            {"letter": "C", "shows": "restaurant kitchen", "screenOrText": False, "onTopic": False},
        ]}
        self.assertEqual(J.usable(verdict, "ABC")["ranking"], ["A"])      # D is not on the sheet
        self.assertEqual(J.usable({"ranking": ["A"]}, "AB")["ranking"], ["A"])   # old cached verdicts still work


if __name__ == "__main__":
    unittest.main()
