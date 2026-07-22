"""Swin Transformer + FPN backbone for MAMT2 localization/segmentation."""

import logging
import math
import os

import timm
import torch

from detectron2.layers import ShapeSpec
from detectron2.modeling import BACKBONE_REGISTRY, Backbone
from detectron2.modeling.backbone.fpn import FPN, LastLevelMaxPool


logger = logging.getLogger(__name__)


def _extract_state_dict(checkpoint):
    if not isinstance(checkpoint, dict):
        return checkpoint
    for key in ("model", "state_dict", "model_state", "state_dict_ema"):
        value = checkpoint.get(key)
        if isinstance(value, dict):
            return value
    return checkpoint


def _strip_prefix(state_dict, prefix):
    if not any(key.startswith(prefix) for key in state_dict.keys()):
        return None
    return {key[len(prefix) :] if key.startswith(prefix) else key: value for key, value in state_dict.items()}


def _add_prefix(state_dict, prefix):
    return {prefix + key: value for key, value in state_dict.items()}


def load_timm_checkpoint_flexible(module, checkpoint_path, description):
    """Load compatible tensors and ignore classifier heads from timm checkpoints."""
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    source_state = _extract_state_dict(checkpoint)
    if not isinstance(source_state, dict):
        raise TypeError(f"Unsupported checkpoint format for {description}: {checkpoint_path}")

    target_state = module.state_dict()
    candidates = [source_state]
    for prefix in ("module.", "model.", "backbone.", "body.", "module.model.", "module.backbone."):
        stripped = _strip_prefix(source_state, prefix)
        if stripped is not None:
            candidates.append(stripped)
    for prefix in ("model.", "backbone.", "body."):
        candidates.append(_add_prefix(source_state, prefix))

    best_filtered = {}
    for candidate in candidates:
        filtered = {
            key: value
            for key, value in candidate.items()
            if key in target_state
            and hasattr(value, "shape")
            and tuple(value.shape) == tuple(target_state[key].shape)
        }
        if len(filtered) > len(best_filtered):
            best_filtered = filtered

    if not best_filtered:
        raise RuntimeError(f"No compatible tensors found in {description}: {checkpoint_path}")

    incompatible = module.load_state_dict(best_filtered, strict=False)
    logger.info(
        "Loaded %s: %d tensors from %s; missing=%d, unexpected=%d",
        description,
        len(best_filtered),
        checkpoint_path,
        len(incompatible.missing_keys),
        len(incompatible.unexpected_keys),
    )
    return len(best_filtered)


class SwinTimmBackbone(Backbone):
    """
    timm Swin Transformer -> Detectron2 bottom-up backbone.

    Outputs for ``swin_tiny_patch4_window7_224``:
        swin1: stride 4,  channels 96
        swin2: stride 8,  channels 192
        swin3: stride 16, channels 384
        swin4: stride 32, channels 768

    Detectron2's FPN then builds p2-p6 from these hierarchical maps.
    """

    def __init__(self, cfg, input_shape):
        super().__init__()

        self.model_name = cfg.MODEL.SWIN.MODEL_NAME
        self.pretrained = cfg.MODEL.SWIN.PRETRAINED
        self.require_pretrained = cfg.MODEL.SWIN.REQUIRE_PRETRAINED
        self.img_size = cfg.MODEL.SWIN.IMG_SIZE
        self.checkpoint_path = cfg.MODEL.SWIN.CHECKPOINT_PATH
        self._manual_forward = False

        # Prefer a local checkpoint. Otherwise timm can use ImageNet weights
        # from its local cache or download them if the environment allows it.
        use_local_ckpt = (
            self.checkpoint_path is not None
            and len(self.checkpoint_path) > 0
            and os.path.exists(self.checkpoint_path)
        )
        if use_local_ckpt:
            logger.info("Using local Swin ImageNet checkpoint: %s", self.checkpoint_path)

        create_kwargs = dict(
            pretrained=(self.pretrained and not use_local_ckpt),
            out_indices=(0, 1, 2, 3),
            img_size=self.img_size,
        )

        try:
            self.body = timm.create_model(
                self.model_name,
                features_only=True,
                **create_kwargs,
            )
            channels = self.body.feature_info.channels()
            reductions = self.body.feature_info.reduction()
        except AttributeError as exc:
            # timm 0.6.x has Swin models whose features_only wrapper expects
            # ``feature_info`` that the model does not expose.  Fall back to
            # the normal model and manually collect the outputs before each
            # stage's patch-merging downsample.
            logger.warning(
                "timm features_only is unavailable for %s (%s); "
                "falling back to manual Swin stage extraction.",
                self.model_name,
                exc,
            )
            create_kwargs.pop("out_indices", None)
            self.body = self._create_standard_swin(create_kwargs, use_local_ckpt)
            self._manual_forward = True
            channels = self._infer_manual_channels()
            reductions = [4, 8, 16, 32]

        if use_local_ckpt:
            load_timm_checkpoint_flexible(self.body, self.checkpoint_path, "Swin ImageNet backbone")

        self._out_features = ["swin1", "swin2", "swin3", "swin4"]

        self._out_feature_channels = {
            name: ch for name, ch in zip(self._out_features, channels)
        }

        self._out_feature_strides = {
            name: st for name, st in zip(self._out_features, reductions)
        }

        logger.info("Swin backbone: %s", self.model_name)
        logger.info("Swin pretrained: %s", self.pretrained)
        logger.info("Swin require_pretrained: %s", self.require_pretrained)
        logger.info("Swin img_size: %s", self.img_size)
        logger.info("Swin checkpoint_path: %s", self.checkpoint_path)
        logger.info("Swin out_features: %s", self._out_features)
        logger.info("Swin channels: %s", self._out_feature_channels)
        logger.info("Swin strides: %s", self._out_feature_strides)

    def _create_standard_swin(self, create_kwargs, use_local_ckpt):
        try:
            return timm.create_model(self.model_name, **create_kwargs)
        except Exception as exc:
            if self.require_pretrained and (create_kwargs.get("pretrained", False) or use_local_ckpt):
                raise RuntimeError(
                    f"Failed to initialize {self.model_name} with pretrained weights. "
                    "Check MODEL.SWIN.CHECKPOINT_PATH, or set MODEL.SWIN.REQUIRE_PRETRAINED False "
                    "only if you intentionally want random initialization."
                ) from exc
            if create_kwargs.get("pretrained", False) and not use_local_ckpt:
                logger.warning(
                    "Could not initialize %s with timm pretrained weights (%s). "
                    "Retrying with random initialization. For paper-style transfer, "
                    "set MODEL.SWIN.CHECKPOINT_PATH to a local Swin checkpoint.",
                    self.model_name,
                    exc,
                )
                retry_kwargs = dict(create_kwargs)
                retry_kwargs["pretrained"] = False
                return timm.create_model(self.model_name, **retry_kwargs)
            raise

    def forward(self, x):
        if self._manual_forward:
            return self._forward_manual(x)

        features = self.body(x)
        outputs = {}

        for name, feat in zip(self._out_features, features):
            expected_c = self._out_feature_channels[name]

            # timm Swin may output NHWC; Detectron2 expects NCHW.
            if feat.dim() == 4 and feat.shape[-1] == expected_c:
                feat = feat.permute(0, 3, 1, 2).contiguous()

            outputs[name] = feat

        return outputs

    def _infer_manual_channels(self):
        if self.model_name.startswith("swin_tiny"):
            return [96, 192, 384, 768]

        channels = []
        for layer in self.body.layers:
            blocks = getattr(layer, "blocks", None)
            if blocks is None or len(blocks) == 0:
                raise ValueError(f"Cannot infer Swin channels for {self.model_name}")
            norm = getattr(blocks[0], "norm1", None)
            if norm is None or not hasattr(norm, "normalized_shape"):
                raise ValueError(f"Cannot infer Swin channels for {self.model_name}")
            channels.append(norm.normalized_shape[0])
        return channels

    def _forward_manual(self, x):
        body = self.body
        x = body.patch_embed(x)

        if getattr(body, "absolute_pos_embed", None) is not None:
            x = x + body.absolute_pos_embed
        x = body.pos_drop(x)

        outputs = {}
        for idx, layer in enumerate(body.layers):
            x = self._run_swin_blocks(layer, x)
            name = self._out_features[idx]
            outputs[name] = self._feature_to_nchw(
                x,
                self._out_feature_channels[name],
            )

            if getattr(layer, "downsample", None) is not None:
                x = layer.downsample(x)

        return outputs

    @staticmethod
    def _run_swin_blocks(layer, x):
        if getattr(layer, "grad_checkpointing", False) and not torch.jit.is_scripting():
            try:
                from timm.models.helpers import checkpoint_seq

                return checkpoint_seq(layer.blocks, x)
            except Exception:
                pass
        return layer.blocks(x)

    @staticmethod
    def _feature_to_nchw(feat, expected_c):
        if feat.dim() == 3:
            batch, length, channels = feat.shape
            if channels != expected_c:
                raise ValueError(
                    f"Unexpected Swin feature channels: got {channels}, expected {expected_c}"
                )
            size = int(math.sqrt(length))
            if size * size != length:
                raise ValueError(f"Cannot reshape Swin tokens with length {length} to a square map")
            feat = feat.reshape(batch, size, size, channels)

        if feat.dim() == 4 and feat.shape[-1] == expected_c:
            return feat.permute(0, 3, 1, 2).contiguous()
        if feat.dim() == 4 and feat.shape[1] == expected_c:
            return feat

        raise ValueError(f"Unexpected Swin feature shape: {tuple(feat.shape)}")

    def output_shape(self):
        return {
            name: ShapeSpec(
                channels=self._out_feature_channels[name],
                stride=self._out_feature_strides[name],
            )
            for name in self._out_features
        }


@BACKBONE_REGISTRY.register()
def build_swin_timm_fpn_backbone(cfg, input_shape):
    bottom_up = SwinTimmBackbone(cfg, input_shape)

    backbone = FPN(
        bottom_up=bottom_up,
        in_features=cfg.MODEL.FPN.IN_FEATURES,
        out_channels=cfg.MODEL.FPN.OUT_CHANNELS,
        norm=cfg.MODEL.FPN.NORM,
        top_block=LastLevelMaxPool(),
        fuse_type=cfg.MODEL.FPN.FUSE_TYPE,
    )

    return backbone
