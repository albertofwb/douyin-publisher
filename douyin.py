#!/usr/bin/env python3
"""抖音发布工具 - 封面生成、TTS音乐、发布"""

import argparse
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DOUYIN_POST_URL = "https://creator.douyin.com/creator-micro/content/post/image?enter_from=publish_page&media_type=image&type=new"


# === Cover ===
def sanitize_dirname(text: str, max_len: int = 50) -> str:
    text = text.split("\n")[0].strip()
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    return text[:max_len]


def cmd_cover(args):
    from PIL import Image, ImageDraw, ImageFont

    text = args.text.replace("\\n", "\n")

    # Create post directory (no spaces)
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

    # Generate image
    img = Image.new("RGB", (1080, 1920), color="white")
    draw = ImageDraw.Draw(img)

    font = None
    for fp in ["/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"]:
        if Path(fp).exists():
            font = ImageFont.truetype(fp, 80)
            break
    if not font:
        font = ImageFont.load_default()

    lines = text.split("\n")
    line_heights = [draw.textbbox((0, 0), l, font=font)[3] for l in lines]
    total_h = sum(line_heights) + (len(lines) - 1) * 20
    y = (1920 - total_h) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (1080 - bbox[2]) // 2
        draw.text((x, y), line, fill="black", font=font)
        y += line_heights[i] + 20

    img.save(str(output))
    print(f"封面: {output}")


# === Music ===
def cmd_music(args):
    # Find latest post directory
    if DATA_DIR.exists():
        dirs = sorted(DATA_DIR.iterdir(), reverse=True)
        output = dirs[0] / "music.mp3" if dirs else DATA_DIR / "music.mp3"
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        output = DATA_DIR / "music.mp3"

    result = subprocess.run(
        ["edge-tts", "--text", args.text, "--voice", args.voice, "--write-media", str(output)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"错误: {result.stderr}")
        sys.exit(1)
    print(f"音乐: {output}")


# === Post ===
def cmd_post(args):
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    from chrome_utils import CDP_URL, ensure_chrome_cdp

    if not ensure_chrome_cdp():
        sys.exit(1)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"无法连接 CDP: {e}")
            sys.exit(1)

        page = browser.contexts[0].new_page()

        try:
            page.goto(DOUYIN_POST_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            try:
                page.wait_for_selector('[placeholder="添加作品标题"]', timeout=15000)
            except PlaywrightTimeout:
                print("请先登录抖音创作者平台")
                sys.exit(1)

            # Upload images
            image_paths = [str(Path(img).expanduser().resolve()) for img in args.images]
            for p in image_paths:
                if not Path(p).exists():
                    print(f"图片不存在: {p}")
                    sys.exit(1)

            upload_btn = page.locator('text=点击上传')
            if upload_btn.count() > 0:
                with page.expect_file_chooser() as fc:
                    upload_btn.first.click()
                fc.value.set_files(image_paths)
                time.sleep(3)

            # Title
            if args.title:
                title_input = page.locator('[placeholder="添加作品标题"]')
                if title_input.count() > 0:
                    title_input.first.fill(args.title)
                    time.sleep(0.5)

            # Description
            if args.description:
                editor = page.locator('[contenteditable="true"]').first
                if editor.count() > 0:
                    editor.click()
                    page.keyboard.type(args.description)
                    time.sleep(0.5)

            # Music (hover + move to reveal button, then click visible one)
            if args.music:
                try:
                    page.locator('text=选择音乐').last.click()
                    time.sleep(2)
                    panel = page.locator('[class*="sidesheet"]').first
                    idx = random.randint(0, 4)
                    # Hover on the music item to reveal button
                    use_btn = panel.locator('text=使用').nth(idx)
                    box = use_btn.bounding_box()
                    if box:
                        page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        time.sleep(0.5)
                        page.mouse.move(box['x'] + box['width']/2 + 5, box['y'] + box['height']/2)
                        time.sleep(random.uniform(1.5, 2.5))
                    # Click the visible primary button
                    page.locator('button[class*="primary"]:has-text("使用"):visible').first.click(timeout=5000)
                    print(f"已选择第 {idx + 1} 个音乐")
                    time.sleep(2)
                    # Close music panel by clicking X button
                    close_btn = page.locator('[class*="sidesheet"] [class*="close"], [class*="sidesheet"] svg').first
                    if close_btn.count() > 0:
                        close_btn.click()
                    time.sleep(1)
                except Exception as e:
                    print(f"音乐选择失败: {e}")

            # Hotspot
            if args.hotspot:
                try:
                    page.locator('text=点击输入热点词').first.click()
                    time.sleep(1)
                    page.keyboard.type(args.hotspot)
                    time.sleep(2)
                    page.locator('[class*="option"]').first.click()
                    time.sleep(1)
                except Exception as e:
                    print(f"热点关联失败: {e}")

            if args.debug:
                input("按 Enter 继续...")
            else:
                # Close any open panel first
                mask = page.locator('[class*="sidesheet-mask"]')
                if mask.count() > 0:
                    mask.first.click()
                    time.sleep(1)
                # Click 发布 button
                print("点击发布...")
                publish_btn = page.locator('button:has-text("发布")').first
                publish_btn.click(timeout=10000)
                time.sleep(3)
                print("已发布")

        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="douyin", description="抖音发布工具")
    sub = parser.add_subparsers(dest="cmd")

    # cover
    p_cover = sub.add_parser("cover", help="生成封面图片")
    p_cover.add_argument("text", help="封面文字 (用 \\n 换行)")

    # music
    p_music = sub.add_parser("music", help="生成 TTS 音乐")
    p_music.add_argument("text", help="要转换的文字")
    p_music.add_argument("--voice", default=DEFAULT_VOICE, help="TTS 声音")

    # post
    p_post = sub.add_parser("post", help="发布到抖音")
    p_post.add_argument("images", nargs="+", help="图片文件")
    p_post.add_argument("-t", "--title", default="", help="标题")
    p_post.add_argument("-d", "--description", default="", help="描述")
    p_post.add_argument("-m", "--music", help="选择音乐")
    p_post.add_argument("--hotspot", help="关联热点")
    p_post.add_argument("--debug", action="store_true", help="调试模式")

    args = parser.parse_args()

    if args.cmd == "cover":
        cmd_cover(args)
    elif args.cmd == "music":
        cmd_music(args)
    elif args.cmd == "post":
        cmd_post(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
