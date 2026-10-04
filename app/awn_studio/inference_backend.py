  1 | """Awn Studio model library plus optional user-added local checkpoints."""
  2 | from __future__ import annotations
  3 | 
  4 | from dataclasses import dataclass
  5 | from importlib.util import find_spec
  6 | from pathlib import Path
  7 | import hashlib
  8 | import json
  9 | import os
 10 | import re
 11 | import sys
 12 | 
 13 | ROOT = Path(__file__).resolve().parents[2]
 14 | sys.path.insert(0, str(ROOT / "src"))
 15 | 
 16 | DEFAULT_MODEL_ID = "yolo11n-canonical"
 17 | OFFICIAL_MODEL_REPO = "anpanchanii/awn-studio-model-zoo"
 18 | OFFICIAL_MODELS_DIR = Path(
 19 |     os.environ.get(
 20 |         "AWN_STUDIO_OFFICIAL_MODELS",
 21 |         Path.home() / ".cache" / "awn-studio" / "models",
 22 |     )
 23 | ).expanduser()
 24 | CUSTOM_MODELS_PATH = Path(
 25 |     os.environ.get(
 26 |         "AWN_STUDIO_CUSTOM_MODELS",
 27 |         Path.home() / ".config" / "awn-studio" / "models.json",
 28 |     )
 29 | ).expanduser()
 30 | 
 31 | SUPPORTED_ADAPTERS = {
 32 |     "ultralytics_yolo_seg": "Ultralytics YOLO segmentation",
 33 |     "torchvision_maskrcnn": "Torchvision Mask R-CNN",
 34 |     "mask2former_segmentation": "Mask2Former segmentation",
 35 |     "rfdetr_segmentation": "RF-DETR segmentation",
 36 | }
 37 | 
 38 | _RUNTIME_REQUIREMENTS = {
 39 |     "ultralytics_yolo_seg": ("ultralytics", None),
 40 |     "torchvision_maskrcnn": ("torchvision", None),
 41 |     "mask2former_segmentation": (
 42 |         "transformers",
 43 |         'Install the optional runtime with: python -m pip install -e ".[mask2former]"',
 44 |     ),
 45 |     "rfdetr_segmentation": (
 46 |         "rfdetr",
 47 |         'Install the optional runtime with: python -m pip install -e ".[rfdetr]"',
 48 |     ),
 49 | }
 50 | 
 51 | 
 52 | @dataclass(frozen=True)
 53 | class ModelSpec:
 54 |     id: str
 55 |     name: str
 56 |     weights: Path
 57 |     adapter: str = "ultralytics_yolo_seg"
 58 |     description: str = ""
 59 |     custom: bool = False
 60 |     official: bool = False
 61 |     remote_path: str | None = None
 62 |     sha256: str | None = None
 63 |     companion_files: tuple[str, ...] = ()
 64 |     size_bytes: int | None = None
 65 |     positioning: str = ""
 66 |     quality_note: str = ""
 67 |     page_seconds: float | None = None
 68 | 
 69 |     @property
 70 |     def installed(self) -> bool:
 71 |         if not self.weights.is_file():
 72 |             return False
 73 |         return all(
 74 |             (OFFICIAL_MODELS_DIR / path).is_file()
 75 |             for path in self.companion_files
 76 |         )
 77 | 
 78 |     @property
 79 |     def runtime_ready(self) -> bool:
 80 |         module, _ = _RUNTIME_REQUIREMENTS.get(self.adapter, (None, None))
 81 |         return module is None or find_spec(module) is not None
 82 | 
 83 |     @property
 84 |     def runtime_hint(self) -> str | None:
 85 |         if self.runtime_ready:
 86 |             return None
 87 |         _, hint = _RUNTIME_REQUIREMENTS.get(self.adapter, (None, None))
 88 |         return hint or f"Missing runtime for {self.adapter}."
 89 | 
 90 |     @property
 91 |     def available(self) -> bool:
 92 |         return self.installed and self.runtime_ready
 93 | 
 94 |     def public(self, *, default: bool = False) -> dict:
 95 |         return {
 96 |             "id": self.id,
 97 |             "name": self.name,
 98 |             "adapter": self.adapter,
 99 |             "description": self.description,
100 |             "available": self.available,
101 |             "installed": self.installed,
102 |             "runtime_ready": self.runtime_ready,
103 |             "runtime_hint": self.runtime_hint,
104 |             "default": default,
105 |             "custom": self.custom,
106 |             "official": self.official,
107 |             "downloadable": bool(self.official and self.remote_path),
108 |             "size_bytes": self.size_bytes,
109 |             "positioning": self.positioning,
110 |             "quality_note": self.quality_note,
111 |             "page_seconds": self.page_seconds,
112 |             "weights": str(self.weights) if self.custom else None,
113 |         }
114 | 
115 | 
116 | def _weights_path() -> Path:
117 |     configured = os.environ.get("AWNPHEN_WEIGHTS")
118 |     if configured:
119 |         return Path(configured).expanduser().resolve()
120 |     try:
121 |         from awnphen.model import resolve_weights
122 |         return resolve_weights()
123 |     except RuntimeError:
124 |         return ROOT / "models" / "best.pt"
125 | 
126 | 
127 | def _official_specs() -> tuple[ModelSpec, ...]:
128 |     return (
129 |         ModelSpec(
130 |             id=DEFAULT_MODEL_ID,
131 |             name="YOLO11N · Default",
132 |             weights=_weights_path(),
133 |             description="Fastest and recommended default for routine Awn Studio use.",
134 |             official=True,
135 |             positioning="Default / fastest",
136 |             quality_note="Strong overall default; validation MAE 1.79 mm.",
137 |             page_seconds=2.28600167890545,
138 |             size_bytes=6006116,
139 |         ),
140 |         ModelSpec(
141 |             id="yolo11m-official",
142 |             name="YOLO11M · Accuracy-oriented",
143 |             weights=OFFICIAL_MODELS_DIR / "yolo11m.pt",
144 |             description="Heavier YOLO alternative with the lowest YOLO11 validation length MAE.",
145 |             official=True,
146 |             remote_path="yolo11m.pt",
147 |             sha256="05d8bee109cb8b71310eb6ef2a80371570a76bd09db1bcf902f84392451081e9",
148 |             size_bytes=45159158,
149 |             positioning="Accuracy-oriented YOLO",
150 |             quality_note="Lowest YOLO11 validation MAE: 1.68 mm.",
151 |         ),
152 |         ModelSpec(
153 |             id="yolo11x-official",
154 |             name="YOLO11X · Extra large",
155 |             weights=OFFICIAL_MODELS_DIR / "yolo11x.pt",
156 |             description="Extra-large YOLO alternative; larger is not consistently better.",
157 |             official=True,
158 |             remote_path="yolo11x.pt",
159 |             sha256="69ed75d44e546dda892b37d80d77b897a108fed257c75a9c6e9ea26f6cc09ae1",
160 |             size_bytes=124774241,
161 |             positioning="Extra-large YOLO",
162 |             quality_note="Exploratory option; larger is not consistently better.",
163 |         ),
164 |         ModelSpec(
165 |             id="maskrcnn-r50-fpn-v2",
166 |             name="Mask R-CNN R50-FPN V2 · Classical baseline",
167 |             weights=OFFICIAL_MODELS_DIR / "maskrcnn-r50-fpn-v2.pt",
168 |             adapter="torchvision_maskrcnn",
169 |             description="Classical two-stage CNN instance-segmentation baseline.",
170 |             official=True,
171 |             remote_path="maskrcnn-r50-fpn-v2.pt",
172 |             sha256="855309a843a8120498cb0b78d1c4535066a09b2b16926af0476f452931284fbc",
173 |             size_bytes=367514968,
174 |             positioning="Classical CNN baseline",
175 |             quality_note="Complete-awn recall 62.3%.",
176 |             page_seconds=4.415757554001175,
177 |         ),
178 |         ModelSpec(
179 |             id="rfdetr-seg-xl",
180 |             name="RF-DETR Seg XL · Transformer",
181 |             weights=OFFICIAL_MODELS_DIR / "rfdetr-seg-xl.pth",
182 |             adapter="rfdetr_segmentation",
183 |             description="Modern transformer segmentation model with low fragmentation.",
184 |             official=True,
185 |             remote_path="rfdetr-seg-xl.pth",
186 |             sha256="f1b79ad06adaca646fd83e62317f38cbec61df9bce0a87a626944322de10dfe8",
187 |             size_bytes=151531795,
188 |             positioning="Modern transformer detector",
189 |             quality_note="Complete-awn recall 81.6%; low fragmentation.",
190 |             page_seconds=12.835252746008337,
191 |         ),
192 |         ModelSpec(
193 |             id="mask2former-swin-l",
194 |             name="Mask2Former Swin-L · Highest quality",
195 |             weights=OFFICIAL_MODELS_DIR / "mask2former-swin-l" / "model.safetensors",
196 |             adapter="mask2former_segmentation",
197 |             description="Highest-quality structural segmentation option in the maintained comparison.",
198 |             official=True,
199 |             remote_path="mask2former-swin-l/model.safetensors",
200 |             companion_files=(
201 |                 "mask2former-swin-l/config.json",
202 |                 "mask2former-swin-l/preprocessor_config.json",
203 |             ),
204 |             sha256="a69ed458370c01040de51aebf81ac4c475c2db2f2310a03406b142b27fc3148c",
205 |             size_bytes=866104120,
206 |             positioning="Highest-quality structural model",
207 |             quality_note="Complete-awn recall 83.2%; best structural coverage in the maintained comparison.",
208 |             page_seconds=32.96233680099249,
209 |         ),
210 |     )
211 | 
212 | 
213 | def _normalize_model_path(value: str | Path) -> Path:
214 |     raw = str(value).strip().strip('"').replace("\\", "/")
215 |     raw = re.sub(r"/+", "/", raw)
216 |     match = re.match(r"^([A-Za-z]):/(.*)$", raw)
217 |     if match and Path("/mnt").is_dir():
218 |         drive, rest = match.groups()
219 |         raw = f"/mnt/{drive.lower()}/{rest}"
220 |     return Path(raw).expanduser().resolve()
221 | 
222 | 
223 | def _read_custom_models() -> list[dict]:
224 |     try:
225 |         data = json.loads(CUSTOM_MODELS_PATH.read_text(encoding="utf-8"))
226 |     except (FileNotFoundError, json.JSONDecodeError, OSError):
227 |         return []
228 |     return data if isinstance(data, list) else []
229 | 
230 | 
231 | def _write_custom_models(items: list[dict]) -> None:
232 |     CUSTOM_MODELS_PATH.parent.mkdir(parents=True, exist_ok=True)
233 |     CUSTOM_MODELS_PATH.write_text(
234 |         json.dumps(items, ensure_ascii=False, indent=2),
235 |         encoding="utf-8",
236 |     )
237 | 
238 | 
239 | def _custom_specs() -> tuple[ModelSpec, ...]:
240 |     specs = []
241 |     for item in _read_custom_models():
242 |         try:
243 |             adapter = str(item.get("adapter") or "ultralytics_yolo_seg")
244 |             if adapter not in SUPPORTED_ADAPTERS:
245 |                 continue
246 |             specs.append(
247 |                 ModelSpec(
248 |                     id=str(item["id"]),
249 |                     name=str(item["name"]),
250 |                     weights=_normalize_model_path(item["weights"]),
251 |                     adapter=adapter,
252 |                     description=str(item.get("description") or "User-added local model."),
253 |                     custom=True,
254 |                 )
255 |             )
256 |         except Exception:
257 |             continue
258 |     return tuple(specs)
259 | 
260 | 
261 | MODEL_REGISTRY: dict[str, ModelSpec] = {}
262 | 
263 | 
264 | def refresh_model_registry() -> dict[str, ModelSpec]:
265 |     registry = {spec.id: spec for spec in _official_specs()}
266 |     for spec in _custom_specs():
267 |         if spec.id not in registry:
268 |             registry[spec.id] = spec
269 |     MODEL_REGISTRY.clear()
270 |     MODEL_REGISTRY.update(registry)
271 |     return MODEL_REGISTRY
272 | 
273 | 
274 | def model_catalog() -> list[dict]:
275 |     refresh_model_registry()
276 |     return [
277 |         spec.public(default=spec.id == DEFAULT_MODEL_ID)
278 |         for spec in MODEL_REGISTRY.values()
279 |     ]
280 | 
281 | 
282 | def model_spec(model_id: str | None = None) -> ModelSpec:
283 |     refresh_model_registry()
284 |     requested = model_id or DEFAULT_MODEL_ID
285 |     try:
286 |         return MODEL_REGISTRY[requested]
287 |     except KeyError as error:
288 |         raise ValueError(f"Unknown model: {requested}") from error
289 | 
290 | 
291 | def _verify_sha256(path: Path, expected: str | None) -> None:
292 |     if not expected:
293 |         return
294 |     actual = hashlib.sha256(path.read_bytes()).hexdigest()
295 |     if actual != expected:
296 |         try:
297 |             path.unlink()
298 |         except OSError:
299 |             pass
300 |         raise RuntimeError(
301 |             f"Checksum verification failed for {path.name}: expected {expected}, got {actual}"
302 |         )
303 | 
304 | 
305 | def install_official_model(model_id: str) -> ModelSpec:
306 |     spec = model_spec(model_id)
307 |     if not spec.official:
308 |         raise ValueError("Only models from the Awn Studio Model Zoo can be downloaded here.")
309 |     if spec.id == DEFAULT_MODEL_ID:
310 |         from awnphen.model import resolve_weights
311 |         path = resolve_weights()
312 |         _verify_sha256(path, "a7a5cf23bf5d35266e4fa6b1dc0244ee802026a381548bcd202f04b3ebf42097")
313 |         refresh_model_registry()
314 |         return model_spec(model_id)
315 |     if not spec.remote_path:
316 |         raise ValueError(f"No download is configured for {spec.name}.")
317 | 
318 |     from huggingface_hub import hf_hub_download
319 | 
320 |     OFFICIAL_MODELS_DIR.mkdir(parents=True, exist_ok=True)
321 |     primary = Path(
322 |         hf_hub_download(
323 |             repo_id=OFFICIAL_MODEL_REPO,
324 |             filename=spec.remote_path,
325 |             local_dir=OFFICIAL_MODELS_DIR,
326 |         )
327 |     )
328 |     _verify_sha256(primary, spec.sha256)
329 |     for filename in spec.companion_files:
330 |         hf_hub_download(
331 |             repo_id=OFFICIAL_MODEL_REPO,
332 |             filename=filename,
333 |             local_dir=OFFICIAL_MODELS_DIR,
334 |         )
335 |     refresh_model_registry()
336 |     return model_spec(model_id)
337 | 
338 | 
339 | def register_custom_model(
340 |     *,
341 |     name: str,
342 |     weights: str,
343 |     adapter: str = "ultralytics_yolo_seg",
344 |     description: str = "",
345 | ) -> ModelSpec:
346 |     name = str(name).strip()
347 |     if not name:
348 |         raise ValueError("Model name is required.")
349 |     adapter = str(adapter).strip()
350 |     if adapter not in SUPPORTED_ADAPTERS:
351 |         raise ValueError(f"Unsupported model adapter: {adapter}")
352 |     path = _normalize_model_path(weights)
353 |     digest = hashlib.sha1(f"{adapter}|{path}".encode()).hexdigest()[:10]
354 |     slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "model"
355 |     model_id = f"custom-{slug[:32]}-{digest}"
356 |     items = [item for item in _read_custom_models() if item.get("id") != model_id]
357 |     items.append(
358 |         {
359 |             "id": model_id,
360 |             "name": name,
361 |             "weights": str(path),
362 |             "adapter": adapter,
363 |             "description": str(description or ""),
364 |         }
365 |     )
366 |     _write_custom_models(items)
367 |     refresh_model_registry()
368 |     return MODEL_REGISTRY[model_id]
369 | 
370 | 
371 | def remove_custom_model(model_id: str) -> bool:
372 |     items = _read_custom_models()
373 |     kept = [item for item in items if item.get("id") != model_id]
374 |     if len(kept) == len(items):
375 |         return False
376 |     _write_custom_models(kept)
377 |     refresh_model_registry()
378 |     return True
379 | 
380 | 
381 | refresh_model_registry()
382 | DEFAULT_MODEL = MODEL_REGISTRY[DEFAULT_MODEL_ID]
383 | MODEL_NAME = DEFAULT_MODEL.name
384 | WEIGHTS = DEFAULT_MODEL.weights
385 | 
386 | 
387 | class Engine:
388 |     """Lazy single-active-model cache used by Awn Studio."""
389 | 
390 |     def __init__(self, device="cpu", *, physical_closeout_runner=None, reconciliation_runner=None):
391 |         self.device = device
392 |         self.physical_closeout_runner = physical_closeout_runner
393 |         self.reconciliation_runner = reconciliation_runner
394 |         self.model = None
395 |         self.model_id = None
396 |         self.loaded_weights = None
397 | 
398 |     def _torch_device(self) -> str:
399 |         value = str(self.device or "cpu")
400 |         if value == "cpu":
401 |             return "cpu"
402 |         if value.isdigit():
403 |             return f"cuda:{value}"
404 |         return value
405 | 
406 |     def _release_model(self) -> None:
407 |         model = self.model
408 |         self.model = None
409 |         self.model_id = None
410 |         self.loaded_weights = None
411 |         close = getattr(model, "close", None)
412 |         if callable(close):
413 |             close()
414 |         try:
415 |             import gc
416 |             import torch
417 |             gc.collect()
418 |             if torch.cuda.is_available():
419 |                 torch.cuda.empty_cache()
420 |         except Exception:
421 |             pass
422 | 
423 |     def _load_ultralytics(self, spec: ModelSpec):
424 |         from ultralytics import YOLO
425 |         model = YOLO(str(spec.weights))
426 |         if dict(model.names) != {0: "awn", 1: "spikelet"}:
427 |             raise ValueError(f"Model class mapping mismatch: {model.names}")
428 |         return model
429 | 
430 |     def _load_maskrcnn(self, spec: ModelSpec):
431 |         import torch
432 |         from torchvision.models.detection import maskrcnn_resnet50_fpn_v2
433 |         from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
434 |         from torchvision.models.detection.mask_rcnn import MaskRCNNPredictor
435 |         from awnphen.modeling.inference.torchvision_maskrcnn import TorchvisionMaskRCNNAdapter
436 | 
437 |         payload = torch.load(spec.weights, map_location="cpu", weights_only=True)
438 |         config = dict(payload.get("config") or {})
439 |         model_cfg = dict(config.get("model") or {})
440 |         proposal = dict(model_cfg.get("proposal_budget") or {})
441 |         num_classes = int(model_cfg.get("num_classes_with_background", 3))
442 |         model = maskrcnn_resnet50_fpn_v2(
443 |             weights=None,
444 |             weights_backbone=None,
445 |             min_size=int(model_cfg.get("min_size", 640)),
446 |             max_size=int(model_cfg.get("max_size", 640)),
447 |             rpn_pre_nms_top_n_train=int(proposal.get("rpn_pre_nms_top_n_train", 2000)),
448 |             rpn_post_nms_top_n_train=int(proposal.get("rpn_post_nms_top_n_train", 2000)),
449 |             rpn_pre_nms_top_n_test=int(proposal.get("rpn_pre_nms_top_n_test", 1000)),
450 |             rpn_post_nms_top_n_test=int(proposal.get("rpn_post_nms_top_n_test", 1000)),
451 |             box_batch_size_per_image=int(proposal.get("box_batch_size_per_image", 512)),
452 |             box_detections_per_img=int(proposal.get("detections_per_img", 100)),
453 |         )
454 |         box_features = model.roi_heads.box_predictor.cls_score.in_features
455 |         model.roi_heads.box_predictor = FastRCNNPredictor(box_features, num_classes)
456 |         mask_features = model.roi_heads.mask_predictor.conv5_mask.in_channels
457 |         model.roi_heads.mask_predictor = MaskRCNNPredictor(mask_features, 256, num_classes)
458 |         model.load_state_dict(payload["model"], strict=True)
459 |         return TorchvisionMaskRCNNAdapter(
460 |             model=model,
461 |             device=torch.device(self._torch_device()),
462 |             input_size=640,
463 |             mask_threshold=0.5,
464 |             checkpoint_path=spec.weights,
465 |         )
466 | 
467 |     def _load_mask2former(self, spec: ModelSpec):
468 |         import torch
469 |         from transformers import AutoImageProcessor, Mask2FormerForUniversalSegmentation
470 |         from awnphen.modeling.inference.mask2former_segmentation import Mask2FormerSegmentationAdapter
471 | 
472 |         checkpoint_dir = spec.weights.parent
473 |         processor = AutoImageProcessor.from_pretrained(checkpoint_dir, local_files_only=True)
474 |         model = Mask2FormerForUniversalSegmentation.from_pretrained(
475 |             checkpoint_dir,
476 |             local_files_only=True,
477 |         )
478 |         model.to(torch.device(self._torch_device())).eval()
479 |         return Mask2FormerSegmentationAdapter(
480 |             model=model,
481 |             processor=processor,
482 |             checkpoint_dir=checkpoint_dir,
483 |             input_size=640,
484 |         )
485 | 
486 |     def _load_rfdetr(self, spec: ModelSpec):
487 |         from rfdetr import RFDETRSegXLarge
488 |         from awnphen.modeling.inference.rfdetr_segmentation import RFDETRSegmentationAdapter
489 | 
490 |         device = self._torch_device()
491 |         if device.startswith("cuda:"):
492 |             device = "cuda"
493 |         wrapper = RFDETRSegXLarge.from_checkpoint(
494 |             spec.weights,
495 |             device=device,
496 |             trust_checkpoint=True,
497 |         )
498 |         return RFDETRSegmentationAdapter(
499 |             model=wrapper,
500 |             input_size=624,
501 |             checkpoint_path=spec.weights,
502 |         )
503 | 
504 |     def _load_model(self, spec: ModelSpec):
505 |         if not spec.installed:
506 |             raise FileNotFoundError(
507 |                 f"{spec.name} is not downloaded yet. Download it from Settings → Measurement."
508 |             )
509 |         if not spec.runtime_ready:
510 |             raise RuntimeError(spec.runtime_hint or f"Runtime for {spec.name} is not installed.")
511 |         if (
512 |             self.model is not None
513 |             and self.model_id == spec.id
514 |             and self.loaded_weights == spec.weights
515 |         ):
516 |             return self.model
517 |         if self.model is not None:
518 |             self._release_model()
519 | 
520 |         loaders = {
521 |             "ultralytics_yolo_seg": self._load_ultralytics,
522 |             "torchvision_maskrcnn": self._load_maskrcnn,
523 |             "mask2former_segmentation": self._load_mask2former,
524 |             "rfdetr_segmentation": self._load_rfdetr,
525 |         }
526 |         model = loaders[spec.adapter](spec)
527 |         self.model = model
528 |         self.model_id = spec.id
529 |         self.loaded_weights = spec.weights
530 |         return model
531 | 
532 |     def preload(self, model_id=None):
533 |         spec = model_spec(model_id)
534 |         self._load_model(spec)
535 |         return spec
536 | 
537 |     def run(self, source, output, progress, *, mm_per_px, model_id=None):
538 |         from canonical_backend import run_canonical
539 |         spec = model_spec(model_id)
540 |         progress(f"Loading {spec.name}…", 0, stage="loading")
541 |         model = self._load_model(spec)
542 |         return run_canonical(
543 |             source=source,
544 |             output=output,
545 |             model=model,
546 |             weights=spec.weights,
547 |             model_name=spec.name,
548 |             model_id=spec.id,
549 |             device=self.device,
550 |             mm_per_px=mm_per_px,
551 |             progress=progress,
552 |             physical_closeout_runner=self.physical_closeout_runner,
553 |             reconciliation_runner=self.reconciliation_runner,
554 |         )
555 | 
556 | 
557 | __all__ = [
558 |     "DEFAULT_MODEL",
559 |     "DEFAULT_MODEL_ID",
560 |     "Engine",
561 |     "MODEL_NAME",
562 |     "MODEL_REGISTRY",
563 |     "ModelSpec",
564 |     "OFFICIAL_MODEL_REPO",
565 |     "ROOT",
566 |     "SUPPORTED_ADAPTERS",
567 |     "WEIGHTS",
568 |     "install_official_model",
569 |     "model_catalog",
570 |     "model_spec",
571 |     "register_custom_model",
572 |     "remove_custom_model",
573 |     "refresh_model_registry",
574 | ]
575 | 