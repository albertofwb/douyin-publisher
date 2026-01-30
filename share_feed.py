#!/usr/bin/env python3
"""
一键刷推分享到抖音

用法:
  share_feed                    # 抓取推特 → 选择内容 → 生成视频 → 发布
  share_feed --dry-run          # 只生成不发布
  share_feed --text "内容"      # 直接指定内容
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()


def fetch_feed() -> str | None:
    """调用 twfeed 抓取推特时间线"""
    print("📡 抓取推特时间线...")
    result = subprocess.run(
        ["twfeed", "--height", "4000"],
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        print(f"❌ 抓取失败: {result.stderr}", file=sys.stderr)
        return None
    return result.stdout.strip()


def parse_tweets(ocr_text: str) -> list[dict]:
    """从 OCR 文本解析推文"""
    tweets = []
    lines = ocr_text.split('\n')
    
    current_tweet = {"author": "", "content": []}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 检测用户名模式 (xxx @xxx · 时间)
        if '@' in line and ('·' in line or '•' in line or 'h' in line or 'm' in line):
            # 保存上一条推文
            if current_tweet["content"]:
                tweets.append(current_tweet)
            current_tweet = {"author": line, "content": []}
        elif current_tweet["author"]:
            # 跳过广告和无关内容
            skip_keywords = ['Ad', '广告', 'Promoted', 'Subscribe', '订阅', '关注', 'Follow']
            if not any(kw in line for kw in skip_keywords):
                current_tweet["content"].append(line)
    
    # 保存最后一条
    if current_tweet["content"]:
        tweets.append(current_tweet)
    
    return tweets


def sanitize_for_douyin(text: str) -> str:
    """去除敏感词"""
    import re
    replacements = {
        r'推特': '某平台',
        r'Twitter': '某平台',
        r'X\.com': '某平台',
        r'tweet': '帖子',
        r'推文': '帖子',
        r'@[\w]+': '',  # 移除 @用户名
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.strip()


def select_tweets(tweets: list[dict]) -> list[dict]:
    """交互式选择要分享的推文"""
    if not tweets:
        return []
    
    print(f"\n📋 找到 {len(tweets)} 条推文，选择要分享的：\n")
    
    for i, tweet in enumerate(tweets[:10], 1):  # 最多显示 10 条
        content = ' '.join(tweet['content'])[:80]
        print(f"  [{i}] {content}...")
    
    print(f"\n  [a] 全选前5条")
    print(f"  [q] 退出")
    
    try:
        choice = input("\n选择 (数字/a/q): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return []
    
    if choice == 'q':
        return []
    elif choice == 'a':
        return tweets[:5]
    else:
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(',')]
            return [tweets[i] for i in indices if 0 <= i < len(tweets)]
        except:
            return []


def generate_script(tweets: list[dict]) -> tuple[str, str]:
    """生成抖音视频的标题和文案"""
    if not tweets:
        return "", ""
    
    # 标题
    title = "今日网络见闻"
    
    # 文案（TTS 内容）
    lines = ["大家好，今天在网上看到几个有意思的事情，分享给大家。"]
    
    for i, tweet in enumerate(tweets, 1):
        content = sanitize_for_douyin(' '.join(tweet['content']))
        if content:
            lines.append(f"第{i}个，{content}")
    
    lines.append("好了，今天就分享到这里，觉得有意思的话点个赞吧！")
    
    script = '\n'.join(lines)
    return title, script


def main():
    parser = argparse.ArgumentParser(description="一键刷推分享到抖音")
    parser.add_argument("--text", "-t", help="直接指定分享内容")
    parser.add_argument("--title", default="今日见闻", help="视频标题")
    parser.add_argument("--dry-run", action="store_true", help="只生成不发布")
    parser.add_argument("--hotspot", help="关联热点")
    parser.add_argument("--no-fetch", action="store_true", help="不抓取，使用上次的内容")
    args = parser.parse_args()
    
    if args.text:
        # 直接使用指定内容
        title = args.title
        script = sanitize_for_douyin(args.text)
    else:
        # 抓取并选择
        ocr_text = fetch_feed()
        if not ocr_text:
            sys.exit(1)
        
        tweets = parse_tweets(ocr_text)
        if not tweets:
            print("❌ 未解析到有效推文")
            sys.exit(1)
        
        selected = select_tweets(tweets)
        if not selected:
            print("👋 已取消")
            sys.exit(0)
        
        title, script = generate_script(selected)
    
    print(f"\n📝 标题: {title}")
    print(f"📝 文案:\n{script[:200]}...")
    
    # 确认
    try:
        confirm = input("\n确认生成视频? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = 'n'
    
    if confirm == 'n':
        print("👋 已取消")
        sys.exit(0)
    
    # 调用 feed_share 生成并发布
    cmd = ["python3", str(SCRIPT_DIR / "feed_share.py"), title, script]
    if not args.dry_run:
        cmd.append("--post")
    if args.hotspot:
        cmd.extend(["--hotspot", args.hotspot])
    
    print("\n" + "="*50)
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
