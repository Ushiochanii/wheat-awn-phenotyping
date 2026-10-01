"""Thin public prediction boundary over the canonical scientific runtime."""
from pathlib import Path


def auto_calibrate(image: Path) -> float:
    """Estimate millimetres per pixel from the scan grid used by the pipeline."""
    import cv2
    import numpy as np
    from awnphen.phenotyping.measurement.calibration import GRID_MM, calibrate_grid_v2

    source = cv2.imread(str(image), cv2.IMREAD_COLOR)
    if source is None or source.size == 0:
        raise ValueError(f"Could not read image for calibration: {image}")
    x_cal, y_cal, _qc, _ = calibrate_grid_v2(source)
    periods = np.asarray(
        [float(x_cal["period_px"]), float(y_cal["period_px"])],
        dtype=np.float64,
    )
    mean_period = float(np.mean(periods))
    if not np.isfinite(mean_period) or mean_period <= 0:
        raise RuntimeError(
            "Automatic grid calibration failed. Pass --mm-per-px explicitly."
        )
    return float(GRID_MM / mean_period)


def predict(*, image: Path, output: Path, weights: Path, mm_per_px: float, device: str):
    from awnphen.pipeline import run_workbench_pipeline
    from ultralytics import YOLO

    model = YOLO(str(weights))
    if dict(model.names) != {0: "awn", 1: "spikelet"}:
        raise ValueError(f"Model class mapping mismatch: {model.names}")
    output.mkdir(parents=True, exist_ok=True)

    def progress(message, tiles, **_):
        print(message)

    return run_workbench_pipeline(
        source=image,
        workspace=output / "workspace",
        model=model,
        weights=weights,
        device=device,
        mm_per_px=mm_per_px,
        progress=progress,
    )
