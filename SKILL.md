---
name: xhs-tikhub-feishu-ingest
description: Collect Xiaohongshu/RedNote note data through TikHub and append it into Lucas's Feishu Base video-material table. Use when the user asks to采集/抓取/同步/入库小红书帖子 or videos into 飞书多维表格, especially with xhslink.com links, TikHub, note cover/video/subtitle data, interaction metrics, or requests to update this ingestion workflow/skill.
---

# XHS TikHub Feishu Ingest

## Purpose

Use this skill to turn one or more Xiaohongshu share links into local artifacts and Feishu Base records. Preserve raw TikHub responses, choose the correct cover, upload attachments, and always verify the final Feishu row.

## Current Target

Default to the existing Base unless the user asks for a new one:

- Base: `小红书视频素材库`
- URL: `https://scnitw8fqog4.feishu.cn/base/OHDKbmvo7aaqUlssdXncKTHCnDc`
- `base_token`: `OHDKbmvo7aaqUlssdXncKTHCnDc`
- Table: `视频笔记`
- `table_id`: `tbl1gfUEArDaQQun`

Expected fields:

- `视频标题`
- `作者`
- `视频封面` attachment
- `视频链接`
- `视频时长`
- `简介`
- `核心总结`
- `文字内容`
- `点赞量`
- `评论量`
- `收藏量`
- Optional legacy field: `视频文件本身` attachment. Keep existing attachments, but do not populate this by default.

If the user changes the Base, read its fields first with `lark-cli base +field-list` and adapt to real field names. Older notes may call the transcript field `视频的文字内容，基于字幕`; the current Base uses `文字内容`.

## Workflow

1. Create a local folder under:
   `/Users/lucas/Documents/国内自媒体运营/小红书笔记采集/xhslink_<code>`
2. Read TikHub config from `~/.codex/mcp/tikhub/tikhub.env`; do not print secrets.
3. Call TikHub App V2 detail endpoints with `share_text=<share link>`:
   - Try `/api/v1/xiaohongshu/app_v2/get_video_note_detail`.
   - If needed, try `/api/v1/xiaohongshu/app_v2/get_image_note_detail` or `get_mixed_note_detail`.
   - Save every response as `raw_<kind>.json`.
4. Select the real target note. If TikHub returns multiple candidates, pick the one matching the share link/title/author and ignore related candidates.
5. Write `note_metadata.json`, `note.md`, downloaded cover assets, `transcript_zh-CN.txt`, and `core_summary.txt`.
6. Create the Feishu record with text/number fields first.
7. Upload only the cover file with `lark-cli base +record-upload-attachment`.
8. Read the Feishu record back and verify field values and attachment names/tokens.

## Performance Rules

Keep quality, but avoid slow redundant work.

- Target runtime for one normal video: about 1-2 minutes after TikHub responds.
- Call `get_video_note_detail` first. Only call image/mixed detail endpoints if the video endpoint fails or returns no usable target note.
- Do not print large raw JSON, full transcripts, or full record payloads to the terminal. Save them to files and print short summaries only.
- Use one local extraction script to parse TikHub data, download `cover_original.webp`, download subtitles, create `transcript_zh-CN.txt`, generate `核心总结`, write the video link, and write metadata.
- Do not download or upload the video file by default. Use `share_info.link` / canonical Xiaohongshu URL in `视频链接` instead.
- Do not include `视频文件本身` in new-record payloads unless Lucas explicitly asks for a local video archive. Leaving that field empty is the expected fast path.
- Download independent assets in parallel when practical: cover and subtitles do not depend on each other.
- Do one final record readback after all writes, not repeated readbacks after every small step unless debugging.
- Cache stable Feishu IDs from this skill (`base_token`, `table_id`, common field IDs) and only list fields again when a write fails or the user changed the table.
- Add lightweight timing logs around TikHub request, local asset downloads, Feishu record create, attachment upload, and final verification when the user asks about speed.

## Field Mapping

- `视频标题`: TikHub `title`
- `作者`: `user.nickname`
- `视频链接`: canonical Xiaohongshu detail URL, preferably `share_info.link`; fall back to the original xhslink share URL
- `视频时长`: formatted duration such as `3:31`; derive from the selected video's duration fields
- `简介`: full TikHub `desc`, not a shortened summary
- `核心总结`: bullet-point summary of the video's core framework and key ideas, 300 Chinese characters or fewer
- `文字内容`: cleaned `zh-CN` subtitle text; use `source` subtitle if `zh-CN` is absent
- `点赞量`: `liked_count`
- `评论量`: `comments_count`
- `收藏量`: `collected_count`
- `视频封面`: correct cover file; see cover rules below
- `视频文件本身`: legacy attachment field; leave empty for new records unless the user explicitly asks to upload the video file

## Interaction Number Fields

Display interaction metrics as whole numbers.

- Configure `点赞量`, `评论量`, and `收藏量` as number fields with `precision: 0`.
- Do not show `.00` or `.0` in grid/card/detail views.
- When creating or repairing a Base, use number style `{"type":"plain","precision":0,"thousands_separator":false,"percentage":false}` for all three fields.
- Write integer values from TikHub counts; if TikHub returns strings, parse them to integers before creating the Feishu row.

## Candidate Selection

TikHub can return a list of related notes instead of only the target note.

- Treat the first usable item as a candidate, not proof. Confirm it has the expected note id, title, author, or canonical `share_info.link` for the submitted xhslink.
- If there are several candidates, choose the one whose `share_info.link` or `note_id` corresponds to the share link. If the share link resolution is ambiguous, prefer the item whose title/author matches the opened target context.
- Save the full raw response before filtering so selection can be audited later.
- Put the chosen `note_id`, title, author, canonical link, and interaction counts into `note_metadata.json`.

## Duration

Capture each video's duration and write it to Feishu.

- Prefer `video_info_v2.media.video.duration` when present; it is usually seconds.
- If that is missing, use `widgets_context.video_duration` after parsing the JSON string.
- If only stream metadata is available, use `video_info_v2.media.stream.h264[0].duration` or another stream `duration`; treat values over 1000 as milliseconds and round to seconds.
- Store both `duration_seconds` and `duration_display` in `note_metadata.json`.
- Write `duration_display` to the Feishu `视频时长` field. Format under one hour as `M:SS`; format one hour or longer as `H:MM:SS`.

## Cover Rules

Be strict here. TikHub may return several image-like fields.

- Default to uploading `cover_original.webp` for the Feishu `视频封面` attachment.
- Generate `cover_original.webp` from the highest-resolution real single-image cover URL, preferably `images_list[0].original`.
- Use `images_list[0].url` only when `images_list[0].original` is absent or invalid.
- If only `share_info.image` is available, inspect its URL. It is often a low-resolution JPG such as `...?imageView2/2/w/360/format/jpg/q/75`.
- For low-resolution `share_info.image`, reconstruct a higher-resolution candidate from the same image id before uploading, for example:
  - Strip query parameters after the image id.
  - Try `?imageView2/2/w/5000/h/5000/format/webp/q/90`.
  - Verify dimensions with PIL before use.
- Save the reconstructed high-resolution candidate as `cover_original.webp`, then upload that file.
- Do not use `video_info_v2.image.thumbnail` when it is a multi-frame preview/contact-sheet image.
- If a thumbnail looks like a grid of many frames, it is wrong for `视频封面`; replace it with `share_cover.jpg`.
- After uploading, read the record back and check the attachment filename. The expected filename is `cover_original.webp`. Avoid keeping a blurry `share_cover.jpg` if a higher-resolution WebP can be generated from the same image id.

## Video And Subtitles

- Use `share_info.link` as the default watch link in `视频链接`.
- Do not download `video.mp4` or upload video attachments unless the user explicitly asks for local/video-file archival.
- If the user explicitly asks for the video file, prefer `video_info_v2.media.stream.h264[0].master_url` for `video.mp4`; use backup URLs on failure. Use H.264 over H.265 for compatibility with Feishu previews.
- Save subtitles from `video_info_v2.media.video.subtitles`.
- Convert SRT to clean text by removing indexes and timestamp lines, preserving sentence order.
- If no subtitles exist, leave `视频的文字内容，基于字幕` blank or explain that the note has no subtitle data.

## Core Summary

Always generate `核心总结` from the complete `文字内容` / subtitle transcript. Do not base it on `简介`; `简介` is often too short or marketing-oriented.

Requirements:

- Do not restate the title or separately extract generic "core points"; the title usually already covers that.
- Summarize the actual structure of the video and the useful content inside each part.
- Use numbered sections, not `框架一` / `框架二`.
- Keep it concise: no more than 300 Chinese characters.
- Write naturally, in plain spoken Chinese; avoid stiff report language.
- Make it scannable enough that Lucas can quickly understand what the video says and how it unfolds.
- Prefer this shape:
  - `1、<小标题>`
  - `<一句解释>`
  - `2、<小标题>`
  - `<一句解释>`
  - `3、<小标题>`
  - `<一句解释>`
  - `4、结论`
  - `<一句收束>`
- If the video has fewer meaningful parts, use fewer numbered sections plus a conclusion; do not pad.

## Feishu Commands

Use `lark-cli` with `--as user` by default.

Create row:

```bash
lark-cli base +record-batch-create --as user \
  --base-token OHDKbmvo7aaqUlssdXncKTHCnDc \
  --table-id tbl1gfUEArDaQQun \
  --json '{"fields":["视频标题","作者","视频链接","视频时长","简介","核心总结","文字内容","点赞量","评论量","收藏量"],"rows":[[...]]}'
```

Save this payload locally as `feishu_record_payload.json`, and save the creation response as `feishu_record_create.json`.

Upload attachments from the asset directory with relative paths:

```bash
lark-cli base +record-upload-attachment --as user \
  --base-token OHDKbmvo7aaqUlssdXncKTHCnDc \
  --table-id tbl1gfUEArDaQQun \
  --record-id <record_id> \
  --field-id "视频封面" \
  --file ./cover_original.webp
```

The attachment command rejects absolute file paths; `cd` into the asset folder first.

To fix a wrong attachment:

```bash
lark-cli base +record-remove-attachment --as user \
  --base-token OHDKbmvo7aaqUlssdXncKTHCnDc \
  --table-id tbl1gfUEArDaQQun \
  --record-id <record_id> \
  --field-id "视频封面" \
  --file-token <token> \
  --yes
```

Then upload the corrected file.

Read back the row once after all writes:

```bash
lark-cli base +record-get --as user \
  --base-token OHDKbmvo7aaqUlssdXncKTHCnDc \
  --table-id tbl1gfUEArDaQQun \
  --record-id <record_id> \
  --format json
```

Save the readback as `feishu_record_get.json`. The response shape is array-based: `data.fields` contains field names, `data.data[0]` contains values in the same order, and `data.record_id_list[0]` contains the record id. Build a name-to-value map from those arrays. Do not assume a `.data.record.fields` object exists.

## Verification Checklist

Before final response, verify and report:

- Record ID
- Title and author
- Like/comment/favorite counts
- Video duration
- `核心总结` exists and is no more than 300 Chinese characters
- Full `简介` length or trailing content if completeness was questioned
- Subtitle text exists when available
- `视频封面` has a single correct cover attachment
- `视频链接` exists and points to the canonical Xiaohongshu note URL
- `视频文件本身` is empty for normal runs unless the user explicitly requested video file archival
- Local folder path
- Feishu Base link: `https://scnitw8fqog4.feishu.cn/base/OHDKbmvo7aaqUlssdXncKTHCnDc`

## Final Response

After every successful ingestion, include both places Lucas needs next:

- Local folder path for the saved artifacts.
- Feishu Base link for opening the table.

Keep the final response concise. Mention the record id, title, author, interaction counts, video duration, the local folder path, and the Feishu Base link.

## Long Text Readability

Grid view is for scanning and will truncate long text cells. Do not treat this as missing data if record readback shows the full text.

- Keep the main grid compact for scanning.
- For reading long `简介` or `文字内容` fields, create or maintain a gallery/card view such as `详情阅读视图`.
- Set `视频封面` as the gallery cover field.
- Recommended visible field order: `视频标题`, `作者`, `视频封面`, `视频链接`, `视频时长`, `点赞量`, `评论量`, `收藏量`, `核心总结`, `简介`, `文字内容`, `视频文件本身`.
- If view configuration by field name fails, list fields and retry with field IDs.

## Record Detail Layout

When creating a new Feishu Base or rebuilding a table for this workflow, configure the record detail page with Lucas's custom layout. This layout is meant for clear per-video review and should be preserved once the user has manually tuned it.

Use this structure:

1. Large title header
   - Use `视频标题` as the record title.
   - Keep it visually prominent at the top, using the detail page's large title style.
2. Section: `视频基础信息`
   - Layout: four columns across the row.
   - Fields, left to right: `视频标题`, `作者`, `视频封面`, `视频链接`.
   - Use a readable medium-large value size for title/author.
   - Show the cover as a visual preview card.
   - Show `视频链接` as a clickable URL so Lucas can jump to Xiaohongshu to watch.
3. Section: `视频数据`
   - Layout: four columns.
   - Fields, left to right: `视频时长`, `评论量`, `收藏量`, `点赞量`.
   - Use number fields with clear labels and enough spacing. `评论量`, `收藏量`, and `点赞量` must display as integers without decimal places.
4. Section: `核心总结`
   - Layout: full-width or readable text block before the long transcript.
   - Main field: `核心总结`.
   - Use bullet points and a medium-large reading size.
   - Keep this section under 300 Chinese characters so it functions as a fast orientation layer.
5. Section: `视频详细内容`
   - Layout: full-width long text area.
   - Main field: `文字内容`.
   - Use a larger, comfortable reading size for long text.
   - Keep enough vertical spacing so the transcript can be scanned without opening tiny grid cells.
6. Optional section: `简介`
   - If the detail page feels crowded, keep `简介` either above `视频详细内容` as a full-width text block or inside `视频基础信息` only when it remains readable.

Do not overwrite an existing customized detail layout unless the user explicitly asks. If the CLI cannot configure every visual detail, document the desired layout in the final response and preserve the current user-customized setup.

## Maintenance Rule

When the user says to optimize, correct, or sync lessons back into this workflow, update this skill immediately. Add concrete constraints learned from the issue, especially around field mapping, cover selection, Feishu attachment behavior, or TikHub response quirks.
