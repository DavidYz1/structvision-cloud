from __future__ import annotations

import argparse
import json
from pathlib import Path

from mamt2_predictor import predict_image_with_mamt2


def parse_args():
    parser = argparse.ArgumentParser(description="Test the real MAMT2 predictor without starting FastAPI.")
    parser.add_argument("--image", required=True, help="Path to a local test image.")
    parser.add_argument("--output-dir", default=None, help="Directory for the result visualization image.")
    return parser.parse_args()


def main():
    args = parse_args()
    result = predict_image_with_mamt2(args.image, output_dir=args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    result_path = Path(result["result_image_path"])
    print(f"result_image_path exists: {result_path.exists()}")
    print(f"result_image_path: {result_path}")


if __name__ == "__main__":
    main()
