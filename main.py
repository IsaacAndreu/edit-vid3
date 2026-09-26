from __future__ import annotations

import argparse

from pipeline.config import ConfigError
from pipeline.context import RunContext
from pipeline.qa import QABlocked
from pipeline.runner import STAGE_NAMES, StageNotImplemented, run_stages


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera un vídeo documental a partir de materiales/<slug>/{titulo.txt, guion.txt, voz.mp3}."
    )
    parser.add_argument("--slug", required=True, help="Carpeta dentro de materiales/, p. ej. Video1.")
    parser.add_argument(
        "--force",
        action="append",
        default=[],
        metavar="ETAPA",
        help=f"Vuelve a ejecutar una etapa aunque esté al día (repetible, o 'all'). Etapas: {', '.join(STAGE_NAMES)}.",
    )
    parser.add_argument("--until", choices=STAGE_NAMES, help="Detiene el pipeline después de esta etapa.")
    parser.add_argument("--review", action="store_true", help="Se detiene tras la QA para revisar antes del render.")
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        ctx = RunContext.create(args.slug)
        if not ctx.materials_dir.is_dir():
            raise FileNotFoundError(f"No existe {ctx.materials_dir}")
        run_stages(ctx, force=set(args.force), until=args.until, review=args.review)
    except StageNotImplemented as error:
        raise SystemExit(f"Parada: {error}") from error
    except QABlocked as error:
        raise SystemExit(f"Render bloqueado por la QA: {error}. Revisa out/{args.slug}/qa/report.md") from error
    except (ConfigError, FileNotFoundError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error


if __name__ == "__main__":
    main()
