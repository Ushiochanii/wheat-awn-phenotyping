#!/usr/bin/env python3
"""Create a local virtual environment, install Awn Studio, and prepare its model."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


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

    if sys.version_info < (3, 10):
        raise SystemExit("Awn Studio requires Python 3.10 or newer.")

    if not VENV.exists():
        print(f"[1/5] Creating virtual environment: {VENV}")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    else:
        print(f"[1/5] Reusing virtual environment: {VENV}")

    python = venv_python()
    print("[2/5] Updating pip")
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])

    if args.keep_torch:
        print("[3/5] Keeping the PyTorch build already installed in .venv")
    elif platform.system() in {"Linux", "Windows"}:
        print("[3/5] Installing CPU-only PyTorch")
        subprocess.check_call([
            str(python), "-m", "pip", "install",
            "torch", "torchvision",
            "--index-url", "https://download.pytorch.org/whl/cpu",
        ])
    else:
        print("[3/5] Installing PyTorch")
        subprocess.check_call([str(python), "-m", "pip", "install", "torch", "torchvision"])

    print("[4/5] Installing Awn Studio")
    subprocess.check_call([str(python), "-m", "pip", "install", "-e", str(ROOT)])

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
