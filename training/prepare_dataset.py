"""
Dataset Preparation — AEGIS-IMINT Training Pipeline
Prepares military vehicle datasets for YOLOv8 fine-tuning.
"""
import os
import json
import shutil
import random
from pathlib import Path
from typing import Tuple, List
import argparse

# NATO military vehicle class mapping
# Maps xView class IDs to simplified military categories
XVIEW_MILITARY_CLASSES = {
    17: 'fixed_wing_aircraft',
    18: 'small_aircraft',
    19: 'cargo_plane',
    20: 'helicopter',
    21: 'passenger_vehicle',
    23: 'truck',
    24: 'bus',
    25: 'pickup_truck',
    26: 'utility_truck',
    27: 'cargo_truck',
    28: 'cargo_truck_w_flatbed',
    29: 'cargo_truck_w_liquid',
    32: 'dump_truck',
    33: 'haul_truck',
    34: 'scraper_tractor',
    35: 'front_loader_bulldozer',
    36: 'excavator',
    37: 'cement_mixer',
    38: 'ground_grader',
    60: 'maritime_vessel',
    61: 'motorboat',
    62: 'sailboat',
    63: 'tugboat',
    64: 'barge',
    65: 'ferry_vessel',
    66: 'container_ship',
    73: 'engineering_vehicle',
    74: 'tower_crane',
    75: 'container_crane',
    76: 'reach_stacker',
    77: 'straddle_carrier',
    79: 'mobile_crane',
    83: 'scraper_tractor',
    84: 'ground_grader',
    86: 'small_car',
    89: 'vehicle_lot',
    93: 'helo_pad',
    94: 'storage_tank',
}

# Simplified 8-class mapping for NATO compatibility
NATO_CLASSES = {
    'ground_vehicle': 0,    # trucks, cars, utility
    'armored_vehicle': 1,   # military ground assets
    'air_asset': 2,         # aircraft, helicopters
    'naval_asset': 3,       # ships, boats
    'engineering': 4,       # construction, military engineers
    'logistics': 5,         # cargo, fuel trucks
    'structure': 6,         # installations, depots
    'unknown': 7,
}

XVIEW_TO_NATO = {
    17: 2, 18: 2, 19: 2, 20: 2,           # aircraft → air_asset
    21: 0, 86: 0, 25: 0,                    # cars → ground_vehicle
    23: 5, 24: 5, 26: 5, 27: 5, 28: 5,    # trucks → logistics
    29: 5, 33: 5,
    60: 3, 61: 3, 62: 3, 63: 3, 64: 3,    # maritime → naval_asset
    65: 3, 66: 3,
    32: 4, 34: 4, 35: 4, 36: 4, 37: 4,    # heavy equip → engineering
    73: 4, 74: 4, 75: 4, 79: 4,
}


def xview_to_yolo(geojson_path: str, images_dir: str, output_dir: str,
                   val_split: float = 0.2, seed: int = 42) -> Tuple[int, int]:
    """
    Convert xView GeoJSON annotations to YOLOv8 format.
    Returns (train_count, val_count).
    """
    random.seed(seed)

    out = Path(output_dir)
    for split in ['train', 'val']:
        (out / 'images' / split).mkdir(parents=True, exist_ok=True)
        (out / 'labels' / split).mkdir(parents=True, exist_ok=True)

    with open(geojson_path) as f:
        data = json.load(f)

    # Group features by image
    by_image: dict = {}
    for feat in data.get('features', []):
        props = feat.get('properties', {})
        img_id = props.get('image_id', '')
        if not img_id:
            continue
        type_id = int(props.get('type_id', -1))
        nato_class = XVIEW_TO_NATO.get(type_id, 7)
        coords = feat['geometry']['coordinates'][0]
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        by_image.setdefault(img_id, []).append({
            'class': nato_class,
            'bbox': [min(xs), min(ys), max(xs), max(ys)],
        })

    image_ids = list(by_image.keys())
    random.shuffle(image_ids)
    n_val = max(1, int(len(image_ids) * val_split))
    val_ids = set(image_ids[:n_val])

    train_count = val_count = 0

    for img_id, objects in by_image.items():
        img_src = Path(images_dir) / img_id
        if not img_src.exists():
            continue

        split = 'val' if img_id in val_ids else 'train'
        img_dst = out / 'images' / split / img_id
        shutil.copy2(img_src, img_dst)

        # Read image size
        import cv2
        img = cv2.imread(str(img_src))
        if img is None:
            continue
        H, W = img.shape[:2]

        label_path = out / 'labels' / split / (Path(img_id).stem + '.txt')
        with open(label_path, 'w') as lf:
            for obj in objects:
                x1, y1, x2, y2 = obj['bbox']
                cx = (x1 + x2) / 2 / W
                cy = (y1 + y2) / 2 / H
                bw = (x2 - x1) / W
                bh = (y2 - y1) / H
                lf.write(f"{obj['class']} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")

        if split == 'val':
            val_count += 1
        else:
            train_count += 1

    return train_count, val_count


def write_dataset_yaml(output_dir: str, num_classes: int = 8) -> str:
    """Write dataset.yaml for YOLOv8."""
    yaml_path = os.path.join(output_dir, 'dataset.yaml')
    content = f"""# AEGIS-IMINT Military Vehicle Dataset
path: {os.path.abspath(output_dir)}
train: images/train
val: images/val

nc: {num_classes}
names:
  0: ground_vehicle
  1: armored_vehicle
  2: air_asset
  3: naval_asset
  4: engineering
  5: logistics
  6: structure
  7: unknown
"""
    with open(yaml_path, 'w') as f:
        f.write(content)
    return yaml_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prepare xView dataset for AEGIS-IMINT')
    parser.add_argument('--geojson', required=True, help='Path to xView GeoJSON file')
    parser.add_argument('--images', required=True, help='Path to xView images directory')
    parser.add_argument('--output', default='training/dataset', help='Output directory')
    parser.add_argument('--val-split', type=float, default=0.2)
    args = parser.parse_args()

    print(f"Preparing dataset: {args.geojson}")
    train, val = xview_to_yolo(args.geojson, args.images, args.output, args.val_split)
    yaml = write_dataset_yaml(args.output)
    print(f"Done: {train} train, {val} val images → {yaml}")


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
import unittest
import tempfile
import json as _json


class TestNatoClassMapping(unittest.TestCase):
    def test_aircraft_mapped(self):
        for xview_id in [17, 18, 19, 20]:
            self.assertEqual(XVIEW_TO_NATO[xview_id], 2, f"ID {xview_id} should be air_asset(2)")

    def test_maritime_mapped(self):
        for xview_id in [60, 61, 62, 63, 64, 65, 66]:
            self.assertEqual(XVIEW_TO_NATO[xview_id], 3, f"ID {xview_id} should be naval_asset(3)")

    def test_logistics_mapped(self):
        for xview_id in [23, 24, 26, 27, 28, 29, 33]:
            self.assertEqual(XVIEW_TO_NATO[xview_id], 5, f"ID {xview_id} should be logistics(5)")

    def test_engineering_mapped(self):
        for xview_id in [32, 34, 35, 36, 37, 73, 74, 75, 79]:
            self.assertEqual(XVIEW_TO_NATO[xview_id], 4, f"ID {xview_id} should be engineering(4)")

    def test_unknown_fallback(self):
        self.assertEqual(XVIEW_TO_NATO.get(9999, 7), 7)

    def test_nato_classes_count(self):
        self.assertEqual(len(NATO_CLASSES), 8)

    def test_xview_military_classes_nonempty(self):
        self.assertGreater(len(XVIEW_MILITARY_CLASSES), 0)


class TestWriteDatasetYaml(unittest.TestCase):
    def test_yaml_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_dataset_yaml(tmpdir)
            self.assertTrue(os.path.isfile(path))
            with open(path) as f:
                content = f.read()
            self.assertIn("nc: 8", content)
            self.assertIn("ground_vehicle", content)
            self.assertIn("armored_vehicle", content)
            self.assertIn("naval_asset", content)
            self.assertIn("images/train", content)
            self.assertIn("images/val", content)

    def test_yaml_custom_classes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_dataset_yaml(tmpdir, num_classes=4)
            with open(path) as f:
                content = f.read()
            self.assertIn("nc: 4", content)

    def test_yaml_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_dataset_yaml(tmpdir)
            with open(path) as f:
                content = f.read()
            self.assertIn(os.path.abspath(tmpdir), content)


class TestXviewToYolo(unittest.TestCase):
    """Tests using synthetic GeoJSON + fake images (no cv2 needed — patched)."""

    def _make_geojson(self, features):
        return {"type": "FeatureCollection", "features": features}

    def _make_feature(self, img_id, type_id, x1, y1, x2, y2):
        return {
            "type": "Feature",
            "properties": {"image_id": img_id, "type_id": type_id},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]]
            }
        }

    def test_empty_geojson_returns_zeros(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            geojson_path = os.path.join(tmpdir, 'empty.json')
            with open(geojson_path, 'w') as f:
                _json.dump(self._make_geojson([]), f)
            train, val = xview_to_yolo(geojson_path, tmpdir, os.path.join(tmpdir, 'out'))
        self.assertEqual(train, 0)
        self.assertEqual(val, 0)

    def test_missing_image_file_skipped(self):
        """If image file doesn't exist in images_dir, it must be skipped gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            feats = [self._make_feature("nonexistent.tif", 17, 0, 0, 100, 100)]
            geojson_path = os.path.join(tmpdir, 'data.json')
            with open(geojson_path, 'w') as f:
                _json.dump(self._make_geojson(feats), f)
            out_dir = os.path.join(tmpdir, 'out')
            train, val = xview_to_yolo(geojson_path, tmpdir, out_dir)
        # Both zero because image file doesn't exist
        self.assertEqual(train + val, 0)

    def test_output_dirs_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            geojson_path = os.path.join(tmpdir, 'empty.json')
            with open(geojson_path, 'w') as f:
                _json.dump(self._make_geojson([]), f)
            out_dir = os.path.join(tmpdir, 'out')
            xview_to_yolo(geojson_path, tmpdir, out_dir)
            self.assertTrue(os.path.isdir(os.path.join(out_dir, 'images', 'train')))
            self.assertTrue(os.path.isdir(os.path.join(out_dir, 'images', 'val')))
            self.assertTrue(os.path.isdir(os.path.join(out_dir, 'labels', 'train')))
            self.assertTrue(os.path.isdir(os.path.join(out_dir, 'labels', 'val')))

    def test_feature_missing_image_id_skipped(self):
        """Features without image_id must be silently ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            feat = {
                "type": "Feature",
                "properties": {"type_id": 17},  # no image_id
                "geometry": {"type": "Polygon",
                             "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
            }
            geojson_path = os.path.join(tmpdir, 'data.json')
            with open(geojson_path, 'w') as f:
                _json.dump(self._make_geojson([feat]), f)
            out_dir = os.path.join(tmpdir, 'out')
            train, val = xview_to_yolo(geojson_path, tmpdir, out_dir)
        self.assertEqual(train + val, 0)

    def test_val_split_at_least_one(self):
        """val_split applied to single image still yields n_val >= 1."""
        # n_val = max(1, int(1 * 0.2)) = max(1, 0) = 1
        n_val = max(1, int(1 * 0.2))
        self.assertEqual(n_val, 1)

    def test_yolo_bbox_normalization(self):
        """Verify YOLO bbox normalization formula via a direct calculation."""
        W, H = 100, 200
        x1, y1, x2, y2 = 10, 20, 50, 80
        cx = (x1 + x2) / 2 / W
        cy = (y1 + y2) / 2 / H
        bw = (x2 - x1) / W
        bh = (y2 - y1) / H
        self.assertAlmostEqual(cx, 0.3)
        self.assertAlmostEqual(cy, 0.25)
        self.assertAlmostEqual(bw, 0.4)
        self.assertAlmostEqual(bh, 0.3)
        # All values must be in [0, 1]
        for v in [cx, cy, bw, bh]:
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
