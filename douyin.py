#!/usr/bin/env python3
"""抖音发布工具 - 封面生成、TTS音乐、发布"""

import argparse
import random
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DOUYIN_POST_URL = "https://creator.douyin.com/creator-micro/content/post/image?enter_from=publish_page&media_type=image&type=new"


# === Cover ===
def cmd_cover(args):
    from gen_cover import gen_cover
    output = gen_cover(args.text)
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
                    time.sleep(3)
                    panel = page.locator('[class*="sidesheet"]').first
                    idx = random.randint(0, 4)
                    # Hover on the music item to reveal button
                    use_btn = panel.locator('text=使用').nth(idx)
                    box = use_btn.bounding_box()
                    if box:
                        cx, cy = box['x'] + box['width']/2, box['y'] + box['height']/2
                        page.mouse.move(cx - 20, cy)
                        time.sleep(0.3)
                        page.mouse.move(cx, cy)
                        time.sleep(0.5)
                        page.mouse.move(cx + 5, cy + 2)
                        time.sleep(2)
                    # Find and click the visible button
                    btns = page.locator('button[class*="primary"]:has-text("使用")').all()
                    for btn in btns:
                        if btn.is_visible():
                            btn.click()
                            print(f"已选择第 {idx + 1} 个音乐")
                            break
                    time.sleep(2)
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
                # Close any open panel first (click X button)
                close_btn = page.locator('[class*="semi-icons-close"]')
                if close_btn.count() > 0 and close_btn.first.is_visible():
                    close_btn.first.click()
                    time.sleep(1)
                # Click 发布 button (the one in header, not 高清发布)
                print("点击发布...")
                publish_btn = page.locator('button:has-text("发布"):not(:has-text("高清"))').first
                publish_btn.click(timeout=10000)
                time.sleep(3)
                print("已发布")

        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)


def cmd_share(args):
    """分享内容到抖音（自动去除敏感词，生成视频）"""
    import feed_share
    
    # 构建参数
    sys.argv = ['feed_share', args.title, args.content]
    if args.post:
        sys.argv.append('--post')
    if args.hotspot:
        sys.argv.extend(['--hotspot', args.hotspot])
    if args.voice:
        sys.argv.extend(['--voice', args.voice])
    
    feed_share.main()


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

    # post (图片)
    p_post = sub.add_parser("post", help="发布图片到抖音")
    p_post.add_argument("images", nargs="+", help="图片文件")
    p_post.add_argument("-t", "--title", default="", help="标题")
    p_post.add_argument("-d", "--description", default="", help="描述")
    p_post.add_argument("-m", "--music", nargs="?", const="auto", default="auto", help="选择音乐 (默认自动选择，--no-music 禁用)")
    p_post.add_argument("--no-music", dest="music", action="store_false", help="不选择音乐")
    p_post.add_argument("--hotspot", help="关联热点")
    p_post.add_argument("--debug", action="store_true", help="调试模式")

    # share (视频 - 从文字生成)
    p_share = sub.add_parser("share", help="分享内容到抖音（生成视频）")
    p_share.add_argument("title", help="视频标题")
    p_share.add_argument("content", help="视频内容（TTS 文本）")
    p_share.add_argument("--post", action="store_true", help="自动发布")
    p_share.add_argument("--hotspot", help="关联热点")
    p_share.add_argument("--voice", default=DEFAULT_VOICE, help="TTS 语音")

    args = parser.parse_args()

    if args.cmd == "cover":
        cmd_cover(args)
    elif args.cmd == "music":
        cmd_music(args)
    elif args.cmd == "post":
        cmd_post(args)
    elif args.cmd == "share":
        cmd_share(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
