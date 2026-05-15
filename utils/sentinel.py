import os
import cv2
import numpy as np
from datetime import datetime, timedelta
from sentinelhub import (SHConfig, SentinelHubRequest, MimeType, CRS, BBox,
                          DataCollection, bbox_to_dimensions)
from config import CLIENT_ID, CLIENT_SECRET, INSTANCE_ID, SENTINEL_RESOLUTION, IMAGES_DIR


def build_config() -> SHConfig:
    cfg = SHConfig()
    cfg.instance_id = INSTANCE_ID
    cfg.sh_client_id = CLIENT_ID
    cfg.sh_client_secret = CLIENT_SECRET
    return cfg


EVALSCRIPT_RGB = """
//VERSION=3
function setup() {
  return { input: ["B04","B03","B02"], output: { bands: 3 } };
}
function evaluatePixel(s) {
  return [3.5*s.B04, 3.5*s.B03, 3.5*s.B02];
}
"""

EVALSCRIPT_NDVI = """
//VERSION=3
function setup() {
  return { input: ["B04","B08"], output: { bands: 1 } };
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04 + 0.0001);
  return [ndvi];
}
"""


def descargar_imagen(bbox_coords: list, days_back: int = 3) -> str:
    """Download latest Sentinel-2 image for bbox. Returns local path.

    Always uses a rolling time window of (today - days_back) to today
    so that the date is never hardcoded.
    """
    config = build_config()
    bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)
    time_interval = (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))

    size = bbox_to_dimensions(bbox, resolution=SENTINEL_RESOLUTION)
    # Cap size to avoid huge downloads
    max_px = 2500
    if size[0] > max_px or size[1] > max_px:
        scale = max_px / max(size)
        size = (int(size[0] * scale), int(size[1] * scale))

    request = SentinelHubRequest(
        evalscript=EVALSCRIPT_RGB,
        input_data=[SentinelHubRequest.input_data(
            data_collection=DataCollection.SENTINEL2_L1C,
            time_interval=time_interval,
            mosaicking_order='leastCC',  # least cloud cover
        )],
        responses=[SentinelHubRequest.output_response('default', MimeType.PNG)],
        bbox=bbox,
        size=size,
        config=config,
    )

    image = request.get_data(save_data=False)[0]

    os.makedirs(IMAGES_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(IMAGES_DIR, f'sentinel_{ts}.png')
    cv2.imwrite(path, cv2.cvtColor((image * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    return path
