  1 | <p align="center">
  2 |   <img src="app/awn_studio/assets/brand/awn-studio-lockup.svg" alt="Awn Studio" width="520">
  3 | </p>
  4 | 
  5 | <p align="center">
  6 |   <strong>Semi-automated wheat awn length measurement from digitized spikelet images.</strong>
  7 | </p>
  8 | 
  9 | Awn Studio is a semi-automated platform for measuring wheat awn length from digitized spikelet images, combining automatic image analysis with human review.
 10 | 
 11 | ---
 12 | 
 13 | ## 🌾 From wheat spike to measurement
 14 | 
 15 | Awn Studio measures the long, bristle-like **awns** that extend from wheat spikelets. Before analysis, the plant material is prepared as an organized digital image of detached spikelets.
 16 | 
 17 | <p align="center">
 18 |   <img src="docs/assets/readme/sample-preparation-cropped.png" alt="From wheat spike to measurement" width="920">
 19 | </p>
 20 | 
 21 | The resulting spikelet pages provide a consistent digital format for measurement, while the same material can also be measured manually to create reference data for validation.
 22 | 
 23 | ---
 24 | 
 25 | ## 💡 Why Awn Studio?
 26 | 
 27 | Awn length is a widely studied cereal phenotype, and awn morphology is frequently examined in genetics, domestication, adaptation, and agronomic research. Reliable length measurements therefore matter, especially when experiments involve many accessions or large mapping populations.
 28 | 
 29 | Traditionally, awns are measured either directly with a ruler or manually from digital images in tools such as ImageJ. Direct ruler measurements are quick for a few samples, but curved and delicate awns are difficult to align accurately, and handling the material can distort or damage the structure being measured. Image-based manual tracing avoids some of those problems, but it still requires a person to trace and measure one awn at a time.
 30 | 
 31 | <p align="center">
 32 |   <img src="docs/assets/readme/why-awn-studio-cropped.png" alt="Conventional manual awn measurement workflows" width="920">
 33 | </p>
 34 | 
 35 | At small scale, both approaches are manageable. At larger scale, however, the same repetitive operation is performed hundreds or thousands of times, making the measurement step both time-consuming and difficult to standardize.
 36 | 
 37 | > **Why I built Awn Studio**  
 38 | > In one phenotyping experiment, I manually measured awns from more than 500 accessions, covering nearly 5,000 individual awn instances. The samples had already been digitized, yet tracing and measuring the awns one by one in ImageJ still took more than 100 hours and over two weeks of work. That experience made the bottleneck very clear: the measurement step itself needed to become much faster.
 39 | 
 40 | Awn Studio grew out of that problem: automate the repetitive part of awn measurement, improve consistency, and still keep the result visible and editable when human judgment is needed.
 41 | 
 42 | ---
 43 | 
 44 | ## ✨ What can Awn Studio do?
 45 | 
 46 | A typical workflow starts with a page of wheat spikelets and ends with reviewed, exportable awn-length measurements.
 47 | 
 48 | ### Automatically detect and measure awns
 49 | 
 50 | Awn Studio identifies spikelets and awn evidence, reconstructs a representative awn path for each spikelet, and converts that path into a calibrated length measurement.
 51 | 
 52 | <p align="center">
 53 |   <img src="docs/assets/readme/automatic-measurement.gif" alt="Awn Studio automatic measurement demo" width="920">
 54 | </p>
 55 | 
 56 | ### Review and correct the result
 57 | 
 58 | Automatic results remain editable. Users can inspect each spikelet, adjust the awn path, add a missing awn, or remove an incorrect path before accepting the measurement.
 59 | 
 60 | <p align="center">
 61 |   <img src="docs/assets/readme/manual-correction.gif" alt="Awn Studio manual correction demo" width="920">
 62 | </p>
 63 | 
 64 | ### Export phenotype measurements
 65 | 
 66 | Reviewed measurements can be exported for downstream analysis instead of remaining trapped inside the visualization interface.
 67 | 
 68 | <p align="center">
 69 |   <img src="docs/assets/readme/export-results.gif" alt="Awn Studio export results demo" width="920">
 70 | </p>
 71 | 
 72 | ---
 73 | 
 74 | ## ⚙️ How Awn Studio works
 75 | 
 76 | Awn Studio does not treat raw segmentation masks as final measurements. The model first provides visual evidence; the pipeline then turns that evidence into a biologically meaningful, measurable awn path.
 77 | 
 78 | <p align="center">
 79 |   <img src="docs/assets/readme/pipeline-principle.gif" alt="Awn Studio pipeline from segmentation evidence through awn reconstruction to calibrated measurement" width="920">
 80 | </p>
 81 | 
 82 | <p align="center"><sub>Image recognition → awn reconstruction → centerline extraction → calibrated measurement.</sub></p>
 83 | 
 84 | ### 1. Image recognition
 85 | 
 86 | An instance-segmentation model identifies **awns** and **spikelets** in the input image. The predicted masks provide the visual evidence used by the following reconstruction steps.
 87 | 
 88 | ### 2. Structural reconstruction
 89 | 
 90 | Raw predictions are treated as image evidence rather than finished objects. Compatible fragments are associated with nearby spikelets and progressively assembled into candidate awn structures. One representative awn is then selected for each spikelet.
 91 | 
 92 | ### 3. Centerline extraction
 93 | 
 94 | The selected awn structure is skeletonized into a one-pixel-wide centerline. This centerline provides the geometric path used by the downstream normalization and length-measurement steps, rather than measuring directly from the reconstructed mask.
 95 | 
 96 | ### 4. Physical measurement
 97 | 
 98 | The centerline is normalized at the spikelet base, simplified where needed for stable geometry, and converted from pixels to millimetres using image calibration. Automatic calibration is used only when its quality checks pass; otherwise an explicit manual calibration can be supplied.
 99 | 
100 | ---
101 | 
102 | ## Human-in-the-loop review
103 | 
104 | Awn Studio keeps the automatic result visible and editable rather than hiding the entire process behind a single number.
105 | 
106 | Core review actions include:
107 | 
108 | - inspect the original image, model evidence, candidate paths, and selected awn;
109 | - use **Review Suggested** to prioritize measurements that deserve attention;
110 | - drag or redraw an awn path, add a missing awn, or delete an incorrect path;
111 | - rerun measurements after changing the model or calibration;
112 | - save and reopen projects before exporting reviewed phenotype measurements.
113 | 
114 | This makes automation the first pass rather than the final authority.
115 | 
116 | ---
117 | 
118 | ## 🚀 Getting started
119 | 
120 | You only need **Python 3.10+** and **Git** for the standard setup. Start with the default CPU configuration first; once Awn Studio is running, you can add GPU acceleration or switch models later.
121 | 
122 | ### 1. Install Awn Studio
123 | 
124 | Clone the repository and run the setup script:
125 | 
126 | ```bash
127 | git clone https://github.com/Ushiochanii/wheat-awn-phenotyping.git
128 | cd wheat-awn-phenotyping
129 | python scripts/bootstrap.py
130 | ```
131 | 
132 | The setup script creates an isolated `.venv`, installs the required packages, prepares the default YOLO11N model, and checks that Awn Studio is ready to run.
133 | 
134 | Platform-specific wrappers are also available:
135 | 
136 | ```bash
137 | # Windows PowerShell
138 | powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
139 | 
140 | # macOS / Linux
141 | sh scripts/setup.sh
142 | ```
143 | 
144 | ### 2. Launch Awn Studio
145 | 
146 | After setup finishes, start the application:
147 | 
148 | ```bash
149 | # Windows
150 | .venv\Scripts\awnphen.exe studio
151 | 
152 | # macOS / Linux
153 | .venv/bin/awnphen studio
154 | ```
155 | 
156 | A browser window should open automatically at `http://127.0.0.1:8780/app/awn_studio/`.
157 | 
158 | From there, the normal workflow is:
159 | 
160 | **Import image → Calibrate → Run automatic measurement → Review or edit → Export**
161 | 
162 | The default model is downloaded automatically on first setup, so there is no model file to place manually.
163 | 
164 | ### 3. Open the example
165 | 
166 | Before importing your own images, you can try the complete workflow directly in Awn Studio.
167 | 
168 | Click **Open sample image** in the left sidebar. The bundled example opens with calibration already prepared. Then click **Run automatic measurement** to run the same segmentation, reconstruction, and measurement pipeline used for your own images.
169 | 
170 | You can inspect the result, switch display layers, edit the representative awn if needed, and try the export workflow without preparing any files first.
171 | 
172 | If you prefer command-line inference for your own image:
173 | 
174 | ```bash
175 | awnphen predict path/to/image.jpg --output runs/my-image
176 | ```
177 | 
178 | ### 4. Use a GPU
179 | 
180 | The standard setup uses CPU inference so that the first installation is predictable and works without CUDA or ROCm.
181 | 
182 | If your machine already has a compatible GPU environment, install the appropriate PyTorch build inside `.venv`, then keep that build when running the bootstrap script:
183 | 
184 | ```bash
185 | python scripts/bootstrap.py --keep-torch
186 | awnphen studio --device 0
187 | ```
188 | 
189 | The exact PyTorch installation depends on your NVIDIA CUDA or AMD ROCm environment.
190 | 
191 | ### 5. Choose a model
192 | 
193 | Awn Studio starts with **YOLO11N**, which is the fastest and recommended default. Other trained checkpoints are available from the [Awn Studio Model Zoo](https://huggingface.co/anpanchanii/awn-studio-model-zoo) and are downloaded only when you choose them.
194 | 
195 | Open **Settings → Measurement → Model library**. Models that are already usable show **Ready**; optional checkpoints show **Download**.
196 | 
197 | | Model | Complete-awn recall ↑ | Fragmentation rate ↓ | Structural coverage ↑ | Speed | Download size |
198 | | --- | ---: | ---: | ---: | ---: | ---: |
199 | | **YOLO11N** | **82.7%** | 28.2% | 91.7% | **2.29 s/page** | **5.7 MB** |
200 | | **YOLO11M** | 81.6% | 22.3% | 91.7% | — | 43.1 MB |
201 | | **YOLO11X** | — | — | — | — | 119.0 MB |
202 | | **Mask R-CNN R50-FPN V2** | 62.3% | 31.6% | 85.7% | 4.42 s/page | 350.5 MB |
203 | | **RF-DETR Seg XL** | 81.6% | **17.6%** | 92.1% | 12.84 s/page | 144.5 MB |
204 | | **Mask2Former Swin-L** | **83.2%** | 20.1% | **95.3%** | 32.96 s/page | **826.0 MB** |
205 | 
206 | The three structural metrics use the same complete-awn benchmark protocol. Speed values are shown only where the model was measured under the same full-page timing benchmark; missing values are intentionally left blank and will be filled after the pending benchmark run. Download size is the actual checkpoint payload stored in the model library.
207 | 
208 | The table is not a simple “larger is better” ranking. **YOLO11N** remains the practical default, **RF-DETR** reduces fragmentation, and **Mask2Former** provides the strongest structural coverage at a much higher storage and runtime cost.
209 | 
210 | YOLO11N, YOLO11M, YOLO11X, and Mask R-CNN work with the standard Awn Studio environment after their checkpoints are downloaded. RF-DETR and Mask2Former need their optional Python runtimes:
211 | 
212 | ```bash
213 | # install both advanced transformer runtimes
214 | python -m pip install -e ".[advanced-models]"
215 | 
216 | # or install only one
217 | python -m pip install -e ".[rfdetr]"
218 | python -m pip install -e ".[mask2former]"
219 | ```
220 | 
221 | #### Advanced · use your own checkpoint
222 | 
223 | Custom local models are still supported, but they are intentionally kept below the curated model library. Open **Settings → Measurement → Advanced · Custom local model** and register the local checkpoint path. For Ultralytics YOLO segmentation checkpoints, use class `0 = awn` and class `1 = spikelet`.
224 | 
225 | You can also launch Awn Studio with a specific compatible local checkpoint:
226 | 
227 | ```bash
228 | awnphen studio --weights path/to/best.pt
229 | ```
230 | 
231 | ### Advanced setup
232 | 
233 | If you prefer to manage the Python environment yourself instead of using the bootstrap script:
234 | 
235 | ```bash
236 | python -m venv .venv
237 | 
238 | # macOS / Linux
239 | source .venv/bin/activate
240 | 
241 | # Windows PowerShell
242 | # .venv\Scripts\Activate.ps1
243 | 
244 | # Windows / Linux CPU setup
245 | python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
246 | 
247 | python -m pip install -e .
248 | awnphen setup
249 | awnphen studio
250 | ```
251 | 
252 | `awnphen setup` checks the runtime, verifies the bundled Awn Studio files, prepares and checksum-verifies the default model, and reports the available compute device.
253 | 
254 | The optional spikelet scale-probe model is not required for normal measurement. If it is not configured, resolution preflight simply remains unassessed and the image is passed through unchanged.
255 | 
256 | > **Naming note:** Awn Studio is the public platform name. The Python package and command-line entry point remain `awnphen` for compatibility.
257 | 
258 | ---
259 | 
260 | ## Outputs
261 | 
262 | Awn Studio can produce:
263 | 
264 | - calibrated awn-length measurements;
265 | - reconstructed awn paths associated with spikelets;
266 | - editable project state for later review;
267 | - CSV phenotype exports;
268 | - reproducible run artifacts for inspection.
269 | 
270 | ---
271 | 
272 | ## Model and reproducibility
273 | 
274 | The default public checkpoint remains the pinned YOLO11N model at `anpanchanii/awnphen-yolo11n`. Optional curated checkpoints are published separately in the [Awn Studio Model Zoo](https://huggingface.co/anpanchanii/awn-studio-model-zoo), so larger models do not inflate the Git repository or the standard installation.
275 | 
276 | Awn Studio verifies downloaded Model Zoo checkpoints against their expected SHA-256 digests. The maintained default inference configuration uses 640 px model input with overlapping 640 px tiles and stride 320. Only one model is kept active at a time to avoid unnecessary GPU-memory use.
277 | 
278 | The public Git repository contains the maintained runtime and model adapters, while large checkpoint files remain on Hugging Face. Training history, raw research datasets, benchmark workspaces, publication drafts, archived algorithms, and caches remain outside the public source tree.
279 | 
280 | ---
281 | 
282 | ## Current limitations
283 | 
284 | Awn Studio is semi-automated rather than fully autonomous. Difficult images can still require human correction, particularly when awns are severely occluded, weakly visible, or confused with neighbouring structures.
285 | 
286 | Automatic physical calibration depends on a valid calibration grid or other reliable physical reference. When automatic calibration fails quality control, an explicit manual calibration is required.
287 | 
288 | The current maintained measurement contract uses one scalar millimetre-per-pixel value for a page.
289 | 
290 | ---
291 | 
292 | ## Developer notes
293 | 
294 | The public README is intended to be the main user-facing documentation. A short [architecture note](docs/architecture.md) is kept for contributors and future maintenance.
295 | 
296 | ---
297 | 
298 | ## Citation
299 | 
300 | If you use Awn Studio in research, please cite the software metadata provided in [CITATION.cff](CITATION.cff).
301 | 
302 | ---
303 | 
304 | ## License
305 | 
306 | Awn Studio is distributed under the GNU Affero General Public License v3.0 (AGPL-3.0). The canonical YOLO11N checkpoint is also released under AGPL-3.0.
307 | 
308 | See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details.
309 | 