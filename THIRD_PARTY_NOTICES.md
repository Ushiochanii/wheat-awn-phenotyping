# Third-party notices

AwnPhen is distributed under the GNU Affero General Public License v3.0 (AGPL-3.0). Some components and dependencies retain their own copyright notices and licenses.

## Ultralytics YOLO

AwnPhen uses the Ultralytics Python package at runtime and the canonical segmentation checkpoint was trained with Ultralytics YOLO11.

Ultralytics states that its YOLO software and trained models are provided under AGPL-3.0 by default unless covered by an applicable commercial license.

- Project: https://github.com/ultralytics/ultralytics
- Licensing information: https://www.ultralytics.com/license

The canonical AwnPhen checkpoint is distributed separately at:

- https://huggingface.co/anpanchanii/awnphen-yolo11n

## Lucide Icons

Awn Studio contains adapted SVG paths from Lucide Icons v0.468.0 (`hand`, `mouse-pointer-2`, `scan`, `undo-2`, and `redo-2`).

Lucide is licensed under the ISC License. Copyright notices and the ISC license text are retained in `app/awn_studio/THIRD_PARTY_NOTICES.md`.

- Source: https://github.com/lucide-icons/lucide

## Python dependencies

Runtime dependencies such as NumPy, SciPy, scikit-image, OpenCV, Pillow, Shapely, PyYAML, Hugging Face Hub, PyTorch/TorchVision, Transformers, RF-DETR, and their transitive dependencies are not relicensed by Awn Studio. Their respective upstream licenses continue to apply.
