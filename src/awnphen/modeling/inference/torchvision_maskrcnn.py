"""TorchVision Mask R-CNN adapter for the canonical awn evidence contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np
import torch
import torchvision

from awnphen.modeling.inference.instance_segmentation_adapter import (
    InstanceMaskPrediction,
)
from awnphen.phenotyping.detection.providers import sha256_file


@dataclass(slots=True)
class TorchvisionMaskRCNNAdapter:
    """Normalize TorchVision Mask R-CNN output to canonical awn/spikelet classes.

    TorchVision detection models reserve class 0 for background. The canonical
    project mapping is normally source labels 1->awn(0), 2->spikelet(1).
    """

    model: Any
    device: str | torch.device = "cuda"
    input_size: int = 640
    mask_threshold: float = 0.5
    label_map: Mapping[int, int] = field(
        default_factory=lambda: {1: 0, 2: 1}
    )
    checkpoint_path: Path | None = None

    def __post_init__(self) -> None:
        self.device = torch.device(self.device)
        self.input_size = int(self.input_size)
        self.mask_threshold = float(self.mask_threshold)
        self.label_map = {
            int(source): int(target)
            for source, target in dict(self.label_map).items()
        }
        if self.input_size <= 0:
            raise ValueError("input_size must be positive")
        if not 0.0 <= self.mask_threshold <= 1.0:
            raise ValueError("mask_threshold must be within [0, 1]")
        if any(target not in (0, 1) for target in self.label_map.values()):
            raise ValueError("label_map targets must use canonical classes 0/1")

        if self.checkpoint_path is not None:
            self.checkpoint_path = Path(self.checkpoint_path)
            if not self.checkpoint_path.is_file():
                raise FileNotFoundError(self.checkpoint_path)

        self.model.to(self.device)
        self.model.eval()

    @property
    def architecture_name(self) -> str:
        return "Mask R-CNN R50-FPN V2"

    @property
    def model_input_size(self) -> int:
        return self.input_size

    def provenance_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "implementation": "awnphen.torchvision_maskrcnn_adapter_v1",
            "architecture": self.architecture_name,
            "torch_version": torch.__version__,
            "torchvision_version": torchvision.__version__,
            "device": str(self.device),
            "model_input_size": self.input_size,
            "mask_threshold": self.mask_threshold,
            "label_map": {
                str(source): target
                for source, target in self.label_map.items()
            },
            "input_color": "BGR->RGB",
            "input_range": "[0,1]",
            "resize_policy": "TorchVision GeneralizedRCNNTransform",
            "proposal_budget": {
                "rpn_pre_nms_top_n_train": int(self.model.rpn._pre_nms_top_n["training"]),
                "rpn_post_nms_top_n_train": int(self.model.rpn._post_nms_top_n["training"]),
                "rpn_pre_nms_top_n_test": int(self.model.rpn._pre_nms_top_n["testing"]),
                "rpn_post_nms_top_n_test": int(self.model.rpn._post_nms_top_n["testing"]),
                "box_batch_size_per_image": int(self.model.roi_heads.fg_bg_sampler.batch_size_per_image),
                "detections_per_img": int(self.model.roi_heads.detections_per_img),
            },
        }
        if self.checkpoint_path is not None:
            payload["checkpoint"] = str(self.checkpoint_path)
            payload["checkpoint_sha256"] = sha256_file(self.checkpoint_path)
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

        # Prevent the model's internal score filter from silently truncating a
        # lower confidence sweep requested by the benchmark.
        if hasattr(self.model, "roi_heads") and hasattr(
            self.model.roi_heads, "score_thresh"
        ):
            self.model.roi_heads.score_thresh = confidence

        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        tensor = (
            torch.from_numpy(np.ascontiguousarray(rgb))
            .permute(2, 0, 1)
            .to(device=self.device, dtype=torch.float32)
            / 255.0
        )

        with torch.inference_mode():
            output = self.model([tensor])[0]

        boxes = output.get("boxes")
        scores = output.get("scores")
        labels = output.get("labels")
        masks = output.get("masks")
        if boxes is None or scores is None or labels is None or masks is None:
            raise RuntimeError(
                "Mask R-CNN output must contain boxes, scores, labels, masks"
            )

        boxes_np = boxes.detach().cpu().numpy()
        scores_np = scores.detach().cpu().numpy()
        labels_np = labels.detach().cpu().numpy()
        masks_np = masks.detach().cpu().numpy()
        if masks_np.ndim == 4 and masks_np.shape[1] == 1:
            masks_np = masks_np[:, 0]

        result: list[InstanceMaskPrediction] = []
        for box_xyxy, score, source_label, mask in zip(
            boxes_np,
            scores_np,
            labels_np,
            masks_np,
        ):
            if float(score) < confidence:
                continue
            canonical_class = self.label_map.get(int(source_label))
            if canonical_class is None:
                continue
            result.append(
                InstanceMaskPrediction(
                    class_id=canonical_class,
                    confidence=float(score),
                    mask=(np.asarray(mask) >= self.mask_threshold).astype(
                        np.uint8
                    ),
                    box_xyxy=tuple(float(value) for value in box_xyxy),
                )
            )
        return tuple(result)


__all__ = ["TorchvisionMaskRCNNAdapter"]
