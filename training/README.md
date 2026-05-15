# AEGIS-IMINT — YOLOv8 Military Vehicle Detector Training Guide

Complete guide to fine-tuning a YOLOv8 model on the xView satellite dataset for military vehicle detection.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Downloading the xView Dataset](#downloading-the-xview-dataset)
3. [Dataset Preparation](#dataset-preparation)
4. [Running Training](#running-training)
5. [Validation & Metrics](#validation--metrics)
6. [Deploying the Model](#deploying-the-model)
7. [Hardware Recommendations](#hardware-recommendations)
8. [Expected Training Times](#expected-training-times)
9. [mAP Targets](#map-targets)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

```bash
pip install ultralytics>=8.0 opencv-python-headless numpy requests
```

Python 3.9+ required. CUDA 11.8+ recommended for GPU training.

---

## Downloading the xView Dataset

xView is a publicly available satellite imagery dataset maintained by DIU (Defense Innovation Unit).

### Step 1 — Register and download

1. Go to https://xviewdataset.org and register for access.
2. Download the following files (~17 GB total):
   - `train_images.tgz` — satellite image chips (0.3 m GSD)
   - `train_labels/xView_train.geojson` — bounding box annotations
3. Extract:
   ```bash
   tar -xzf train_images.tgz -C /data/xview/
   ```

### Step 2 — Directory layout expected

```
/data/xview/
├── train_images/
│   ├── 1.tif
│   ├── 2.tif
│   └── ...
└── xView_train.geojson
```

### Alternative: DOTA dataset

If xView access is unavailable, the DOTA v2.0 dataset (https://captain-whu.github.io/DOTA) provides similar aerial vehicle annotations. Adapt `prepare_dataset.py` class mappings to DOTA's 18-class schema.

---

## Dataset Preparation

Run `prepare_dataset.py` to convert xView GeoJSON annotations to YOLOv8 format and split into train/val sets:

```bash
python training/prepare_dataset.py \
    --geojson /data/xview/xView_train.geojson \
    --images  /data/xview/train_images/ \
    --output  training/dataset/ \
    --val-split 0.2
```

### What it does

- Maps 60+ xView class IDs to 8 NATO-compatible categories (see table below)
- Converts polygon annotations to YOLO center-x, center-y, width, height format (normalized 0–1)
- Splits images 80/20 train/val (reproducible via `--seed`)
- Writes `dataset.yaml` for YOLOv8

### Class mapping

| ID | NATO Class       | Includes                                    |
|----|------------------|---------------------------------------------|
| 0  | ground_vehicle   | passenger cars, pickup trucks               |
| 1  | armored_vehicle  | military ground assets (annotate manually)  |
| 2  | air_asset        | fixed-wing aircraft, helicopters            |
| 3  | naval_asset      | ships, boats, ferries, barges               |
| 4  | engineering      | bulldozers, cranes, excavators              |
| 5  | logistics        | cargo/fuel trucks, buses                    |
| 6  | structure        | installations, storage tanks                |
| 7  | unknown          | unmapped xView classes                      |

### Expected output structure

```
training/dataset/
├── dataset.yaml
├── images/
│   ├── train/   (~3,200 images)
│   └── val/     (~800 images)
└── labels/
    ├── train/   (YOLO .txt per image)
    └── val/
```

---

## Running Training

### Full fine-tuning (recommended)

```bash
python training/train.py \
    --dataset training/dataset/dataset.yaml \
    --base-model yolov8m.pt \
    --epochs 100 \
    --batch 16 \
    --imgsz 640 \
    --device 0
```

### Larger model for higher accuracy

```bash
python training/train.py \
    --base-model yolov8l.pt \
    --batch 8 \
    --imgsz 1280 \
    --device 0
```

### CPU-only (testing/debugging)

```bash
python training/train.py \
    --base-model yolov8n.pt \
    --epochs 5 \
    --batch 4 \
    --device cpu
```

### Key training parameters explained

| Parameter      | Default  | Notes                                               |
|----------------|----------|-----------------------------------------------------|
| `--base-model` | yolov8m  | Pre-trained COCO weights as starting point          |
| `--epochs`     | 100      | Early stopping triggers after 20 stagnant epochs    |
| `--imgsz`      | 640      | Input resolution. 1280 improves small object recall |
| `--batch`      | 16       | Reduce if VRAM OOM                                  |
| `--freeze`     | 10       | Freeze backbone for first 10 epochs                 |

### Augmentation pipeline (aerial-optimized)

The training script applies augmentations tuned for overhead satellite imagery:

- **Rotation ±45°** — vehicles appear at any heading
- **Vertical + horizontal flip** — no canonical orientation from above
- **Mosaic (4-image)** — improves small object detection
- **HSV jitter** — handles sensor/lighting variation
- **Perspective disabled** — satellite images have near-orthographic projection

---

## Validation & Metrics

```bash
python training/train.py \
    --validate-only \
    --model-path modelos/yolov8_military.pt \
    --dataset training/dataset/dataset.yaml
```

Output:
```
mAP50:    0.742
mAP50-95: 0.531
Precision: 0.801
Recall:    0.714
```

Confusion matrices and PR curves are saved to `modelos/aegis_military_v1/`.

---

## Deploying the Model

After training, the best checkpoint is automatically copied to:

```
modelos/yolov8_military.pt
```

### Integration with AEGIS detector

Replace the model path in the main AEGIS pipeline configuration:

```python
# config.py or aegis_config.yaml
MODEL_PATH = "modelos/yolov8_military.pt"
CONF_THRESHOLD = 0.35   # adjust based on validation PR curve
```

### Export to ONNX for CPU inference

```bash
yolo export model=modelos/yolov8_military.pt format=onnx imgsz=640
```

### Export to TensorRT for NVIDIA edge deployment

```bash
yolo export model=modelos/yolov8_military.pt format=engine device=0
```

---

## Hardware Recommendations

### By YOLOv8 model variant

| Model      | Parameters | VRAM Required | Recommended GPU              |
|------------|-----------|---------------|------------------------------|
| YOLOv8n    | 3.2M      | 4 GB          | GTX 1650, RTX 3050           |
| YOLOv8s    | 11.2M     | 6 GB          | RTX 2060, GTX 1660           |
| YOLOv8m    | 25.9M     | 8 GB          | RTX 3070, RTX 2080 (default) |
| YOLOv8l    | 43.7M     | 12 GB         | RTX 3080, RTX 4080           |
| YOLOv8x    | 68.2M     | 16 GB+        | RTX 4090, A100               |

### Multi-GPU training

```bash
python training/train.py --device 0,1 --batch 32
```

### Cloud options

- **AWS**: `p3.2xlarge` (V100 16 GB) — ~$3/hr
- **GCP**: `n1-standard-8` + T4 — ~$0.80/hr
- **RunPod**: RTX 3090 — ~$0.35/hr
- **Google Colab Pro**: T4/A100 (shared, free/Pro tier)

---

## Expected Training Times

Times for 100 epochs at `imgsz=640` on ~4,000 images:

| Hardware          | YOLOv8n | YOLOv8m | YOLOv8l |
|-------------------|---------|---------|---------|
| RTX 3070 (8 GB)  | 45 min  | 2.5 hr  | 4 hr    |
| RTX 4090 (24 GB) | 20 min  | 1 hr    | 1.8 hr  |
| A100 (80 GB)     | 10 min  | 35 min  | 55 min  |
| CPU (i9-13900K)  | 8 hr    | 30+ hr  | N/A     |

With `imgsz=1280`, multiply times by ~2.5x.

---

## mAP Targets

Expected performance ranges after fine-tuning on xView:

| Class            | mAP50 Target | Notes                                       |
|------------------|-------------|---------------------------------------------|
| ground_vehicle   | 0.70–0.80   | Abundant training samples                   |
| logistics        | 0.65–0.75   | Large vehicles, easier to detect            |
| air_asset        | 0.75–0.85   | Distinctive shape signature                 |
| naval_asset      | 0.70–0.80   | Water background aids segmentation          |
| engineering      | 0.55–0.70   | High intra-class variance                   |
| armored_vehicle  | 0.50–0.65   | Requires augmented or specialist data       |
| structure        | 0.60–0.70   | Static targets, easier to learn             |
| **Overall mAP50**| **0.65–0.75** | Baseline for operational deployment       |

To improve `armored_vehicle` class performance, supplement with:
- DOTA dataset (annotations include military vehicles)
- Synthetic data from ArmA3/VBS3 simulators
- Hand-labeled Sentinel-2 or Planet imagery

---

## Troubleshooting

### CUDA out of memory

```bash
# Reduce batch size
python training/train.py --batch 8

# Or use gradient accumulation (effective batch = batch * accumulate)
# Edit train.py: add accumulate=4 to model.train() call
```

### Training loss not decreasing

1. Verify dataset integrity: `python -c "import cv2; print(cv2.__version__)"`
2. Check label files are non-empty in `training/dataset/labels/train/`
3. Reduce learning rate: add `lr0=0.001` to `model.train()` call
4. Unfreeze backbone earlier: change `freeze=5`

### Low validation mAP despite good training mAP (overfitting)

- Increase augmentation: raise `degrees=90.0`, add `copy_paste=0.1`
- Add dropout: `dropout=0.1` in `model.train()`
- Reduce model size: switch from `yolov8l` to `yolov8m`

### Images not found during preparation

Verify image filenames in GeoJSON match actual filenames:
```bash
python -c "
import json
with open('xView_train.geojson') as f:
    data = json.load(f)
ids = set(f['properties']['image_id'] for f in data['features'])
print(f'Unique image IDs: {len(ids)}')
print('Sample:', list(ids)[:5])
"
```
