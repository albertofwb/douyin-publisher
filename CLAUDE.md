# 抖音发布工具开发笔记

## 项目结构

```
~/douyin/
├── douyin             # Shell wrapper (调用 douyin.py)
├── douyin.py          # 主脚本入口 (cover/music/post)
├── gen_cover.py       # 封面图片生成模块
├── chrome_utils.py    # Chrome CDP 连接工具
├── pyproject.toml     # uv 项目配置
└── data/              # 帖子数据目录
    └── YYYYMMDD_HHMMSS_标题/
        ├── cover.png
        ├── music.mp3
        └── post.json
```

## 关键选择器 (抖音创作者平台)

| 功能 | 选择器 | 方法 |
|------|--------|------|
| 标题输入 | `[placeholder="添加作品标题"]` | `.fill()` |
| 描述输入 | `[contenteditable="true"]` | `keyboard.type()` |
| 图片上传 | `text=点击上传` | `expect_file_chooser()` + click |
| 关联热点 | `text=点击输入热点词` | click + `keyboard.type()` |
| 选择音乐 | `text=选择音乐` | click 打开侧边弹窗 |
| 使用音乐 | `button[class*="primary"]:has-text("使用")` | hover 显示后 click |
| 关闭弹窗 | `[class*="semi-icons-close"]` | click |
| 发布按钮 | `button:has-text("发布"):not(:has-text("高清"))` | click |

## 开发经验

### 1. 登录检测
- 不要用 `input[type="file"]` 检测登录状态
- 用 `[placeholder="添加作品标题"]` 更可靠

### 2. 文件上传
- 抖音用自定义上传组件，不是标准 `<input type="file">`
- 需要用 `page.expect_file_chooser()` 监听文件选择器事件

```python
with page.expect_file_chooser() as fc:
    page.locator('text=点击上传').first.click()
fc.value.set_files(image_paths)
```

### 3. 文本输入
- 标题框: 普通 input，用 `.fill()`
- 描述框: contenteditable div，用 `keyboard.type()` 更可靠

### 4. 热点关联
- 点击输入框后用 `keyboard.type()` 输入关键词
- 等待建议出现后点击第一个 `[class*="option"]`

### 5. 音乐选择
- 点击"选择音乐"打开侧边弹窗 `[class*="sidesheet"]`
- "使用"按钮默认隐藏，需要 hover 才显示
- 用 `mouse.move()` 模拟 hover，然后找可见的按钮点击
- 发布前需要先关闭音乐弹窗

### 6. 封面生成 (gen_cover.py)
- 1080x1920 黑底白字
- 第一行为标题（大字），后续为正文
- 自动换行，字体大小自适应
- 中文字体优先级: wqy-zenhei > wqy-microhei > NotoSansCJK

## 命令行参数

```bash
# cover - 生成封面
douyin cover "标题\n正文内容"

# music - 生成 TTS
douyin music "要说的话" [--voice VOICE]

# post - 发布
douyin post <images...> [-t TITLE] [-d DESC] [--hotspot WORD] [--music|--no-music] [--debug]
```

## 待实现

- [ ] 定时发布支持
- [ ] 上传本地音乐文件（目前只能选平台推荐音乐）
- [ ] 多账号支持

## Chrome CDP 连接

项目通过 CDP 连接到已登录的 Chrome 浏览器，避免重复登录：
- CDP 端口: 9222
- 用户数据目录: `.chrome/`
- `chrome_utils.py` 负责启动/连接 Chrome
