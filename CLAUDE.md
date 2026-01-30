# 抖音发布工具开发笔记

## 项目结构

```
~/douyin/
├── douyin             # Shell wrapper
├── douyin.py          # 主脚本 (cover/music/post)
├── chrome_utils.py    # Chrome CDP 连接工具
├── pyproject.toml     # uv 项目配置
└── data/              # 帖子数据目录
    └── YYYY-MM-DD HHMMSS 标题/
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
| 选择音乐 | `text=选择音乐` | click 打开弹窗 |

## 开发经验

### 1. 登录检测
- 不要用 `input[type="file"]` 检测登录状态
- 用 `[placeholder="添加作品标题"]` 更可靠

### 2. 文件上传
- 抖音用自定义上传组件，不是标准 `<input type="file">`
- 需要用 `page.expect_file_chooser()` 监听文件选择器事件
- 点击 `text=点击上传` 触发原生文件对话框

```python
with page.expect_file_chooser() as fc_info:
    page.locator('text=点击上传').click()
file_chooser = fc_info.value
file_chooser.set_files(image_paths)
```

### 3. 文本输入
- 标题框: 普通 input，用 `.fill()`
- 描述框: contenteditable div，用 `keyboard.type()` 更可靠

### 4. 热点关联
- 点击输入框后用 `keyboard.type()` 输入关键词
- 等待建议出现后点击第一个 `[class*="option"]`

## 待实现

- [ ] 音乐上传功能 (需要分析音乐选择弹窗结构)
- [ ] 自动发布 (点击发布按钮)
- [ ] 定时发布支持

## 使用示例

```bash
douyin cover "标题\n正文内容"                              # 生成封面
douyin music "大家好，欢迎收看"                            # 生成 TTS 音乐
douyin post data/*/cover.png -t "标题" -d "描述" --hotspot "热点"  # 发布
```
