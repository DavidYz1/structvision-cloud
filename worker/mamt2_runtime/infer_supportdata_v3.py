#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run spalling inference through the in-repository MAMT2 runtime package.

v3 fixes two common migration issues:
1) Swin-FPN requires fixed 224x224 input. The script square-resizes images
   before MAMT2 inference and postprocesses predictions back to the original size.
2) Some timm versions name Swin stages as layers.0/layers.1 while others name
   them layers_0/layers_1. The script remaps those checkpoint keys before loading.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import pickle
import re
from pathlib import Path
from typing import List

import cv2
import numpy as np
import torch
from detectron2.config import get_cfg
from detectron2.data import MetadataCatalog
from detectron2.data.transforms import ResizeShortestEdge
from detectron2.modeling import build_model
from detectron2.utils.visualizer import ColorMode, Visualizer

# The runtime is a normal package under worker/mamt2_runtime. Batch CLI defaults
# remain relative to this package, while the Worker imports the functions below
# directly and supplies explicit config, weight, input, and output paths.
PROJECT_ROOT = Path(__file__).resolve().parent

try:
    from .config.add_mamt2_config import add_mamt2_config
    from .backbone.swin_fpn_backbone import build_swin_timm_fpn_backbone  # noqa: F401
except Exception as exc:  # noqa: BLE001
    add_mamt2_config = None
    _MAMT2_IMPORT_ERROR = exc
else:
    _MAMT2_IMPORT_ERROR = None

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def imread_unicode(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_unicode(path: Path, image) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower() or ".jpg"
    ok, encoded = cv2.imencode(suffix, image)
    if not ok:
        return False
    encoded.tofile(str(path))
    return True


def list_images(input_dir: Path, recursive: bool = True) -> List[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(p for p in input_dir.glob(pattern) if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def find_latest_weight(output_dir: Path) -> str:
    output_dir = Path(output_dir)
    last_checkpoint = output_dir / "last_checkpoint"
    if last_checkpoint.exists():
        ckpt_name = last_checkpoint.read_text(encoding="utf-8").strip()
        ckpt_path = output_dir / ckpt_name
        if ckpt_path.exists():
            return str(ckpt_path)

    pth_files = glob.glob(str(output_dir / "*.pth"))
    if not pth_files:
        raise FileNotFoundError(f"没有在 {output_dir} 下找到 .pth 权重文件")
    pth_files.sort(key=os.path.getmtime, reverse=True)
    return pth_files[0]


def scan_candidate_weights(project_root: Path) -> List[Path]:
    roots = [project_root / "output", project_root / "MRCNN", project_root / "MAMT2_main", project_root]
    weights = []
    for root in roots:
        if root.exists():
            weights.extend(Path(p) for p in glob.glob(str(root / "**" / "*.pth"), recursive=True))

    def rank(path: Path):
        name = path.name.lower()
        priority = 99
        for idx, key in enumerate(["model_best_segm", "model_best_bbox", "model_final", "model_", "last"]):
            if key in name:
                priority = idx
                break
        return (priority, -path.stat().st_mtime)

    return sorted(set(weights), key=rank)


def infer_config_from_weight(weight_path: str) -> str:
    cfg_path = Path(weight_path).resolve().parent / "config.yaml"
    return str(cfg_path) if cfg_path.exists() else ""


def build_cfg(args, weight_path: str):
    cfg = get_cfg()
    if args.arch == "mamt2":
        if add_mamt2_config is None:
            raise ImportError(
                "MAMT2 package imports failed. 请通过 worker.mamt2_runtime 包运行。"
            ) from _MAMT2_IMPORT_ERROR
        add_mamt2_config(cfg)

    config_file = args.config_file or infer_config_from_weight(weight_path)
    if not config_file:
        raise FileNotFoundError("没有找到 config.yaml。请使用 --config-file output\\...\\config.yaml 指定训练保存的配置。")

    print("config file :", config_file)
    cfg.merge_from_file(config_file)

    cfg.MODEL.WEIGHTS = ""  # 手动加载，方便修复 timm key 命名差异
    cfg.MODEL.DEVICE = args.device
    cfg.MODEL.ROI_HEADS.NUM_CLASSES = 1
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = args.score_thresh
    cfg.INPUT.MASK_FORMAT = "polygon"
    cfg.DATALOADER.NUM_WORKERS = 0

    if args.arch == "mamt2":
        # Swin patch_embed in this project asserts exact H=W=IMG_SIZE.
        cfg.MODEL.SWIN.IMG_SIZE = args.square_size
        cfg.INPUT.MIN_SIZE_TEST = args.square_size
        cfg.INPUT.MAX_SIZE_TEST = args.square_size
    elif args.arch == "r50" and args.input_size > 0:
        cfg.INPUT.MIN_SIZE_TEST = args.input_size
        cfg.INPUT.MAX_SIZE_TEST = args.input_size

    cfg.freeze()
    return cfg


def _extract_state_dict(checkpoint):
    if not isinstance(checkpoint, dict):
        return checkpoint
    for key in ("model", "state_dict", "model_state", "model_state_dict"):
        value = checkpoint.get(key)
        if isinstance(value, dict):
            return value
    return checkpoint


def _load_checkpoint_file(path: str):
    path_obj = Path(path)
    if path_obj.suffix == ".pkl":
        with path_obj.open("rb") as handle:
            checkpoint = pickle.load(handle, encoding="latin1")
    else:
        checkpoint = torch.load(str(path_obj), map_location="cpu")
    return _extract_state_dict(checkpoint)


def _remap_swin_timm_keys(state_dict: dict) -> dict:
    """Map old timm Swin names layers.0 -> layers_0 used by some timm Feature wrappers.

    Blocks map stage-to-stage:
        layers.2.blocks -> layers_2.blocks
    Downsample modules shift forward in the current wrapper:
        layers.0.downsample -> layers_1.downsample
    """
    out = {}
    for key, value in state_dict.items():
        new_key = key

        # blocks: body.layers.0.blocks -> body.layers_0.blocks
        new_key = re.sub(
            r"(backbone\.bottom_up\.body\.layers)\.(\d+)\.blocks",
            lambda m: f"{m.group(1)}_{m.group(2)}.blocks",
            new_key,
        )

        # downsample: body.layers.0.downsample -> body.layers_1.downsample
        def downsample_repl(m):
            idx = int(m.group(2)) + 1
            return f"{m.group(1)}_{idx}.downsample"

        new_key = re.sub(
            r"(backbone\.bottom_up\.body\.layers)\.(\d+)\.downsample",
            downsample_repl,
            new_key,
        )

        out[new_key] = value
    return out


def load_weights_flexible(model, weight_path: str):
    source_state = _load_checkpoint_file(weight_path)
    if not isinstance(source_state, dict):
        raise TypeError(f"Unsupported checkpoint format: {weight_path}")

    model_state = model.state_dict()

    # Start with the raw checkpoint, then add remapped keys. Remapped keys only
    # matter when the current timm version uses layers_0/layers_1 naming.
    merged_state = dict(source_state)
    remapped = _remap_swin_timm_keys(source_state)
    merged_state.update(remapped)

    filtered = {}
    skipped_shape = []
    for key, value in merged_state.items():
        if key not in model_state or not hasattr(value, "shape"):
            continue
        if tuple(value.shape) == tuple(model_state[key].shape):
            filtered[key] = value
        else:
            skipped_shape.append((key, tuple(value.shape), tuple(model_state[key].shape)))

    incompatible = model.load_state_dict(filtered, strict=False)
    print(f"loaded tensors: {len(filtered)} / checkpoint tensors: {len(source_state)}")
    print(f"missing keys after flexible load: {len(incompatible.missing_keys)}")
    print(f"unexpected keys after flexible load: {len(incompatible.unexpected_keys)}")
    if skipped_shape:
        print("shape-skipped tensors:", len(skipped_shape))
        for item in skipped_shape[:10]:
            print("  ", item)

    # A quick warning for the exact problem you met.
    missing_swin = [k for k in incompatible.missing_keys if k.startswith("backbone.bottom_up.body.layers_")]
    if missing_swin:
        print("警告：仍有 Swin backbone tensors 没加载，MAMT2 结果可能不可靠。前几个 missing：")
        for key in missing_swin[:10]:
            print("  ", key)


def build_predictor_like(args, cfg, weight_path: str):
    model = build_model(cfg)
    load_weights_flexible(model, weight_path)
    model.eval()

    if cfg.MODEL.DEVICE == "cuda":
        model.cuda()
    return model


def preprocess_for_model(args, cfg, original_bgr):
    height, width = original_bgr.shape[:2]

    if args.arch == "mamt2":
        # Fixed square input avoids: Input height (192) doesn't match model (224).
        image = cv2.resize(original_bgr, (args.square_size, args.square_size), interpolation=cv2.INTER_LINEAR)
    else:
        aug = ResizeShortestEdge([cfg.INPUT.MIN_SIZE_TEST, cfg.INPUT.MIN_SIZE_TEST], cfg.INPUT.MAX_SIZE_TEST)
        transform = aug.get_transform(original_bgr)
        image = transform.apply_image(original_bgr)

    if cfg.INPUT.FORMAT == "RGB":
        image = image[:, :, ::-1]
    image = torch.as_tensor(image.astype("float32").transpose(2, 0, 1))
    return {"image": image, "height": height, "width": width}


@torch.no_grad()
def predict_one(args, cfg, model, img_bgr):
    inputs = preprocess_for_model(args, cfg, img_bgr)
    if cfg.MODEL.DEVICE == "cuda":
        inputs["image"] = inputs["image"].cuda()
    return model([inputs])[0]


def run_one_weight(args, weight_path: str, save_dir: Path):
    cfg = build_cfg(args, weight_path)
    model = build_predictor_like(args, cfg, weight_path)

    metadata = MetadataCatalog.get("supportdata_spalling_infer")
    metadata.thing_classes = [args.class_name]

    images = list_images(args.input_dir, recursive=not args.no_recursive)
    if not images:
        raise FileNotFoundError(f"没有在 {args.input_dir} 下找到 jpg/png/bmp/webp 图片")

    pred_dir = save_dir / "pred"
    raw_dir = save_dir / "raw"
    csv_path = save_dir / "summary.csv"
    pred_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    total_instances = 0

    for idx, img_path in enumerate(images, start=1):
        img = imread_unicode(img_path)
        if img is None:
            print(f"[跳过] 读图失败: {img_path}")
            continue

        outputs = predict_one(args, cfg, model, img)
        instances = outputs["instances"].to("cpu")
        num_instances = len(instances)
        total_instances += num_instances

        scores = []
        boxes = []
        if num_instances > 0:
            if instances.has("scores"):
                scores = [float(x) for x in instances.scores.numpy().tolist()]
            if instances.has("pred_boxes"):
                boxes = [[round(float(v), 2) for v in box] for box in instances.pred_boxes.tensor.numpy().tolist()]

        v = Visualizer(img[:, :, ::-1], metadata=metadata, scale=args.vis_scale, instance_mode=ColorMode.IMAGE)
        vis = v.draw_instance_predictions(instances)
        pred_img = vis.get_image()[:, :, ::-1]

        rel_parent = img_path.parent.relative_to(args.input_dir) if img_path.parent != args.input_dir else Path("")
        out_name = f"{img_path.stem}_pred.jpg"
        raw_name = f"{img_path.stem}_raw.jpg"
        imwrite_unicode(pred_dir / rel_parent / out_name, pred_img)
        imwrite_unicode(raw_dir / rel_parent / raw_name, img)

        print(f"[{idx:03d}/{len(images):03d}] {img_path.name} | pred={num_instances} | scores={scores[:5]}")
        rows.append({
            "image": str(img_path),
            "pred_count": num_instances,
            "scores": ";".join(f"{s:.4f}" for s in scores),
            "boxes_xyxy": str(boxes),
            "weight": weight_path,
            "arch": args.arch,
            "square_size": args.square_size if args.arch == "mamt2" else "",
        })

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "pred_count", "scores", "boxes_xyxy", "weight", "arch", "square_size"])
        writer.writeheader()
        writer.writerows(rows)

    print("\n========== inference done ==========")
    print("arch       :", args.arch)
    print("weight     :", weight_path)
    print("input dir  :", args.input_dir)
    print("save dir   :", save_dir)
    print("images     :", len(rows))
    print("instances  :", total_instances)
    print("summary csv:", csv_path)
    if total_instances == 0:
        print("\n没有检测结果：建议把 --score-thresh 降到 0.01，或裁剪局部破损区域后再跑。")


def parse_args():
    parser = argparse.ArgumentParser(description="Infer spalling on unlabeled supportdata images.")
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "supportdata", help="待检测图片文件夹")
    parser.add_argument("--save-dir", type=Path, default=PROJECT_ROOT / "supportout", help="输出文件夹")
    parser.add_argument("--arch", choices=("mamt2", "r50"), default="mamt2", help="mamt2=Swin-FPN；r50=标准Mask R-CNN R50-FPN")
    parser.add_argument("--weights", default="", help="指定 .pth 权重；为空则从 --output-dir 找最新权重")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "output" / "mamt2_swin_fpn_strong_spalling", help="权重输出目录，用于自动找 .pth")
    parser.add_argument("--config-file", default="", help="指定训练输出的 config.yaml。为空时自动用权重同目录下的 config.yaml")
    parser.add_argument("--score-thresh", type=float, default=0.05, help="检测阈值。迁移测试建议 0.01~0.10")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu", help="cuda 或 cpu")
    parser.add_argument("--class-name", default="SP", help="可视化类别名")
    parser.add_argument("--vis-scale", type=float, default=1.0, help="可视化缩放")
    parser.add_argument("--no-recursive", action="store_true", help="不递归读取子文件夹")
    parser.add_argument("--input-size", type=int, default=224, help="r50 模式测试尺寸；<=0 表示使用 config 默认")
    parser.add_argument("--square-size", type=int, default=224, help="mamt2/Swin 固定方形输入尺寸")
    parser.add_argument("--list-weights", action="store_true", help="列出可能的 .pth 权重后退出")
    return parser.parse_args()


def main():
    args = parse_args()
    args.input_dir = args.input_dir.resolve()
    args.save_dir = args.save_dir.resolve()
    args.output_dir = args.output_dir.resolve()

    if args.list_weights:
        print("可能的权重文件：")
        for p in scan_candidate_weights(PROJECT_ROOT):
            print("  ", p)
        return

    weight_path = args.weights or find_latest_weight(args.output_dir)
    weight_path = str(Path(weight_path).resolve())

    run_name = f"{args.arch}_{Path(weight_path).stem}_thr{args.score_thresh:g}"
    if args.arch == "mamt2":
        run_name = f"{args.arch}_square{args.square_size}_{Path(weight_path).stem}_thr{args.score_thresh:g}"
    save_dir = args.save_dir / run_name

    print("PROJECT_ROOT:", PROJECT_ROOT)
    print("input dir   :", args.input_dir)
    print("save dir    :", save_dir)
    print("arch        :", args.arch)
    print("weights     :", weight_path)
    print("device      :", args.device)
    print("score thresh:", args.score_thresh)

    run_one_weight(args, weight_path, save_dir)


if __name__ == "__main__":
    main()
