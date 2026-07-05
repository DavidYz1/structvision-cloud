from __future__ import annotations

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import sys
import threading
import uuid
from argparse import Namespace
from pathlib import Path
from typing import Any

import numpy as np

DETECTRON2_ROOT = Path(os.environ.get(
    "MAMT2_DETECTRON2_ROOT",
    r"D:\pythonproject\MAMT2-final\detectron2-main",
))
MAMT2_ROOT = DETECTRON2_ROOT / "projects" / "MAMT2"
MAMT2_MAIN = MAMT2_ROOT / "MAMT2_main"
CONFIG_PATH = Path(os.environ.get(
    "MAMT2_CONFIG_PATH",
    r"D:\pythonproject\MAMT2-final\detectron2-main\projects\MAMT2\output"
    r"\mamt2_swin_fpn_task18pretrained_paper_strong\config.yaml",
))
WEIGHT_PATH = Path(os.environ.get(
    "MAMT2_WEIGHT_PATH",
    r"D:\pythonproject\MAMT2-final\detectron2-main\projects\MAMT2\output"
    r"\mamt2_swin_fpn_task18pretrained_paper_strong\model_best_segm.pth",
))
DEFAULT_OUTPUT_DIR = Path(os.environ.get(
    "MAMT2_OUTPUT_DIR",
    r"D:\pythonproject\mamt2-cloud-shm\backend\app\outputs",
))
CLASS_ID_TO_LABEL = {0: "spalling"}

for _path in (DETECTRON2_ROOT, MAMT2_ROOT, MAMT2_MAIN):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

_RUNTIME: dict[str, Any] | None = None
_RUNTIME_ERROR: Exception | None = None
_PREDICTOR: "MAMT2Predictor | None" = None
_PREDICTOR_LOCK = threading.Lock()


def _load_runtime() -> dict[str, Any]:
    """Import heavy MAMT2/Detectron2 dependencies lazily with a clear error."""
    global _RUNTIME, _RUNTIME_ERROR
    if _RUNTIME is not None:
        return _RUNTIME
    if _RUNTIME_ERROR is not None:
        raise RuntimeError(
            "MAMT2 runtime import failed. Please run in the General conda environment "
            "with detectron2, torch, timm, cv2, and project paths available."
        ) from _RUNTIME_ERROR

    try:
        import cv2
        import timm  # noqa: F401
        import torch
        from detectron2.data import MetadataCatalog
        from detectron2.utils.visualizer import ColorMode, Visualizer
        from infer_supportdata_v3 import (
            build_cfg,
            build_predictor_like,
            imread_unicode,
            imwrite_unicode,
            predict_one,
        )
    except Exception as exc:  # noqa: BLE001
        _RUNTIME_ERROR = exc
        raise RuntimeError(
            "Failed to import MAMT2 runtime dependencies. Confirm the General conda "
            "environment can import detectron2, torch, timm, cv2, and "
            "projects/MAMT2/MAMT2_main/infer_supportdata_v3.py."
        ) from exc

    _RUNTIME = {
        "cv2": cv2,
        "torch": torch,
        "MetadataCatalog": MetadataCatalog,
        "ColorMode": ColorMode,
        "Visualizer": Visualizer,
        "build_cfg": build_cfg,
        "build_predictor_like": build_predictor_like,
        "imread_unicode": imread_unicode,
        "imwrite_unicode": imwrite_unicode,
        "predict_one": predict_one,
    }
    return _RUNTIME


def _resolve_device(device: str | None) -> str:
    if device:
        return device
    runtime = _load_runtime()
    torch = runtime["torch"]
    return "cuda" if torch.cuda.is_available() else "cpu"


def _build_args(config_path: Path, device: str) -> Namespace:
    return Namespace(
        arch="mamt2",
        config_file=str(config_path),
        score_thresh=0.5,
        device=device,
        input_size=224,
        square_size=224,
        class_name="SP",
        vis_scale=1.0,
    )


def masks_to_polygons(masks) -> list[dict]:
    """Convert Detectron2 binary masks to largest-contour polygon payloads."""
    runtime = _load_runtime()
    cv2 = runtime["cv2"]

    if masks is None:
        return []
    if hasattr(masks, "numpy"):
        masks = masks.numpy()

    polygons: list[dict] = []
    for mask in masks:
        mask_array = np.asarray(mask)
        if mask_array.size == 0:
            polygons.append({"type": "polygon", "points": []})
            continue

        mask_uint8 = (mask_array.astype("uint8") * 255)
        contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            polygons.append({"type": "polygon", "points": []})
            continue

        contour = max(contours, key=cv2.contourArea)
        if contour.size == 0:
            points = []
        else:
            points = [[float(x), float(y)] for x, y in contour.reshape(-1, 2)]
        polygons.append({"type": "polygon", "points": points})

    return polygons


class MAMT2Predictor:
    def __init__(
        self,
        config_path: str | Path = CONFIG_PATH,
        weight_path: str | Path = WEIGHT_PATH,
        device: str | None = None,
    ):
        self.config_path = Path(config_path)
        self.weight_path = Path(weight_path)

        if not self.config_path.exists():
            raise FileNotFoundError(f"MAMT2 config file does not exist: {self.config_path}")
        if not self.weight_path.exists():
            raise FileNotFoundError(f"MAMT2 weight file does not exist: {self.weight_path}")

        self.runtime = _load_runtime()
        self.device = _resolve_device(device)
        self.args = _build_args(self.config_path, self.device)

        try:
            self.cfg = self.runtime["build_cfg"](self.args, str(self.weight_path))
            self.model = self.runtime["build_predictor_like"](
                self.args,
                self.cfg,
                str(self.weight_path),
            )
            self.metadata = self.runtime["MetadataCatalog"].get("mamt2_cloud_spalling")
            self.metadata.thing_classes = [CLASS_ID_TO_LABEL[0]]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Failed to initialize the real MAMT2 predictor. Check config, weight, "
                "Swin checkpoint path in config, and General environment dependencies."
            ) from exc

    def predict(self, image_path: str, output_dir: str | Path | None = None) -> dict:
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"Input image does not exist: {image_file}")

        save_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
        save_dir.mkdir(parents=True, exist_ok=True)

        imread_unicode = self.runtime["imread_unicode"]
        imwrite_unicode = self.runtime["imwrite_unicode"]
        predict_one = self.runtime["predict_one"]
        Visualizer = self.runtime["Visualizer"]
        ColorMode = self.runtime["ColorMode"]

        image_bgr = imread_unicode(image_file)
        if image_bgr is None:
            raise ValueError(f"Failed to read input image: {image_file}")

        try:
            outputs = predict_one(self.args, self.cfg, self.model, image_bgr)
            instances = outputs["instances"].to("cpu")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"MAMT2 inference failed for image: {image_file}") from exc

        boxes: list[list[float]] = []
        labels: list[str] = []
        scores: list[float] = []
        masks: list[dict] = []

        if len(instances) > 0:
            if instances.has("pred_boxes"):
                boxes = [
                    [round(float(value), 2) for value in box]
                    for box in instances.pred_boxes.tensor.numpy().tolist()
                ]
            if instances.has("scores"):
                scores = [round(float(value), 4) for value in instances.scores.numpy().tolist()]
            if instances.has("pred_classes"):
                labels = [
                    CLASS_ID_TO_LABEL.get(int(class_id), str(int(class_id)))
                    for class_id in instances.pred_classes.numpy().tolist()
                ]
            else:
                labels = [CLASS_ID_TO_LABEL[0] for _ in boxes]
            if instances.has("pred_masks"):
                masks = masks_to_polygons(instances.pred_masks)

        if not labels and boxes:
            labels = [CLASS_ID_TO_LABEL[0] for _ in boxes]
        if not masks:
            masks = [{"type": "polygon", "points": []} for _ in boxes]

        result_filename = f"result_{uuid.uuid4().hex}.jpg"
        result_path = save_dir / result_filename

        try:
            visualizer = Visualizer(
                image_bgr[:, :, ::-1],
                metadata=self.metadata,
                scale=1.0,
                instance_mode=ColorMode.IMAGE,
            )
            vis_output = visualizer.draw_instance_predictions(instances)
            result_bgr = vis_output.get_image()[:, :, ::-1]
            if not imwrite_unicode(result_path, result_bgr):
                raise RuntimeError(f"Failed to write visualization image: {result_path}")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to save MAMT2 visualization image: {result_path}") from exc

        return {
            "boxes": boxes,
            "labels": labels,
            "scores": scores,
            "masks": masks,
            "result_image_path": str(result_path),
            "result_filename": result_filename,
        }


def get_predictor() -> MAMT2Predictor:
    global _PREDICTOR
    if _PREDICTOR is None:
        with _PREDICTOR_LOCK:
            if _PREDICTOR is None:
                _PREDICTOR = MAMT2Predictor()
    return _PREDICTOR


def predict_image_with_mamt2(image_path: str, output_dir: str | Path | None = None) -> dict:
    predictor = get_predictor()
    return predictor.predict(image_path=image_path, output_dir=output_dir)




