"""Command-line entry point for the public release."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .model import resolve_weights


def _bundle_root() -> Path:
    return Path(__file__).resolve().parent / "_bundle"


def _studio_dir() -> Path:
    return _bundle_root() / "app" / "awn_studio"


def _demo_image() -> Path:
    return _bundle_root() / "examples" / "demo_page.jpg"


def _run_predict(args) -> int:
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        raise FileNotFoundError(f"Input image not found: {image}")
    if args.mm_per_px is not None and not 0 < args.mm_per_px < 10:
        raise ValueError("--mm-per-px must be a positive physical calibration.")
    weights = resolve_weights(args.weights)
    # Runtime implementation is copied from the canonical frozen pipeline during
    # release materialization. Keeping this import lazy makes --help usable in a
    # minimal environment.
    from awnphen.public_runtime import auto_calibrate, predict
    mm_per_px = args.mm_per_px
    if mm_per_px is None:
        mm_per_px = auto_calibrate(image)
        print(f"Automatic calibration: {mm_per_px:.6f} mm/px")
    output = Path(args.output).expanduser().resolve()
    predict(
        image=image,
        output=output,
        weights=weights,
        mm_per_px=mm_per_px,
        device=args.device,
    )
    print(f"Results written to {output}")
    return 0


def _run_demo(args) -> int:
    demo = _demo_image()
    if not demo.is_file():
        raise FileNotFoundError("Bundled demo image is missing.")
    args.image = str(demo)
    args.output = args.output or "runs/demo"
    return _run_predict(args)


def _run_studio(args) -> int:
    studio = _studio_dir()
    launcher = studio / "serve_model.py"
    if not launcher.is_file():
        raise RuntimeError(
            "Awn Studio runtime has not been materialized into this staging build yet."
        )
    env = dict(os.environ)
    if args.weights:
        env["AWNPHEN_WEIGHTS"] = str(resolve_weights(args.weights))
    return subprocess.call(
        [sys.executable, str(launcher), "--device", args.device],
        env=env,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awnphen",
        description="Wheat awn phenotyping and Awn Studio.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    predict = sub.add_parser("predict", help="Measure one scanned wheat image.")
    predict.add_argument("image")
    predict.add_argument("--mm-per-px", type=float, help="Override automatic grid calibration.")
    predict.add_argument("--weights")
    predict.add_argument("--output", default="runs/predict")
    predict.add_argument("--device", default="cpu")
    predict.set_defaults(func=_run_predict)

    demo = sub.add_parser("demo", help="Run the bundled example.")
    demo.add_argument("--mm-per-px", type=float, help="Override automatic grid calibration.")
    demo.add_argument("--weights")
    demo.add_argument("--output")
    demo.add_argument("--device", default="cpu")
    demo.set_defaults(func=_run_demo)

    studio = sub.add_parser("studio", help="Launch Awn Studio locally.")
    studio.add_argument("--weights")
    studio.add_argument("--device", default="cpu")
    studio.set_defaults(func=_run_studio)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args) or 0)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
