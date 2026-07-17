# 小红书内容库 (XHS Library)

把一条小红书分享链接转换成结构化本地资料，并可选同步到飞书多维表格。

项目同时提供两种使用方式：

- 独立命令行工具：不依赖 Codex，也可以直接运行。
- Codex Skill：允许用户通过自然语言触发同一套流程。

## 能做什么

- 读取小红书短链接、完整链接或整段分享文字。
- 保存标题、作者、简介、发布时间、视频时长和互动数据。
- 下载原始 WebP 封面并保存字幕文本。
- 根据字幕生成不超过 300 字的核心总结草稿。
- 保存原始响应、结构化元数据、Markdown 笔记和执行报告。
- 可选同步到飞书多维表格。
- 自动创建飞书 Base、视频表、作者表、字段、关联和视图。
- 按小红书用户 ID 复用作者记录，并避免重复创建视频记录。

默认不会下载或上传视频文件，只在飞书中保存可打开的小红书链接。

## 一句话初始化

安装这个 Codex Skill 后，只需要对 Codex 说：

```text
开始初始化
```

Codex 会自动启动初始化。用户只需要依次完成两件事：

1. 在自动打开的流程中完成飞书本地 CLI 登录。
2. 注册 TikHub、创建 API Key，并在本地隐藏输入框中填入。

可以点击下方链接，完成 TikHub 注册：

[https://user.tikhub.io/register?ref=bW0RSDaJ](https://user.tikhub.io/register?ref=bW0RSDaJ)

注册完成后，请在 TikHub 创建 API Key，初始化程序会引导你把它填入本地隐藏输入框。

其余工作全部都自动完成：

- 创建本地配置和输出目录。
- 检查并自动安装飞书 CLI。
- 验证飞书登录状态和 TikHub API Key。
- 创建或复用飞书 Base、视频表和作者表。
- 创建字段、作者关联、表格视图和卡片视图。
- 保存 Base 与表格 ID。
- 运行完整诊断并返回飞书链接和本地目录。

TikHub API Key 只通过本地隐藏输入框采集，保存在用户本机，不会显示在聊天内容、诊断结果或初始化报告中。

## 命令行初始化

不使用 Codex 时，也只需要运行一个命令：

```bash
git clone https://github.com/glanderness/xhs-library.git
cd xhs-library
./xhs-library onboard
```

需要 Python 3.9 或更高版本。系统缺少 `lark-cli` 时，`onboard` 会通过 npm 自动安装。

初始化完成后直接采集：

```bash
./xhs-library run "http://xhslink.com/o/example"
```

默认输出目录：

```text
~/xhs-library
```

## 配置

配置读取顺序为：

```text
命令参数 > 环境变量 > config.toml > 通用默认值
```

通常不需要手动编辑配置。`./xhs-library onboard` 会自动创建并填写它。高级用户也可以复制 [config.example.toml](config.example.toml) 或单独运行 `./xhs-library init`。

旧版本的 `./xhs-ingest` 命令、`XHS_INGEST_CONFIG` 环境变量和 `~/.config/xhs-tikhub-feishu-ingest` 配置目录继续兼容；首次使用新名称时会自动迁移到 `~/.config/xhs-library`。

主要环境变量：

| 环境变量 | 用途 |
| --- | --- |
| `XHS_LIBRARY_CONFIG` | 指定配置文件路径 |
| `XHS_LIBRARY_ROOT` | 指定本地内容库目录 |
| `TIKHUB_API_KEY` | TikHub API Key |
| `TIKHUB_BASE_URL` | TikHub API 地址 |
| `TIKHUB_ENV_FILE` | 兼容已有 TikHub env 文件 |
| `XHS_OUTPUT_ROOT` | 本地输出目录 |
| `FEISHU_BASE_TOKEN` | 飞书 Base 标识 |
| `FEISHU_VIDEO_TABLE_ID` | 视频表 ID |
| `FEISHU_CREATOR_TABLE_ID` | 作者表 ID |
| `FEISHU_BASE_URL` | 用户可打开的飞书 Base 链接 |

使用另一份配置：

```bash
./xhs-library doctor --config /path/to/config.toml
./xhs-library run "<小红书链接>" --config /path/to/config.toml
```

## 命令说明

### `onboard`

推荐的初始化入口。依次完成飞书登录和 TikHub API Key 输入，然后自动完成全部本地与飞书配置。

```bash
./xhs-library onboard
```

### `init`

仅创建配置文件和输出目录，主要用于高级配置。已有配置默认不会被覆盖。

```bash
./xhs-library init --output-root ~/Documents/xhs-materials
```

### `doctor`

检查 Python、配置文件、输出目录、TikHub 配置、飞书命令和飞书表格信息。

```bash
./xhs-library doctor
./xhs-library doctor --json
```

### `setup-feishu`

创建或补齐飞书数据结构。重复运行时会优先复用现有表和字段。

```bash
./xhs-library setup-feishu
./xhs-library setup-feishu --check
```

### `run`

处理一条小红书分享内容。

```bash
./xhs-library run "<分享链接或分享文字>"
```

常用选项：

- `--skip-feishu`：仅保存本地文件。
- `--expected-title`：在多个候选结果中提供标题提示。
- `--expected-author`：提供作者提示。
- `--summary-file`：使用人工整理的核心总结。
- `--summary-text`：直接传入核心总结。
- `--force-create`：即使发现相同记录也创建新行。

旧入口仍可使用：

```bash
python3 scripts/ingest_xhs_note.py "<小红书链接>" --skip-feishu
```

## 本地输出

每条笔记会生成独立目录，通常包含：

```text
raw_video.json
note_metadata.json
note.md
transcript_zh-CN.txt
core_summary.txt
ingest_report.json
assets/cover_original.webp
assets/subtitle_*.srt
```

同步飞书后还会保存创建结果和最终读取结果，便于核对字段是否完整。

## 飞书数据结构

视频表默认包含：

- 视频标题、作者、视频封面、视频链接。
- 视频时长、发布时间、简介、核心总结、文字内容。
- 点赞量、评论量、收藏量。

作者表默认包含：

- 博主名称、小红书用户 ID、小红书号、主页链接。
- 头像、简介、主页背景图。
- 粉丝量、获赞和收藏量、最近更新时间。

作者优先按小红书用户 ID 识别，其次使用小红书号，最后才使用博主名称。

## 常见问题

### `doctor` 提示没有 TikHub API Key

还没有 TikHub 账号时，请通过项目作者推荐链接 [注册 TikHub](https://user.tikhub.io/register?ref=bW0RSDaJ)。注册并创建 API Key 后，重新运行 `./xhs-library onboard`，在本地隐藏输入框中填写。高级用户仍可使用 `TIKHUB_API_KEY` 环境变量。

### 只想保存本地文件

所有 `doctor` 和 `run` 命令都可以使用 `--skip-feishu`。

### 已经有自己的飞书 Base

在 `config.toml` 中填写 Base 和表格 ID，再执行：

```bash
./xhs-library setup-feishu --check
```

如果字段缺失，去掉 `--check` 后再次运行即可补齐。

### 为什么默认不保存视频文件

下载和上传完整视频会明显增加执行时间和存储空间。项目默认保存可点击的视频链接，需要本地归档时再单独扩展。

## Codex Skill

仓库本身就是一个 Codex Skill。安装到 Codex Skill 目录后，可以直接用自然语言提出：

```text
开始初始化
```

初始化完成后，可以继续提出：

```text
用 xhs-library 采集这条小红书链接并同步到我的飞书 Base。
```

`SKILL.md` 保存 Agent 执行规则，`scripts/` 保存可重复运行的确定性程序。命令行工具和 Skill 使用同一套配置与字段规则。

## 使用说明

请只处理你有权访问和保存的内容，并遵守 TikHub、小红书和飞书各自的服务规则。项目不会替你判断内容授权范围，公开分享、再次发布或商业使用前请自行确认相关要求。

## License

[MIT License](LICENSE)
