from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import yaml

from worker.install_detectron2_wheel import (
    WHEEL_FILENAME,
    WHEEL_SHA256,
    WHEEL_URL,
    verify_wheel,
)
from worker.mamt2_runtime.infer_supportdata_v3 import build_cfg


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO_ROOT / "model"


class RuntimeLayoutTests(unittest.TestCase):
    def test_migrated_config_is_byte_identical(self):
        digest = hashlib.sha256((MODEL_DIR / "config.yaml").read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            "489eaf6e23f155fcbb3ac71a9fe82596aade5d45efbedbb47ca760cf79785c54",
        )

    def test_config_loads_without_dataset_registration(self):
        from detectron2.data import DatasetCatalog

        registered_before = set(DatasetCatalog.list())
        args = Namespace(
            arch="mamt2",
            config_file=str(MODEL_DIR / "config.yaml"),
            score_thresh=0.5,
            device="cpu",
            input_size=224,
            square_size=224,
            class_name="SP",
            vis_scale=1.0,
        )
        cfg = build_cfg(args, "unused-model-path.pth")
        self.assertEqual(cfg.MODEL.META_ARCHITECTURE, "GeneralizedRCNN")
        self.assertEqual(cfg.MODEL.BACKBONE.NAME, "build_swin_timm_fpn_backbone")
        self.assertEqual(cfg.MODEL.ROI_HEADS.NUM_CLASSES, 1)
        self.assertEqual(cfg.MODEL.WEIGHTS, "")
        self.assertFalse(cfg.MODEL.SWIN.PRETRAINED)
        self.assertFalse(cfg.MODEL.SWIN.REQUIRE_PRETRAINED)
        self.assertEqual(cfg.MODEL.SWIN.IMG_SIZE, 224)
        self.assertEqual(set(DatasetCatalog.list()), registered_before)

    def test_labels_and_manifest_match_runtime_contract(self):
        labels = json.loads((MODEL_DIR / "labels.json").read_text(encoding="utf-8"))
        manifest = yaml.safe_load((MODEL_DIR / "manifest.yaml").read_text(encoding="utf-8"))
        self.assertEqual(labels["classes"], [{"id": 0, "name": "spalling", "model_label": "SP"}])
        self.assertEqual(manifest["model"]["filename"], "model_best_segm.pth")
        self.assertEqual(
            manifest["model"]["sha256"],
            "ea1a4e99731f7755598a59527ca782a30c48c08df57d6a61bcd5e95f377be0e2",
        )
        self.assertEqual(manifest["runtime"]["gpu_architectures"], ["sm_86"])
        self.assertEqual(manifest["detectron2"]["wheel"]["url"], WHEEL_URL)
        self.assertEqual(manifest["detectron2"]["wheel"]["sha256"], WHEEL_SHA256)

    def test_detectron2_release_is_pinned(self):
        self.assertTrue(WHEEL_URL.endswith(f"/runtime-deps-v1/{WHEEL_FILENAME}"))
        self.assertEqual(
            WHEEL_SHA256,
            "eb7295b6cb477467cb03660ea024a11ab13e97fc12b157040b9234897f809ace",
        )

    def test_detectron2_wheel_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_wheel = Path(temp_dir) / WHEEL_FILENAME
            fake_wheel.write_bytes(b"not-the-published-wheel")
            with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
                verify_wheel(fake_wheel)

    def test_repo_docker_context_is_allowlisted(self):
        dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertTrue(dockerignore.startswith("**\n"))
        self.assertIn("!worker/mamt2_runtime/", dockerignore)
        included_paths = [
            line[1:] for line in dockerignore.splitlines() if line.startswith("!")
        ]
        self.assertFalse(
            any(path.startswith("mamt2-artifacts/") for path in included_paths)
        )
        self.assertFalse(any(path.startswith("detectron2/") for path in included_paths))

        dockerfile = (REPO_ROOT / "worker" / "Dockerfile.hf").read_text(
            encoding="utf-8"
        )
        self.assertIn("python /tmp/install_detectron2_wheel.py", dockerfile)
        self.assertNotIn("COPY mamt2-artifacts", dockerfile)
        self.assertNotIn("COPY detectron2", dockerfile)


if __name__ == "__main__":
    unittest.main()
