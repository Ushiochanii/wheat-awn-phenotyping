"""Mask2Former adapter for the canonical awn instance-segmentation evidence contract."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

from awnphen.modeling.inference.instance_segmentation_adapter import InstanceMaskPrediction
from awnphen.phenotyping.detection.providers import sha256_file


@dataclass(slots=True)
class Mask2FormerSegmentationAdapter:
    """Normalize Hugging Face Mask2Former outputs to canonical awn/spikelet masks."""

    model: Any
    processor: Any
    checkpoint_dir: Path | None = None
    input_size: int = 640

    def __post_init__(self) -> None:
        self.input_size = int(self.input_size)
        if self.input_size <= 0:
            raise ValueError("input_size must be positive")
        if self.checkpoint_dir is not None:
            self.checkpoint_dir = Path(self.checkpoint_dir)
            if not self.checkpoint_dir.is_dir():
                raise FileNotFoundError(self.checkpoint_dir)

    @property
    def architecture_name(self) -> str:
        return "Mask2Former Swin-L"

    @property
    def model_input_size(self) -> int:
        return self.input_size

    def _checkpoint_weight(self) -> Path | None:
        if self.checkpoint_dir is None:
            return None
        for name in ("model.safetensors", "pytorch_model.bin"):
            path = self.checkpoint_dir / name
            if path.is_file():
                return path
        return None

    def provenance_payload(self) -> dict[str, Any]:
        try:
            transformers_version = metadata.version("transformers")
        except metadata.PackageNotFoundError:
            transformers_version = None
        payload: dict[str, Any] = {
            "implementation": "awnphen.mask2former_segmentation_adapter_v1",
            "architecture": self.architecture_name,
            "transformers_version": transformers_version,
            "model_input_size": self.input_size,
            "label_map": {"0": 0, "1": 1},
            "input_color": "BGR->RGB",
            "mask_coordinate_space": "original_input_tile",
            "overlap_safe_binary_maps": True,
        }
        weight = self._checkpoint_weight()
        if self.checkpoint_dir is not None:
            payload["checkpoint_dir"] = str(self.checkpoint_dir)
        if weight is not None:
            payload["checkpoint_weight"] = str(weight)
            payload["checkpoint_sha256"] = sha256_file(weight)
        return payload

    def predict_tile(
        self,
        image_bgr: np.ndarray,
        *,
        confidence: float,
    ) -> tuple[InstanceMaskPrediction, ...]:
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError("expected HxWx3 BGR image")

        height, width = image_bgr.shape[:2]
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        inputs = self.processor(
            images=rgb,
            return_tensors="pt",
            do_resize=False,
        )
        device = next(self.model.parameters()).device
        inputs = {
            key: value.to(device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }

        self.model.eval()
        with torch.no_grad():
            outputs = self.model(**inputs)
        post = self.processor.post_process_instance_segmentation(
            outputs,
            threshold=confidence,
            mask_threshold=0.5,
            target_sizes=[(height, width)],
            return_binary_maps=True,
        )[0]

        segmentation = post.get("segmentation")
        segments_info = list(post.get("segments_info", ()))
        if segmentation is None or not segments_info:
            return ()

        masks = segmentation.detach().cpu().numpy()
        if masks.ndim == 2:
            masks = masks[None, ...]
        if len(masks) != len(segments_info):
            raise RuntimeError(
                "Mask2Former binary-map count does not match segments_info: "
                f"{len(masks)} vs {len(segments_info)}"
            )

        result: list[InstanceMaskPrediction] = []
        for mask, info in zip(masks, segments_info):
            class_id = int(info["label_id"])
            if class_id not in (0, 1):
                continue
            score = float(info["score"])
            if score < confidence:
                continue
            binary = np.asarray(mask) > 0
            ys, xs = np.nonzero(binary)
            if not len(xs):
                continue
            box = (
                float(xs.min()),
                float(ys.min()),
                float(xs.max() + 1),
                float(ys.max() + 1),
            )
            result.append(
                InstanceMaskPrediction(
                    class_id=class_id,
                    confidence=score,
                    mask=binary.astype(np.uint8),
                    box_xyxy=box,
                )
            )
        return tuple(result)


__all__ = ["Mask2FormerSegmentationAdapter"]
