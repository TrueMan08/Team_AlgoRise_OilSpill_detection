# OilTrace ML Service

Sentinel-1 VV+VH GeoTIFF in; georeferenced oil-slick polygons out. The ML
component has advanced beyond the original MVP detector: it now combines a
pretrained segmentation model, scene context and a train-fitted component
verifier. The reported operating points were selected on the held-out
validation split. The 450-scene Part III test set remains sealed.

## Current model comparison

| Run / system | Architecture | Pixel Dice | Object precision | Recall, slicks ≥10 ha | Role |
|---|---|---:|---:|---:|---|
| E5_focal + original rules | from-scratch U-Net | 0.350 | 0.474 | 0.667 | MVP baseline |
| X1c_r34_strict | SMP U-Net, ResNet-34 | 0.679 | — | — | Best validated segmentation checkpoint before postprocessing |
| X1c + C3 + V1 | X1c segmenter + ResNet-34 scene context + component verifier | 0.679* | **0.817** | **0.812** | Current operational validation champion |
| X2_smp_dlv3p_r34 + C3 | SMP DeepLabV3+, ResNet-34 + C3 gate | **0.736** | 0.812 | 0.800 | Highest pixel Dice challenger |

The X1c + C3 + V1 operating point improves object precision by **34.3
percentage points** and large-slick recall by **14.5 points** over the E5
baseline. Its verifier threshold is 0.5, with segmentation threshold 0.8.
A recall-focused setting reaches 0.848 recall at 0.676 precision (verifier
threshold 0.1). X2's pixel Dice is measured at threshold 0.39; the X2+C3
object metrics use segmentation threshold 0.39 and gate threshold 0.4.

\* Pixel Dice uses the model's own validation-swept threshold (0.915 for
X1c). Object metrics use their stated component operating points, so a row
does not imply the pixel and object metrics were measured at the same
threshold. All figures are validation-only, on 4,362 held-out patches. They
are not a sealed-test score or a production guarantee. The C3 classifier
macro-accuracy is 0.771.

## What is included

| Path | Contents |
|---|---|
| `service/` | Complete FastAPI + Docker inference service, runtime model code and X1c/C3/V1 checkpoints |
| `runs/` | Compact training histories, checkpoint manifests and V1 evaluation report |
| `docs/` | API reference and judge card |

The service checkpoint files are under `service/data/models/` and tracked
with Git LFS. Run `git lfs install` and `git lfs pull` after cloning so the
binary checkpoint files are available to Docker. The service package includes
the runtime code and model artifacts required for inference.

## Run the service locally

From the repository root:

```sh
docker build -t oiltrace-ml ./ML-service/service
docker run --rm -p 7860:7860 oiltrace-ml
```

The API provides `GET /health`, `GET /detect/demo`, `GET /demo/scene`, and
`POST /detect`. Upload a two-band, georeferenced Sentinel-1 GeoTIFF as the
multipart `file` field. The service uses the calibrated segmentation
threshold 0.8 and V1 score threshold 0.5; a different segmentation threshold
is rejected because it would invalidate the verifier calibration.

## Training and evaluation record

- X1c: strict 1:1 balancing, paired-interleave sampling and reduced encoder
  learning rate; best checkpoint epoch 9.
- C3: pretrained ResNet-34 scene classifier; validation macro-accuracy 0.771.
- V1: logistic component verifier fitted on training components only and
  measured on held-out validation components.
- X2: DeepLabV3+ / ResNet-34; best checkpoint epoch 13, early-stopped after
  epoch 19 under the configured patience rule.
- The validation shards are the fixed 4,362-patch leaderboard. Part III
  remains sealed for the one-time final test evaluation.

Each `runs/<experiment>/` folder contains the training history and the
manifest where available. See [`runs/V1_verifier/report.json`](runs/V1_verifier/report.json)
for the verifier operating-point sweep and [`service/README.md`](service/README.md)
for the inference interface.

## Credits

Training imagery: Trujillo-Acatitla et al., Zenodo record 13761290, CC-BY 4.0.
The model pipeline was trained and evaluated by Team AlgoRise for SIH 2026,
problem SIH26143.
