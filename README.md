# 抖音发布工具

命令行工具，用于生成封面、TTS 音频并自动发布到抖音创作者平台。

## 安装

```bash
cd ~/douyin
uv sync
```

## 使用

### 生成封面

```bash
douyin cover "标题\n正文第一行\n正文第二行"
```

生成 1080x1920 黑底白字封面图，自动保存到 `data/` 目录。

### 生成 TTS 音频

```bash
douyin music "大家好，欢迎收看今天的内容"
```

使用 edge-tts 生成语音，保存为 `music.mp3`。

### 发布到抖音

```bash
# 基本发布
douyin post data/*/cover.png

# 完整参数
douyin post cover.png -t "标题" -d "描述文字" --hotspot "热点词"

# 不选择背景音乐
douyin post cover.png --no-music

# 调试模式（发布前暂停）
douyin post cover.png --debug
```

## 工作流程示例

```bash
# 1. 生成封面
douyin cover "今日分享\n三个提高效率的小技巧"

# 2. 生成配音（可选）
douyin music "大家好，今天分享三个提高效率的小技巧"

# 3. 发布
douyin post data/*/cover.png -t "效率技巧" -d "三个小技巧分享" --hotspot "效率"
```

## 注意事项

- 首次使用需要在弹出的 Chrome 中登录抖音创作者平台
- 登录状态会保存在 `.chrome/` 目录
- 发布前确保网络通畅
