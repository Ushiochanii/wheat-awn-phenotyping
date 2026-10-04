"""Command-line entry point for the public release."""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

from .model import resolve_weights


def _bundle_root() -> Path:
    return Path(__file__).resolve().parent / "_bundle"


def _studio_dir() -> Path:
    return _bundle_root() / "app" / "awn_studio"


def _runtime_check(*, download_model: bool) -> tuple[list[str], Path | None]:
    checks = [
        ("numpy", "NumPy"),
        ("PIL", "Pillow"),
        ("yaml", "PyYAML"),
        ("shapely", "Shapely"),
        ("scipy", "SciPy"),
        ("skimage", "scikit-image"),
        ("cv2", "OpenCV"),
        ("ultralytics", "Ultralytics"),
        ("huggingface_hub", "Hugging Face Hub"),
        ("torch", "PyTorch"),
    ]
    missing: list[str] = []
    for module, label in checks:
        try:
            importlib.import_module(module)
        except Exception:
            missing.append(label)

    studio = _studio_dir() / "serve_model.py"
    if not studio.is_file():
        missing.append("Awn Studio bundled web application")

    weights = None
    if download_model and not missing:
        weights = resolve_weights()
    return missing, weights


def _run_setup(args) -> int:
    missing, weights = _runtime_check(download_model=not args.no_download)
    if missing:
        raise RuntimeError(
            "Setup check failed. Missing or unusable components: "
            + ", ".join(missing)
            + ". Reinstall with 'python -m pip install -e .'."
        )

    print("Awn Studio runtime: ready")
    if weights is not None:
        print(f"Default model: ready ({weights})")
    else:
        print("Default model: download skipped")
    try:
        import torch
        if torch.cuda.is_available():
            print(f"Compute: GPU available ({torch.cuda.get_device_name(0)})")
        else:
            print("Compute: CPU ready; no CUDA GPU detected")
    except Exception:
        print("Compute: PyTorch available")
    probe_override = os.environ.get("AWNPHEN_SCALE_PROBE_WEIGHTS")
    probe_default = _bundle_root() / "models" / "spikelet_scale_probe.pt"
    probe = Path(probe_override).expanduser() if probe_override else probe_default
    if probe.is_file():
        print(f"Optional resolution probe: ready ({probe})")
    else:
        print("Optional resolution probe: not configured; resolution preflight will pass through")
    print("Next: awnphen studio")
    return 0


def _run_predict(args) -> int:
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        raise FileNotFoundError(f"Input image not found: {image}")
    if args.mm_per_px is not None and not 0 < args.mm_per_px < 10:
        raise ValueError("--mm-per-px must be a positive physical calibration.")
    weights = resolve_weights(args.weights)
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


def _run_studio(args) -> int:
    studio = _studio_dir()
    launcher = studio / "serve_model.py"
    if not launcher.is_file():
        raise RuntimeError(
            "Awn Studio runtime has not been materialized into this installation."
        )
    env = dict(os.environ)
    env["AWNPHEN_WEIGHTS"] = str(resolve_weights(args.weights))
    command = [
        sys.executable,
        str(launcher),
        "--device",
        args.device,
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.no_browser:
        command.append("--no-browser")
    return subprocess.call(command, env=env)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awnphen",
        description="Wheat awn phenotyping and Awn Studio.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser(
        "setup",
        help="Verify the runtime and prepare the default model.",
    )
    setup.add_argument(
        "--no-download",
        action="store_true",
        help="Check the runtime without downloading the default model.",
    )
    setup.set_defaults(func=_run_setup)

    predict = sub.add_parser("predict", help="Measure one digitized wheat image.")
    predict.add_argument("image")
    predict.add_argument("--mm-per-px", type=float, help="Override automatic grid calibration.")
    predict.add_argument("--weights")
    predict.add_argument("--output", default="runs/predict")
    predict.add_argument("--device", default="cpu")
    predict.set_defaults(func=_run_predict)

    studio = sub.add_parser("studio", help="Launch Awn Studio locally.")
    studio.add_argument("--weights")
    studio.add_argument("--device", default="cpu")
    studio.add_argument("--host", default="127.0.0.1")
    studio.add_argument("--port", type=int, default=8780)
    studio.add_argument("--no-browser", action="store_true")
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
