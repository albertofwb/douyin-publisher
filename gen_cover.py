#!/usr/bin/env python3
"""封面图片生成工具"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"


def sanitize_dirname(text: str, max_len: int = 50) -> str:
    text = text.split("\n")[0].strip()
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    return text[:max_len]


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> list[str]:
    """将文本按宽度自动换行"""
    words = list(text)  # 中文按字符分割
    lines = []
    current_line = ""

    for char in words:
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = char

    if current_line:
        lines.append(current_line)

    return lines


def gen_cover(text: str, output: Path | None = None) -> Path:
    """生成封面图片

    Args:
        text: 封面文字，用 \n 换行，第一行为标题
        output: 输出路径，默认自动创建 data/ 目录

    Returns:
        生成的封面图片路径
    """
    text = text.replace("\\n", "\n")

    # Create post directory
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dirname = f"{timestamp}_{sanitize_dirname(text)}"
        post_dir = DATA_DIR / dirname
        post_dir.mkdir(parents=True, exist_ok=True)
        output = post_dir / "cover.png"

        # Save post.json
        lines = text.split("\n")
        title = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        with open(post_dir / "post.json", "w", encoding="utf-8") as f:
            json.dump({"title": title, "body": body, "cover": "cover.png"}, f, ensure_ascii=False, indent=2)

    # Generate image with pure black background
    width, height = 1080, 1920
    margin = 80
    max_text_width = width - margin * 2
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Find Chinese font
    font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    font_path = None
    for fp in font_paths:
        if Path(fp).exists():
            font_path = fp
            break

    # Parse text: first line is title, rest is body
    raw_lines = text.split("\n")
    title = raw_lines[0].strip() if raw_lines else ""
    body_lines = [l.strip() for l in raw_lines[1:] if l.strip()]

    # Start with default font sizes
    title_size = 90
    body_size = 60
    spacing = 40
    title_body_gap = 60

    # Wrap and calculate, shrink font if needed
    max_content_height = height - margin * 2

    while title_size >= 40:
        if font_path:
            title_font = ImageFont.truetype(font_path, title_size)
            body_font = ImageFont.truetype(font_path, body_size)
        else:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()

        # Wrap title
        wrapped_title = wrap_text(title, title_font, max_text_width, draw) if title else []

        # Wrap body lines
        wrapped_body = []
        for line in body_lines:
            wrapped_body.extend(wrap_text(line, body_font, max_text_width, draw))

        # Calculate total height
        total_h = 0

        # Title height
        for line in wrapped_title:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            total_h += bbox[3] - bbox[1] + spacing

        if wrapped_title and wrapped_body:
            total_h += title_body_gap - spacing  # Extra gap between title and body

        # Body height
        for line in wrapped_body:
            bbox = draw.textbbox((0, 0), line, font=body_font)
            total_h += bbox[3] - bbox[1] + spacing

        total_h -= spacing  # Remove last spacing

        if total_h <= max_content_height:
            break

        # Shrink fonts
        title_size -= 10
        body_size = int(title_size * 0.67)
        spacing = int(title_size * 0.4)
        title_body_gap = int(title_size * 0.67)

    # Draw text centered vertically
    y = (height - total_h) // 2

    # Draw title lines
    for line in wrapped_title:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, fill="white", font=title_font)
        y += bbox[3] - bbox[1] + spacing

    if wrapped_title and wrapped_body:
        y += title_body_gap - spacing

    # Draw body lines
    for line in wrapped_body:
        bbox = draw.textbbox((0, 0), line, font=body_font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, fill="white", font=body_font)
        y += bbox[3] - bbox[1] + spacing

    img.save(str(output))
    return output


def main():
    import argparse
    parser = argparse.ArgumentParser(description="生成抖音封面图片")
    parser.add_argument("text", help="封面文字 (用 \\n 换行)")
    parser.add_argument("-o", "--output", type=Path, help="输出路径 (默认自动创建)")
    args = parser.parse_args()

    output = gen_cover(args.text, args.output)
    print(f"封面: {output}")


if __name__ == "__main__":
    main()
