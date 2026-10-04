<p align="center">
  <img src="app/awn_studio/assets/brand/awn-studio-lockup.svg" alt="Awn Studio" width="520">
</p>

<p align="center">
  <strong>Semi-automated wheat awn length measurement from digitized spikelet images.</strong>
</p>

Awn Studio is a semi-automated platform for measuring wheat awn length from digitized spikelet images, combining automatic image analysis with human review.

---

## 🌾 From wheat spike to measurement

Awn Studio measures the long, bristle-like **awns** that extend from wheat spikelets. Before analysis, the plant material is prepared as an organized digital image of detached spikelets.

<p align="center">
  <img src="docs/assets/readme/sample-preparation-cropped.png" alt="From wheat spike to measurement" width="920">
</p>

The resulting spikelet pages provide a consistent digital format for measurement, while the same material can also be measured manually to create reference data for validation.

---

## 💡 Why Awn Studio?

Awn length is a widely studied cereal phenotype, and awn morphology is frequently examined in genetics, domestication, adaptation, and agronomic research. Reliable length measurements therefore matter, especially when experiments involve many accessions or large mapping populations.

Traditionally, awns are measured either directly with a ruler or manually from digital images in tools such as ImageJ. Direct ruler measurements are quick for a few samples, but curved and delicate awns are difficult to align accurately, and handling the material can distort or damage the structure being measured. Image-based manual tracing avoids some of those problems, but it still requires a person to trace and measure one awn at a time.

<p align="center">
  <img src="docs/assets/readme/why-awn-studio-cropped.png" alt="Conventional manual awn measurement workflows" width="920">
</p>

At small scale, both approaches are manageable. At larger scale, however, the same repetitive operation is performed hundreds or thousands of times, making the measurement step both time-consuming and difficult to standardize.

> **Why I built Awn Studio**  
> In one phenotyping experiment, I manually measured awns from more than 500 accessions, covering nearly 5,000 individual awn instances. The samples had already been digitized, yet tracing and measuring the awns one by one in ImageJ still took more than 100 hours and over two weeks of work. That experience made the bottleneck very clear: the measurement step itself needed to become much faster.

Awn Studio grew out of that problem: automate the repetitive part of awn measurement, improve consistency, and still keep the result visible and editable when human judgment is needed.

---

## ✨ What can Awn Studio do?

A typical workflow starts with a page of wheat spikelets and ends with reviewed, exportable awn-length measurements.

### Automatically detect and measure awns

Awn Studio identifies spikelets and awn evidence, reconstructs a representative awn path for each spikelet, and converts that path into a calibrated length measurement.

<p align="center">
  <img src="docs/assets/readme/automatic-measurement.gif" alt="Awn Studio automatic measurement demo" width="920">
</p>

### Review and correct the result

Automatic results remain editable. Users can inspect each spikelet, adjust the awn path, add a missing awn, or remove an incorrect path before accepting the measurement.

<p align="center">
  <img src="docs/assets/readme/manual-correction.gif" alt="Awn Studio manual correction demo" width="920">
</p>

### Export phenotype measurements

Reviewed measurements can be exported for downstream analysis instead of remaining trapped inside the visualization interface.

<p align="center">
  <img src="docs/assets/readme/export-results.gif" alt="Awn Studio export results demo" width="920">
</p>

---

## ⚙️ How Awn Studio works

Awn Studio does not treat raw segmentation masks as final measurements. The model first provides visual evidence; the pipeline then turns fragmented predictions into a measurable awn path.

<p align="center">
  <img src="docs/assets/readme/pipeline-principle.gif" alt="Awn Studio pipeline from segmentation evidence through awn reconstruction to calibrated measurement" width="920">
</p>

<p align="center"><sub>Image recognition → awn reconstruction → centerline extraction → calibrated measurement.</sub></p>

### 1. Image recognition

An instance-segmentation model identifies **awns** and **spikelets** in the input image. The predicted masks provide the visual evidence used by the following reconstruction steps.

### 2. Structural reconstruction

Raw predictions are treated as image evidence rather than finished objects. Compatible fragments are associated with nearby spikelets and progressively assembled into candidate awn structures. One representative awn is then selected for each spikelet.

### 3. Centerline extraction

The selected awn structure is converted into a centerline that provides the geometric path for normalization and length measurement, rather than measuring directly from the reconstructed mask.

### 4. Physical measurement

The centerline is normalized at the spikelet base, simplified where needed for stable geometry, and converted from pixels to millimetres using image calibration. Automatic calibration is used only when its quality checks pass; otherwise an explicit manual calibration can be supplied.

---

## 🚀 Getting started

You only need **Python 3.10+** and **Git**.

### 1. Install Awn Studio

Clone the repository and run the setup script:

```bash
git clone https://github.com/Ushiochanii/wheat-awn-phenotyping.git
cd wheat-awn-phenotyping
python scripts/bootstrap.py
```

The setup script creates an isolated environment, installs the required packages, downloads the default model, and checks that Awn Studio is ready to run.

### 2. Launch Awn Studio

After setup finishes, start the application:

```bash
# Windows
.venv\\Scripts\\awnphen.exe studio

# macOS / Linux
.venv/bin/awnphen studio
```

A browser window should open automatically at `http://127.0.0.1:8780/app/awn_studio/`.

From there, use the Web interface for calibration, model settings, measurement, review, editing, and export.

---

## Model and reproducibility

Awn Studio verifies downloaded Model Zoo checkpoints against their expected SHA-256 digests. The maintained default inference configuration uses 640 px model input with overlapping 640 px tiles and stride 320, and only one model is kept active at a time to avoid unnecessary GPU-memory use.

| Model | Complete-awn recall ↑ | Fragmentation rate ↓ | Structural coverage ↑ | Speed | Download size |
| --- | ---: | ---: | ---: | ---: | ---: |
| **YOLO11N** | 82.7% | 28.2% | 91.7% | **2.29 s/page** | **5.7 MB** |
| **RF-DETR Seg XL** | 81.6% | **17.6%** | 92.1% | 12.84 s/page | 144.5 MB |
| **Mask2Former Swin-L** | **83.2%** | 20.1% | **95.3%** | 32.96 s/page | **826.0 MB** |

All three structural metrics were evaluated on the same held-out **Validation11** benchmark (11 pages, 597 awn ground-truth instances and 464 spikelet ground-truth instances). Speed was measured with the same full-page timing protocol on an **AMD Radeon RX 7800 XT with ROCm**, using 640 × 640 tiles with stride 320. Download size is the actual checkpoint payload stored in the model library.

Large checkpoint files are hosted on Hugging Face rather than committed to the Git repository.

---

## Current limitations

Awn Studio is semi-automated rather than fully autonomous. Difficult images can still require human correction, particularly when awns are severely occluded, weakly visible, or confused with neighbouring structures.

Automatic physical calibration depends on a valid calibration grid or other reliable physical reference. When automatic calibration fails quality control, an explicit manual calibration is required.

The current maintained measurement contract uses one scalar millimetre-per-pixel value for a page.

---

## Citation

If you use Awn Studio in research, please cite the software metadata provided in [CITATION.cff](CITATION.cff).

---

## License

Awn Studio is distributed under the GNU Affero General Public License v3.0 (AGPL-3.0). The canonical YOLO11N checkpoint is also released under AGPL-3.0.

See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details.
