from pathlib import Path

from detectron2.config import CfgNode as CN


def _default_swin_tiny_imagenet_checkpoint():
    checkpoint = Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "swin_tiny_patch4_window7_224.pth"
    return str(checkpoint) if checkpoint.exists() else ""


def add_mamt2_config(cfg):
    """
    MAMT2 / Swin configuration.

    This project implements the localization/segmentation stage:
        Mask R-CNN heads + Swin-FPN backbone.

    RPN, ROI Box Head, and ROI Mask Head intentionally remain Detectron2's
    Mask R-CNN modules, matching the paper's second-stage design.
    """
    cfg.MODEL.SWIN = CN()

    # Swin-Tiny: 4 stages with channels 96, 192, 384, 768 for 224 input.
    cfg.MODEL.SWIN.MODEL_NAME = "swin_tiny_patch4_window7_224"

    # ImageNet initialization is the practical substitute when the paper's
    # multiattribute classification-pretrained Swin checkpoint is unavailable.
    cfg.MODEL.SWIN.PRETRAINED = True

    # Fail loudly if neither a local checkpoint nor a timm pretrained download
    # can initialize Swin. Random Swin initialization gives poor small-data
    # detection/segmentation performance and should be an explicit choice.
    cfg.MODEL.SWIN.REQUIRE_PRETRAINED = True

    # Align with the paper's 224x224 phi-NeXt image resolution.
    cfg.MODEL.SWIN.IMG_SIZE = 224

    # Prefer the local timm ImageNet checkpoint cache if present. This avoids
    # relying on network access during training.
    cfg.MODEL.SWIN.CHECKPOINT_PATH = _default_swin_tiny_imagenet_checkpoint()

    # Optimizer settings for Swin fine-tuning. The backbone keeps a smaller LR,
    # while FPN/RPN/ROI heads adapt faster to the spalling dataset.
    cfg.SOLVER.OPTIMIZER = "ADAMW"
    cfg.SOLVER.BACKBONE_MULTIPLIER = 0.1

    cfg.MAMT2 = CN()
    cfg.MAMT2.COLOR_AUG = False
    cfg.MAMT2.PAPER_GEOMETRY_AUG = False
    cfg.MAMT2.SAVE_BEST_CHECKPOINTS = True
    cfg.MAMT2.CASCADE_BOX_WARM_START = False
    cfg.MAMT2.RPN_ANCHOR_WARM_START = False
    cfg.MAMT2.FREEZE_BACKBONE = False
    cfg.MAMT2.FREEZE_FPN = False
    cfg.MAMT2.FREEZE_RPN = False
    cfg.MAMT2.FREEZE_MASK_HEAD = False
    cfg.MAMT2.TASK_NUM_CLASSES = [3, 2, 2, 2, 3, 4, 4, 4]
    cfg.MAMT2.CLS_LOSS_WEIGHT = 0.3
    cfg.MAMT2.CLS_FEATURE_NAME = "p5"
    cfg.MAMT2.CLASSIFICATION_PRETRAINED = ""
