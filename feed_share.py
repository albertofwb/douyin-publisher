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

# 视频发布 URL（发布视频 tab）
DOUYIN_VIDEO_URL = "https://creator.douyin.com/creator-micro/content/upload"


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


def gen_cover(title: str, post_dir: Path, with_title: bool = False) -> Path:
    """生成封面图片
    
    Args:
        title: 标题文字
        post_dir: 输出目录
        with_title: 是否在封面上显示标题（默认否，让字幕作为唯一文字）
    """
    from PIL import Image
    output = post_dir / "cover.png"
    
    if with_title:
        from gen_cover import gen_cover as _gen_cover
        _gen_cover(title, output)
    else:
        # 纯黑背景，不带文字
        img = Image.new("RGB", (1080, 1920), color=(0, 0, 0))
        img.save(str(output))
    
    return output


def gen_audio(text: str, output: Path, voice: str = DEFAULT_VOICE) -> bool:
    """生成 TTS 音频"""
    cmd = ["edge-tts", "--text", text, "--voice", voice, "--write-media", str(output)]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ TTS 失败: {result.stderr}", file=sys.stderr)
        return False
    
    return True


def gen_subtitles_whisper(audio: Path, output: Path, max_chars: int = 20) -> bool:
    """用 Whisper 生成精确字级字幕
    
    Args:
        audio: 音频文件路径
        output: 输出 SRT 文件路径
        max_chars: 每行最大字符数
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("⚠️ faster-whisper 未安装，回退到 edge-tts 字幕", file=sys.stderr)
        return False
    
    # 加载模型
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio), language="zh", word_timestamps=True)
    
    # 收集所有词
    words = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                words.append({
                    'text': w.word.strip(),
                    'start': w.start,
                    'end': w.end
                })
    
    if not words:
        return False
    
    # 按字符数分组
    def format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    
    srt_blocks = []
    block_num = 1
    current_text = ""
    current_start = None
    current_end = None
    
    for word in words:
        if not word['text']:
            continue
            
        if current_start is None:
            current_start = word['start']
        
        # 检查是否需要换行
        if len(current_text) + len(word['text']) > max_chars and current_text:
            # 保存当前行
            srt_blocks.append(
                f"{block_num}\n{format_time(current_start)} --> {format_time(current_end)}\n{current_text}"
            )
            block_num += 1
            current_text = word['text']
            current_start = word['start']
        else:
            current_text += word['text']
        
        current_end = word['end']
    
    # 保存最后一行
    if current_text:
        srt_blocks.append(
            f"{block_num}\n{format_time(current_start)} --> {format_time(current_end)}\n{current_text}"
        )
    
    output.write_text('\n\n'.join(srt_blocks), encoding='utf-8')
    return True


def vtt_to_srt(vtt_path: Path, srt_path: Path, max_chars_per_line: int = 20):
    """将 VTT 字幕转换为 SRT 格式，自动分行长文本
    
    Args:
        vtt_path: VTT 字幕文件路径
        srt_path: 输出 SRT 文件路径
        max_chars_per_line: 每行最大字符数
    """
    import re
    
    content = vtt_path.read_text(encoding='utf-8')
    
    # 移除 VTT 头部和空行
    lines = content.split('\n')
    lines = [l for l in lines if l.strip() and not l.startswith('WEBVTT')]
    
    def parse_time(time_str: str) -> float:
        """解析时间字符串为秒数"""
        time_str = time_str.replace(',', '.')
        parts = time_str.split(':')
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    
    def format_time(seconds: float) -> str:
        """格式化秒数为 SRT 时间格式"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    
    def split_text(text: str, max_chars: int) -> list[str]:
        """将长文本分割成多行"""
        if len(text) <= max_chars:
            return [text]
        
        # 按标点分割优先
        segments = []
        current = ""
        for char in text:
            current += char
            if char in '，。！？、；：' and len(current) >= max_chars // 2:
                segments.append(current)
                current = ""
        if current:
            segments.append(current)
        
        # 如果还是太长，强制分割
        result = []
        for seg in segments:
            while len(seg) > max_chars:
                result.append(seg[:max_chars])
                seg = seg[max_chars:]
            if seg:
                result.append(seg)
        
        return result if result else [text]
    
    # 解析字幕块
    raw_subtitles = []
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        if line.isdigit():
            i += 1
            continue
        
        if '-->' in line:
            time_line = re.sub(r'(\d{2}:\d{2}:\d{2})\.(\d{3})', r'\1,\2', line)
            times = time_line.split(' --> ')
            start_time = parse_time(times[0])
            end_time = parse_time(times[1])
            
            text_lines = []
            i += 1
            while i < len(lines) and '-->' not in lines[i] and not lines[i].strip().isdigit():
                if lines[i].strip():
                    text_lines.append(lines[i].strip())
                i += 1
            
            if text_lines:
                text = ' '.join(text_lines)
                raw_subtitles.append({
                    'start': start_time,
                    'end': end_time,
                    'text': text
                })
        else:
            i += 1
    
    # 分割长字幕
    srt_blocks = []
    block_num = 1
    
    for sub in raw_subtitles:
        text_parts = split_text(sub['text'], max_chars_per_line)
        duration = sub['end'] - sub['start']
        time_per_part = duration / len(text_parts)
        
        for j, part in enumerate(text_parts):
            start = sub['start'] + j * time_per_part
            end = sub['start'] + (j + 1) * time_per_part - 0.05  # 小间隔
            
            srt_blocks.append(f"{block_num}\n{format_time(start)} --> {format_time(end)}\n{part}")
            block_num += 1
    
    srt_path.write_text('\n\n'.join(srt_blocks), encoding='utf-8')


def gen_subtitles(text: str, duration: float, output: Path) -> Path:
    """生成 SRT 字幕文件
    
    简单策略：按句子分割，均匀分配时间
    """
    import re
    
    # 按句子分割（中文句号、问号、感叹号、换行）
    sentences = re.split(r'[。！？\n]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        sentences = [text]
    
    # 计算每句时间
    time_per_sentence = duration / len(sentences)
    
    srt_content = []
    for i, sentence in enumerate(sentences):
        start_time = i * time_per_sentence
        end_time = (i + 1) * time_per_sentence - 0.1  # 留一点间隔
        
        # 格式化时间 HH:MM:SS,mmm
        def format_time(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        
        srt_content.append(f"{i + 1}")
        srt_content.append(f"{format_time(start_time)} --> {format_time(end_time)}")
        srt_content.append(sentence)
        srt_content.append("")
    
    output.write_text('\n'.join(srt_content), encoding='utf-8')
    return output


def gen_video(image: Path, audio: Path, output: Path, subtitles: Path = None) -> bool:
    """合成视频（静态图片 + 音频 + 可选字幕）"""
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
    
    # 构建 ffmpeg 命令
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image),
        "-i", str(audio),
    ]
    
    # 如果有字幕，添加字幕滤镜
    if subtitles and subtitles.exists():
        # 复制字幕到临时文件（避免中文路径问题）
        import shutil
        import tempfile
        temp_srt = Path(tempfile.gettempdir()) / "temp_subtitles.srt"
        shutil.copy(subtitles, temp_srt)
        
        # 字幕样式：居中，白色大字，黑色描边
        # 注意：路径中的特殊字符需要转义
        srt_path_escaped = str(temp_srt).replace('\\', '/').replace(':', '\\:')
        subtitle_filter = (
            f"subtitles={srt_path_escaped}:force_style='"
            f"FontSize=48,"
            f"FontName=Noto Sans CJK SC,"
            f"PrimaryColour=&HFFFFFF,"
            f"OutlineColour=&H000000,"
            f"Outline=3,"
            f"Shadow=1,"
            f"Alignment=5,"  # 5=居中（屏幕正中央）
            f"MarginL=0,MarginR=0,MarginV=0'"  # 清除所有边距
        )
        cmd.extend(["-vf", subtitle_filter])
    
    cmd.extend([
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-t", str(duration),
        str(output)
    ])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ 视频生成失败: {result.stderr}", file=sys.stderr)
        return False
    
    return True


def get_audio_duration(audio: Path) -> float:
    """获取音频时长"""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True
    )
    if probe.returncode == 0:
        return float(probe.stdout.strip())
    return 0.0


def post_video(video: Path, title: str, description: str = "", hotspot: str = "", debug: bool = False) -> bool:
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
            time.sleep(3)

            # 确保在「发布视频」tab
            try:
                video_tab = page.locator('text=发布视频').first
                if video_tab.count() > 0:
                    video_tab.click()
                    time.sleep(1)
            except:
                pass

            # 等待上传按钮出现
            try:
                page.wait_for_selector('text=上传视频', timeout=15000)
            except PlaywrightTimeout:
                # 尝试其他选择器
                try:
                    page.wait_for_selector('text=点击上传', timeout=5000)
                except PlaywrightTimeout:
                    print("❌ 请先登录抖音创作者平台", file=sys.stderr)
                    return False

            # 上传视频 - 找到文件输入框
            print(f"📤 上传视频: {video.name}")
            
            # 方法1: 直接找 file input
            file_input = page.locator('input[type="file"][accept*="video"]')
            if file_input.count() > 0:
                file_input.set_input_files(str(video))
            else:
                # 方法2: 点击上传按钮触发 file chooser
                upload_btn = page.locator('text=上传视频').first
                if upload_btn.count() == 0:
                    upload_btn = page.locator('text=点击上传').first
                
                with page.expect_file_chooser() as fc:
                    upload_btn.click()
                fc.value.set_files(str(video))
            
            # 等待上传完成
            print("⏳ 等待上传...")
            
            # 等待进度条消失或标题输入框出现
            max_wait = 180  # 最多等 3 分钟
            waited = 0
            while waited < max_wait:
                # 检查是否有标题输入框（上传完成的标志）
                title_input = page.locator('[placeholder*="标题"], [placeholder*="作品标题"]')
                if title_input.count() > 0 and title_input.first.is_visible():
                    print("✅ 上传完成")
                    break
                
                # 检查是否有错误提示
                error = page.locator('text=上传失败')
                if error.count() > 0 and error.first.is_visible():
                    print("❌ 上传失败", file=sys.stderr)
                    return False
                
                time.sleep(2)
                waited += 2
                if waited % 10 == 0:
                    print(f"   已等待 {waited}s...")
            
            if waited >= max_wait:
                print("❌ 上传超时", file=sys.stderr)
                return False
            
            time.sleep(2)

            # 填写标题
            if title:
                print(f"✍️ 填写标题: {title[:30]}...")
                title_input = page.locator('[placeholder*="标题"], [placeholder*="作品标题"]').first
                title_input.fill(title[:30])  # 抖音标题限制
                time.sleep(0.5)

            # 填写描述（在编辑框中）
            if description:
                print("✍️ 填写描述...")
                # 抖音的描述在 contenteditable div 中
                editor = page.locator('[contenteditable="true"]').first
                if editor.count() > 0:
                    editor.click()
                    # 清空现有内容
                    page.keyboard.press("Control+a")
                    page.keyboard.press("Delete")
                    time.sleep(0.3)
                    # 输入新内容（限制长度）
                    page.keyboard.type(description[:500])
                    time.sleep(0.5)

            # 关联热点
            if hotspot:
                try:
                    print(f"🔥 关联热点: {hotspot}")
                    hotspot_input = page.locator('text=点击输入热点词, text=添加热点')
                    if hotspot_input.count() > 0:
                        hotspot_input.first.click()
                        time.sleep(1)
                        page.keyboard.type(hotspot)
                        time.sleep(2)
                        # 选择第一个热点选项
                        option = page.locator('[class*="option"], [class*="item"]').first
                        if option.count() > 0:
                            option.click()
                            time.sleep(1)
                except Exception as e:
                    print(f"⚠️ 热点关联失败: {e}")

            if debug:
                print("🔍 调试模式 - 按 Enter 继续发布...")
                input()

            # 发布
            print("🚀 发布中...")
            # 找发布按钮（不是高清发布）
            publish_btn = page.locator('button:has-text("发布"):not(:has-text("高清"))')
            if publish_btn.count() == 0:
                publish_btn = page.locator('button:has-text("发布")')
            
            publish_btn.first.click(timeout=10000)
            time.sleep(5)
            
            # 检查是否发布成功
            success_indicator = page.locator('text=发布成功, text=作品已发布')
            if success_indicator.count() > 0:
                print("✅ 发布成功！")
            else:
                print("✅ 已点击发布（请检查是否成功）")
            
            return True

        except Exception as e:
            print(f"❌ 发布失败: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
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
    parser.add_argument("--debug", action="store_true", help="调试模式（发布前暂停）")
    
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
    
    # 3. 用 Whisper 生成字级字幕
    print("📝 生成字幕 (Whisper)...")
    subtitles = post_dir / "subtitles.srt"
    if not gen_subtitles_whisper(audio, subtitles):
        print("   ⚠️ Whisper 失败，使用备用方案")
        # 备用：用 edge-tts 的字幕
        vtt = post_dir / "subtitles.vtt"
        subprocess.run(["edge-tts", "--text", content, "--voice", args.voice, 
                       "--write-media", "/dev/null", "--write-subtitles", str(vtt)],
                      capture_output=True)
        if vtt.exists():
            vtt_to_srt(vtt, subtitles)
    print(f"   字幕: {subtitles}")
    
    # 4. 合成视频（带字幕）
    print("🎬 合成视频...")
    video = post_dir / "video.mp4"
    if not gen_video(cover, audio, video, subtitles):
        sys.exit(1)
    print(f"   视频: {video}")
    
    # 5. 发布（如果指定）
    if args.post:
        print("\n📤 开始发布...")
        success = post_video(video, title, content[:100], args.hotspot, debug=args.debug)
        sys.exit(0 if success else 1)
    else:
        print(f"\n✅ 视频已生成: {video}")
        print("   使用 --post 参数自动发布")


if __name__ == "__main__":
    main()
