#!/usr/bin/env python3
"""Create a local virtual environment, install Awn Studio, and prepare its model."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _preflight() -> None:
    system = platform.system() or "Unknown"
    machine = platform.machine() or "Unknown"
    version = platform.python_version()
    free_gib = shutil.disk_usage(ROOT).free / (1024 ** 3)

    print("Awn Studio preflight")
    print(f"  Platform: {system} {machine}")
    print(f"  Python:   {version}")
    print(f"  Free:     {free_gib:.1f} GiB")

    if sys.version_info < (3, 10):
        raise SystemExit("Awn Studio requires Python 3.10 or newer.")
    if sys.version_info >= (3, 13):
        print("  Note: Python 3.13+ is not yet part of the validated release matrix.")
    if free_gib < 4:
        raise SystemExit("Awn Studio needs at least 4 GiB of free disk space for the environment and model cache.")
    if system == "Darwin" and machine.lower() in {"arm64", "aarch64"}:
        print("  Compute:  Apple Silicon detected; MPS will be used when available.")
    elif system == "Darwin":
        print("  Compute:  Intel macOS detected; CPU runtime will be used by default.")
    elif machine.lower() not in {"x86_64", "amd64", "arm64", "aarch64"}:
        print(f"  Warning: architecture {machine} is not in the validated platform set.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a local Awn Studio environment.")
    parser.add_argument(
        "--no-model-download",
        action="store_true",
        help="Install and validate the environment without downloading the default model.",
    )
    parser.add_argument(
        "--keep-torch",
        action="store_true",
        help="Keep a PyTorch build already installed in .venv instead of installing the CPU build.",
    )
    args = parser.parse_args()

    _preflight()

    created_venv = not VENV.exists()
    if created_venv:
        print(f"[1/5] Creating virtual environment: {VENV}")
        try:
            subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
        except subprocess.CalledProcessError as error:
            hint = " On Debian/Ubuntu, install the matching python3-venv package first." if platform.system() == "Linux" else ""
            raise SystemExit(f"Could not create the virtual environment.{hint}") from error
    else:
        print(f"[1/5] Reusing virtual environment: {VENV}")

    python = venv_python()
    if created_venv:
        print("[2/5] Updating pip")
        subprocess.check_call([
            str(python), "-m", "pip", "--disable-pip-version-check",
            "install", "--upgrade", "pip",
        ])
    else:
        print("[2/5] Reusing existing pip")

    if args.keep_torch:
        print("[3/5] Keeping the PyTorch build already installed in .venv")
    elif platform.system() in {"Linux", "Windows"}:
        probe = subprocess.run(
            [
                str(python),
                "-c",
                (
                    "import torch, torchvision; "
                    "assert torch.version.cuda is None and getattr(torch.version, 'hip', None) is None"
                ),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if probe.returncode == 0:
            print("[3/5] Reusing existing CPU-only PyTorch")
        else:
            print("[3/5] Installing CPU-only PyTorch")
            subprocess.check_call([
                str(python), "-m", "pip", "--disable-pip-version-check",
                "install", "--prefer-binary",
                "torch", "torchvision",
                "--index-url", "https://download.pytorch.org/whl/cpu",
            ])
    else:
        print("[3/5] Installing PyTorch")
        subprocess.check_call([
            str(python), "-m", "pip", "--disable-pip-version-check",
            "install", "--prefer-binary", "torch", "torchvision",
        ])

    print("[4/5] Installing Awn Studio")
    subprocess.check_call([
        str(python), "-m", "pip", "--disable-pip-version-check",
        "install", "--prefer-binary", "-e", str(ROOT),
    ])

    print("[5/5] Verifying runtime and model")
    command = [str(python), "-m", "awnphen.cli", "setup"]
    if args.no_model_download:
        command.append("--no-download")
    subprocess.check_call(command)

    if os.name == "nt":
        launcher = VENV / "Scripts" / "awnphen.exe"
    else:
        launcher = VENV / "bin" / "awnphen"
    print()
    print("Awn Studio is ready.")
    print(f"Launch with: {launcher} studio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
