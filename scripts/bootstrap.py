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

INTEL_MAC_MAX_PYTHON = (3, 12)
INTEL_MAC_PYTHON_CANDIDATES = ("python3.12", "python3.11", "python3.10")
INTEL_MAC_TORCH = "torch==2.2.2"
INTEL_MAC_TORCHVISION = "torchvision==0.17.2"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _is_intel_macos() -> bool:
    return platform.system() == "Darwin" and platform.machine().lower() in {"x86_64", "amd64"}


def _python_minor(executable: str | Path) -> tuple[int, int] | None:
    try:
        probe = subprocess.run(
            [
                str(executable),
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    if probe.returncode != 0:
        return None

    try:
        major, minor = probe.stdout.strip().split(".", 1)
        return int(major), int(minor)
    except (TypeError, ValueError):
        return None


def _intel_mac_python_compatible(executable: str | Path) -> bool:
    version = _python_minor(executable)
    return version is not None and (3, 10) <= version <= INTEL_MAC_MAX_PYTHON


def _find_intel_mac_python() -> str | None:
    candidates: list[str] = [sys.executable]
    for name in INTEL_MAC_PYTHON_CANDIDATES:
        resolved = shutil.which(name)
        if resolved:
            candidates.append(resolved)

    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(Path(candidate).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        if _intel_mac_python_compatible(resolved):
            return resolved
    return None


def _find_environment_manager() -> str | None:
    for name in ("micromamba", "mamba", "conda"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def _remove_incompatible_venv() -> None:
    python = venv_python()
    if not VENV.exists() or not python.exists():
        return
    if _intel_mac_python_compatible(python):
        return

    version = _python_minor(python)
    label = ".".join(map(str, version)) if version else "unknown"
    print(
        f"[1/5] Existing .venv uses Python {label}, which cannot use the "
        "maintained Intel macOS PyTorch wheel. Recreating it."
    )
    shutil.rmtree(VENV)


def _create_intel_mac_venv() -> bool:
    """Create a Python <=3.12 environment for the final Intel-macOS PyTorch wheels."""
    _remove_incompatible_venv()

    if VENV.exists() and venv_python().exists():
        return False

    compatible_python = _find_intel_mac_python()
    if compatible_python:
        version = _python_minor(compatible_python)
        version_label = ".".join(map(str, version)) if version else "compatible"
        print(f"[1/5] Creating Intel macOS environment with Python {version_label}: {VENV}")
        subprocess.check_call([compatible_python, "-m", "venv", str(VENV)])
        return True

    manager = _find_environment_manager()
    if manager:
        manager_name = Path(manager).name
        print(
            f"[1/5] Python 3.10-3.12 was not found. "
            f"Creating a Python 3.12 environment with {manager_name}: {VENV}"
        )
        subprocess.check_call(
            [manager, "create", "-y", "-p", str(VENV), "python=3.12", "pip"]
        )
        return True

    raise SystemExit(
        "Intel macOS needs Python 3.10-3.12 because PyTorch no longer publishes "
        "Intel-macOS wheels for Python 3.13+. Install Python 3.12 and rerun this "
        "script, for example with 'brew install python@3.12' followed by "
        "'python3.12 scripts/bootstrap.py'. If you use micromamba/conda, making "
        "that command available on PATH lets this installer create the compatible "
        "environment automatically."
    )


def _prepare_venv() -> bool:
    if _is_intel_macos():
        return _create_intel_mac_venv()

    created_venv = not VENV.exists()
    if created_venv:
        print(f"[1/5] Creating virtual environment: {VENV}")
        try:
            subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
        except subprocess.CalledProcessError as error:
            hint = (
                " On Debian/Ubuntu, install the matching python3-venv package first."
                if platform.system() == "Linux"
                else ""
            )
            raise SystemExit(f"Could not create the virtual environment.{hint}") from error
    else:
        print(f"[1/5] Reusing virtual environment: {VENV}")
    return created_venv


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
        if _is_intel_macos():
            print(
                "  Compatibility: Intel macOS requires Python <=3.12 for PyTorch; "
                "the installer will switch to or create a compatible environment."
            )
        else:
            print("  Note: Python 3.13+ is not yet part of the validated release matrix.")
    if free_gib < 4:
        raise SystemExit(
            "Awn Studio needs at least 4 GiB of free disk space for the environment and model cache."
        )
    if system == "Darwin" and machine.lower() in {"arm64", "aarch64"}:
        print("  Compute:  Apple Silicon detected; MPS will be used when available.")
    elif _is_intel_macos():
        print(
            "  Compute:  Intel macOS detected; CPU runtime will use the final "
            "x86_64 PyTorch release supported on macOS."
        )
    elif machine.lower() not in {"x86_64", "amd64", "arm64", "aarch64"}:
        print(f"  Warning: architecture {machine} is not in the validated platform set.")
    print()


def _install_intel_mac_torch(python: Path) -> None:
    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import torch, torchvision; "
                "assert torch.__version__.split('+')[0] == '2.2.2'; "
                "assert torchvision.__version__.split('+')[0] == '0.17.2'"
            ),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode == 0:
        print("[3/5] Reusing Intel macOS PyTorch 2.2.2")
        return

    print("[3/5] Installing Intel macOS compatibility runtime")
    subprocess.check_call(
        [
            str(python),
            "-m",
            "pip",
            "--disable-pip-version-check",
            "install",
            "--prefer-binary",
            "numpy<2",
            "opencv-python<4.12",
            INTEL_MAC_TORCH,
            INTEL_MAC_TORCHVISION,
        ]
    )


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
        help="Keep a PyTorch build already installed in .venv instead of installing the platform default.",
    )
    args = parser.parse_args()

    _preflight()
    created_venv = _prepare_venv()

    python = venv_python()
    if not python.exists():
        raise SystemExit(f"Environment creation did not produce a Python executable at {python}")

    if created_venv:
        print("[2/5] Updating pip")
        subprocess.check_call(
            [
                str(python),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "install",
                "--upgrade",
                "pip",
            ]
        )
    else:
        print("[2/5] Reusing existing pip")

    if args.keep_torch:
        print("[3/5] Keeping the PyTorch build already installed in .venv")
    elif _is_intel_macos():
        _install_intel_mac_torch(python)
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
            subprocess.check_call(
                [
                    str(python),
                    "-m",
                    "pip",
                    "--disable-pip-version-check",
                    "install",
                    "--prefer-binary",
                    "torch",
                    "torchvision",
                    "--index-url",
                    "https://download.pytorch.org/whl/cpu",
                ]
            )
    else:
        print("[3/5] Installing PyTorch")
        subprocess.check_call(
            [
                str(python),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "install",
                "--prefer-binary",
                "torch",
                "torchvision",
            ]
        )

    print("[4/5] Installing Awn Studio")
    subprocess.check_call(
        [
            str(python),
            "-m",
            "pip",
            "--disable-pip-version-check",
            "install",
            "--prefer-binary",
            "-e",
            str(ROOT),
        ]
    )

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
