# XHS TikHub Feishu Ingest

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

## 运行要求

- Python 3.9 或更高版本。
- 可用的 TikHub API Key。
- 需要飞书同步时，安装并登录 `lark-cli`。

安装飞书命令行工具：

```bash
npm install -g @larksuite/cli
lark-cli auth login
```

## 五分钟开始

1. 获取项目：

```bash
git clone https://github.com/glanderness/xhs-tikhub-feishu-ingest.git
cd xhs-tikhub-feishu-ingest
```

2. 创建用户配置：

```bash
./xhs-ingest init
```

默认配置位置：

```text
~/.config/xhs-tikhub-feishu-ingest/config.toml
```

3. 设置 TikHub API Key：

```bash
export TIKHUB_API_KEY="your-api-key"
```

需要长期使用时，可以把环境变量写入自己的终端配置。程序只检查是否已配置，不会在诊断结果中显示具体值。

4. 先检查本地保存模式：

```bash
./xhs-ingest doctor --skip-feishu
```

5. 采集一条笔记并仅保存到本地：

```bash
./xhs-ingest run "http://xhslink.com/o/example" --skip-feishu
```

默认输出目录为：

```text
~/xhs-ingest-output
```

## 启用飞书同步

确认 `lark-cli auth login` 已完成，然后运行：

```bash
./xhs-ingest setup-feishu
./xhs-ingest doctor
```

`setup-feishu` 会：

1. 创建或识别“小红书视频素材库”。
2. 创建或识别“对标博主”表。
3. 创建或识别“视频笔记”表。
4. 补齐必需字段和作者关联字段。
5. 创建“表格视图”和“卡片视图”。
6. 把 Base 和两张表的 ID 写入本地配置。

只检查现有 Base、不进行改动：

```bash
./xhs-ingest setup-feishu --check
```

完成后可以直接同步：

```bash
./xhs-ingest run "http://xhslink.com/o/example"
```

## 配置

配置读取顺序为：

```text
命令参数 > 环境变量 > config.toml > 通用默认值
```

可以复制仓库中的 [config.example.toml](config.example.toml)，也可以使用 `./xhs-ingest init` 自动创建。

主要环境变量：

| 环境变量 | 用途 |
| --- | --- |
| `XHS_INGEST_CONFIG` | 指定配置文件路径 |
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
./xhs-ingest doctor --config /path/to/config.toml
./xhs-ingest run "<小红书链接>" --config /path/to/config.toml
```

## 命令说明

### `init`

创建配置文件和输出目录。已有配置默认不会被覆盖。

```bash
./xhs-ingest init --output-root ~/Documents/xhs-materials
```

### `doctor`

检查 Python、配置文件、输出目录、TikHub 配置、飞书命令和飞书表格信息。

```bash
./xhs-ingest doctor
./xhs-ingest doctor --json
```

### `setup-feishu`

创建或补齐飞书数据结构。重复运行时会优先复用现有表和字段。

```bash
./xhs-ingest setup-feishu
./xhs-ingest setup-feishu --check
```

### `run`

处理一条小红书分享内容。

```bash
./xhs-ingest run "<分享链接或分享文字>"
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

确认当前终端已经设置：

```bash
export TIKHUB_API_KEY="your-api-key"
```

也可以在个人 `config.toml` 的 `[tikhub]` 区域填写，但不要提交包含个人配置的文件。

### 只想保存本地文件

所有 `doctor` 和 `run` 命令都可以使用 `--skip-feishu`。

### 已经有自己的飞书 Base

在 `config.toml` 中填写 Base 和表格 ID，再执行：

```bash
./xhs-ingest setup-feishu --check
```

如果字段缺失，去掉 `--check` 后再次运行即可补齐。

### 为什么默认不保存视频文件

下载和上传完整视频会明显增加执行时间和存储空间。项目默认保存可点击的视频链接，需要本地归档时再单独扩展。

## Codex Skill

仓库本身就是一个 Codex Skill。安装到 Codex Skill 目录后，可以直接用自然语言提出：

```text
用 xhs-tikhub-feishu-ingest 采集这条小红书链接并同步到我的飞书 Base。
```

`SKILL.md` 保存 Agent 执行规则，`scripts/` 保存可重复运行的确定性程序。命令行工具和 Skill 使用同一套配置与字段规则。

## 使用说明

请只处理你有权访问和保存的内容，并遵守 TikHub、小红书和飞书各自的服务规则。项目不会替你判断内容授权范围，公开分享、再次发布或商业使用前请自行确认相关要求。

## License

[MIT License](LICENSE)
