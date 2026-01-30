#!/usr/bin/env python3
"""
分享有趣内容到抖音 - 从刷推/论坛内容生成视频并发布

流程:
1. 接收内容摘要（已去除敏感词）
2. 生成封面图片
3. 生成 TTS 语音
4. 合成视频（图片 + 音频）
5. 发布到抖音

用法:
  feed_share.py "标题" "正文内容..." [--post]
  feed_share.py --from-file summary.txt [--post]
"""

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# 视频发布 URL
DOUYIN_VIDEO_URL = "https://creator.douyin.com/creator-micro/content/upload?enter_from=publish_page"


def sanitize_dirname(text: str, max_len: int = 40) -> str:
    """生成安全的目录名"""
    text = text.split("\n")[0].strip()
    text = re.sub(r'[<>:"/\\|?*\s]', '_', text)
    text = re.sub(r'_+', '_', text)
    return text[:max_len].strip('_')


def sanitize_content(text: str) -> str:
    """去除敏感词汇（推特/Twitter 等）"""
    replacements = {
        r'推特': '某平台',
        r'Twitter': '某平台',
        r'X\.com': '某平台',
        r'tweet': '帖子',
        r'推文': '帖子',
        r'@\w+': '',  # 移除 @用户名
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def gen_cover(title: str, post_dir: Path) -> Path:
    """生成封面图片"""
    from gen_cover import gen_cover as _gen_cover
    output = post_dir / "cover.png"
    _gen_cover(title, output)
    return output


def gen_audio(text: str, output: Path, voice: str = DEFAULT_VOICE) -> bool:
    """生成 TTS 音频"""
    result = subprocess.run(
        ["edge-tts", "--text", text, "--voice", voice, "--write-media", str(output)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"❌ TTS 失败: {result.stderr}", file=sys.stderr)
        return False
    return True


def gen_video(image: Path, audio: Path, output: Path) -> bool:
    """合成视频（静态图片 + 音频）"""
    # 获取音频时长
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True
    )
    if probe.returncode != 0:
        print(f"❌ 无法获取音频时长", file=sys.stderr)
        return False
    
    duration = float(probe.stdout.strip())
    
    # 生成视频：图片循环 + 音频
    result = subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image),
        "-i", str(audio),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-t", str(duration),
        str(output)
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ 视频生成失败: {result.stderr}", file=sys.stderr)
        return False
    
    return True


def post_video(video: Path, title: str, description: str = "", hotspot: str = "") -> bool:
    """发布视频到抖音"""
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    from chrome_utils import CDP_URL, ensure_chrome_cdp

    if not ensure_chrome_cdp():
        return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"❌ 无法连接 CDP: {e}", file=sys.stderr)
            return False

        page = browser.contexts[0].new_page()

        try:
            print("📍 打开抖音创作者平台...")
            page.goto(DOUYIN_VIDEO_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # 等待上传区域
            try:
                page.wait_for_selector('text=点击上传', timeout=15000)
            except PlaywrightTimeout:
                print("❌ 请先登录抖音创作者平台", file=sys.stderr)
                return False

            # 上传视频
            print(f"📤 上传视频: {video.name}")
            upload_area = page.locator('text=点击上传').first
            with page.expect_file_chooser() as fc:
                upload_area.click()
            fc.value.set_files(str(video))
            
            # 等待上传完成（可能需要较长时间）
            print("⏳ 等待上传...")
            time.sleep(10)
            
            # 等待标题输入框出现（表示上传完成）
            try:
                page.wait_for_selector('[placeholder*="标题"]', timeout=120000)
            except PlaywrightTimeout:
                print("❌ 上传超时", file=sys.stderr)
                return False
            
            time.sleep(2)

            # 填写标题
            if title:
                print(f"✍️ 填写标题: {title[:20]}...")
                title_input = page.locator('[placeholder*="标题"]').first
                title_input.fill(title)
                time.sleep(0.5)

            # 填写描述
            if description:
                print("✍️ 填写描述...")
                editor = page.locator('[contenteditable="true"]').first
                if editor.count() > 0:
                    editor.click()
                    page.keyboard.type(description)
                    time.sleep(0.5)

            # 关联热点
            if hotspot:
                try:
                    print(f"🔥 关联热点: {hotspot}")
                    hotspot_btn = page.locator('text=点击输入热点词').first
                    hotspot_btn.click()
                    time.sleep(1)
                    page.keyboard.type(hotspot)
                    time.sleep(2)
                    page.locator('[class*="option"]').first.click()
                    time.sleep(1)
                except Exception as e:
                    print(f"⚠️ 热点关联失败: {e}")

            # 发布
            print("🚀 发布中...")
            publish_btn = page.locator('button:has-text("发布")').first
            publish_btn.click(timeout=10000)
            time.sleep(5)
            
            print("✅ 发布成功！")
            return True

        except Exception as e:
            print(f"❌ 发布失败: {e}", file=sys.stderr)
            return False
        finally:
            page.close()


def main():
    parser = argparse.ArgumentParser(
        description="分享内容到抖音（自动去除敏感词）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  feed_share "今日热点" "今天在某论坛看到几个有趣的帖子..."
  feed_share "科技分享" "有人分享了一个AI项目..." --post
  feed_share --from-file summary.txt --post
        """
    )
    
    parser.add_argument("title", nargs="?", help="视频标题")
    parser.add_argument("content", nargs="?", help="视频内容（TTS 文本）")
    parser.add_argument("--from-file", "-f", metavar="FILE", help="从文件读取内容")
    parser.add_argument("--post", action="store_true", help="自动发布（默认只生成不发布）")
    parser.add_argument("--hotspot", help="关联热点话题")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="TTS 语音")
    parser.add_argument("--no-sanitize", action="store_true", help="不过滤敏感词")
    
    args = parser.parse_args()
    
    # 读取内容
    if args.from_file:
        with open(args.from_file, 'r', encoding='utf-8') as f:
            lines = f.read().strip().split('\n', 1)
            title = lines[0]
            content = lines[1] if len(lines) > 1 else title
    elif args.title and args.content:
        title = args.title
        content = args.content
    else:
        parser.print_help()
        sys.exit(1)
    
    # 去除敏感词
    if not args.no_sanitize:
        title = sanitize_content(title)
        content = sanitize_content(content)
    
    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dirname = f"{timestamp}_{sanitize_dirname(title)}"
    post_dir = DATA_DIR / dirname
    post_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 输出目录: {post_dir}")
    
    # 1. 生成封面
    print("🎨 生成封面...")
    cover = gen_cover(title, post_dir)
    print(f"   封面: {cover}")
    
    # 2. 生成音频
    print("🎤 生成语音...")
    audio = post_dir / "audio.mp3"
    if not gen_audio(content, audio, args.voice):
        sys.exit(1)
    print(f"   音频: {audio}")
    
    # 3. 合成视频
    print("🎬 合成视频...")
    video = post_dir / "video.mp4"
    if not gen_video(cover, audio, video):
        sys.exit(1)
    print(f"   视频: {video}")
    
    # 4. 发布（如果指定）
    if args.post:
        print("\n📤 开始发布...")
        success = post_video(video, title, content[:100], args.hotspot)
        sys.exit(0 if success else 1)
    else:
        print(f"\n✅ 视频已生成: {video}")
        print("   使用 --post 参数自动发布")


if __name__ == "__main__":
    main()
