from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.cli import _run_parser, main
from pipeline.runner import RunRequest
from pipeline.runner import run_pipeline as _run_request


# --- Compatibility with code that imports this module ----------------------
# Earlier versions exposed `_parser()` and `run_pipeline(args)` here. They are
# kept so an external launcher (a web panel, a cron script) keeps working.
def _parser() -> argparse.ArgumentParser:
    return _run_parser()


def run_pipeline(args: argparse.Namespace) -> Path:
    """Run from an argparse namespace with at least guion, voz and output."""

    return _run_request(
        RunRequest(
            script_path=Path(args.guion),
            audio_path=Path(args.voz),
            output_path=Path(args.output),
            avatar_dir=getattr(args, "avatar_dir", None),
            skip_render=bool(getattr(args, "skip_render", False)),
            skip_audio_master=bool(getattr(args, "skip_audio_master", False)),
            skip_third_party=bool(getattr(args, "skip_third_party", False)),
            skip_preflight=bool(getattr(args, "skip_preflight", False)),
            fresh=bool(getattr(args, "fresh", False)),
        )
    )


if __name__ == "__main__":
    sys.exit(main())
