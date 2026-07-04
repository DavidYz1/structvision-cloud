from pathlib import Path
import uuid

from PIL import Image, ImageDraw, ImageFont


def predict_image(image_path: str) -> dict:
    """
    第一版mock Mask R-CNN / MAMT2推理：
    输入一张图片，生成一个假的bbox和mask可视化结果。
    后面真实接入MAMT2时，只需要把这里替换成真实模型推理即可。
    """
    image_path = Path(image_path)

    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    result_filename = f"result_{uuid.uuid4().hex}{image_path.suffix}"
    result_path = output_dir / result_filename

    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    # 根据图片尺寸自适应生成一个mock bbox，避免固定坐标导致框太大或太小
    x1 = int(width * 0.25)
    y1 = int(height * 0.25)
    x2 = int(width * 0.80)
    y2 = int(height * 0.80)

    box = [x1, y1, x2, y2]
    label = "spalling"
    score = 0.92

    # 创建半透明mask层
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # 用一个不规则多边形模拟剥落区域mask
    mask_polygon = [
        (int(width * 0.30), int(height * 0.30)),
        (int(width * 0.72), int(height * 0.28)),
        (int(width * 0.78), int(height * 0.48)),
        (int(width * 0.66), int(height * 0.74)),
        (int(width * 0.38), int(height * 0.78)),
        (int(width * 0.22), int(height * 0.55)),
    ]

    # 半透明红色mask
    overlay_draw.polygon(mask_polygon, fill=(255, 0, 0, 90))

    # 合成mask
    result = Image.alpha_composite(image.convert("RGBA"), overlay)

    # 画bbox和文字
    draw = ImageDraw.Draw(result)
    draw.rectangle(box, outline=(255, 0, 0, 255), width=max(2, width // 150))

    text = f"{label} {score:.2f}"
    text_x = x1
    text_y = max(0, y1 - 24)

    # 文字背景，避免看不清
    text_box = draw.textbbox((text_x, text_y), text)
    draw.rectangle(text_box, fill=(255, 0, 0, 180))
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255))

    result = result.convert("RGB")
    result.save(result_path)

    return {
        "boxes": [box],
        "labels": [label],
        "scores": [score],
        "masks": [
            {
                "type": "polygon",
                "points": [[x, y] for x, y in mask_polygon]
            }
        ],
        "result_image_path": str(result_path),
        "result_filename": result_filename
    }