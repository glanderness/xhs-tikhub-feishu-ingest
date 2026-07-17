---
name: xhs-tikhub-feishu-ingest
description: Collect Xiaohongshu/RedNote note data through TikHub, save local artifacts, and optionally append it into a user-configured Feishu Base. Use when the user asks to采集/抓取/同步/入库小红书帖子 or videos, configure TikHub or Feishu ingestion, create the required Base schema, or update this workflow/skill.
---

# XHS TikHub Feishu Ingest

## Purpose

Use this skill to turn one or more Xiaohongshu share links into local artifacts and Feishu Base records. Preserve raw TikHub responses, choose the correct cover, upload attachments, and always verify the final Feishu row.

## Configuration

Load configuration in this priority order: command options, environment variables, `config.toml`, then portable defaults. Use `~/.config/xhs-tikhub-feishu-ingest/config.toml` by default or pass `--config <path>`.

Use the repository's `config.example.toml` as the configuration template. Never commit a populated user configuration file.

The default names are:

- Base: `小红书视频素材库`
- Video table: `视频笔记`
- Creator table: `对标博主`

Expected fields:

- `视频标题`
- `作者` link to the `对标博主` table
- `视频封面` attachment
- `视频链接`
- `视频时长`
- `发布时间`
- `简介`
- `核心总结`
- `文字内容`
- `点赞量`
- `评论量`
- `收藏量`
- Optional legacy field: `视频文件本身` attachment. Keep existing attachments, but do not populate this by default.

If the user changes the Base, read its fields first with `lark-cli base +field-list` and adapt to real field names. Older notes may call the transcript field `视频的文字内容，基于字幕`; the current Base uses `文字内容`.

## Workflow

Use the unified command entry point:

```bash
./xhs-ingest init
./xhs-ingest doctor
./xhs-ingest setup-feishu
./xhs-ingest run "<XHS share link or full share text>"
```

Use `./xhs-ingest setup-feishu --check` to verify an existing Base without changing it. Run `setup-feishu` without `--check` to create missing tables, fields, and views, then save the resulting IDs into the selected local configuration file.

Keep `python scripts/ingest_xhs_note.py ...` as a backward-compatible direct ingestion entry point.

Useful options:

- `--expected-title "<title>"` and `--expected-author "<author>"` add candidate-selection hints.
- `--summary-text "<核心总结>"` or `--summary-file /path/to/core_summary.txt` overrides the script's automatic summary draft.
- `--skip-feishu` creates only local artifacts for debugging.
- `--force-create` creates a new video row even if the script finds a matching existing row.

The script creates/updates local artifacts, resolves the creator, writes or updates the Feishu video row, uploads `cover_original.webp`, reads the row back, and writes `ingest_report.json`. It also avoids duplicate rows by matching `视频链接`, `note_id`, or exact title. Creator reuse is ID-first: `小红书用户ID` -> `小红书号` -> exact `博主名称`.

The script is the unified subtitle parser. It must support both TikHub subtitle shapes: a list and a language-grouped object such as `{"zh-CN":[...],"source":[...]}`.

For production-quality ingestion, first run the script with `--skip-feishu` when needed, read `transcript_zh-CN.txt`, write a polished `core_summary.txt` according to the Core Summary rules, then rerun with `--summary-file <folder>/core_summary.txt`. The script's built-in summary is a fallback draft, not the preferred final summary when full subtitles are available.

Manual fallback workflow:

1. Create a local folder under the configured `output.root`, using `xhslink_<code>` or `xhs_<note_id>`.
2. Read TikHub configuration through `scripts/xhs_config.py`; do not print the API key.
3. Preserve the original user-provided `xhslink.com` short link, then call TikHub App V2 detail endpoints with `share_text=<share link>`:
   - Try `/api/v1/xiaohongshu/app_v2/get_video_note_detail`.
   - If needed, try `/api/v1/xiaohongshu/app_v2/get_image_note_detail` or `get_mixed_note_detail`.
   - Save every response as `raw_<kind>.json`.
4. Select the real target note. If TikHub returns multiple candidates, pick the one matching the share link/title/author and ignore related candidates.
5. Resolve the creator before creating the video row:
   - Search `对标博主` for the creator using `user.userid` when available; also check exact `博主名称` as a fallback.
   - If the creator already exists, reuse that creator record id for the video `作者` link field.
   - If the creator is new, call TikHub `/api/v1/xiaohongshu/app_v2/get_user_info?user_id=<id>`, create a new `对标博主` row, upload avatar/background attachments, then use the new record id.
6. Write `note_metadata.json`, `note.md`, downloaded cover assets, `transcript_zh-CN.txt`, and `core_summary.txt`.
   - Store both `original_share_link` and TikHub's `canonical_link` in `note_metadata.json`.
   - Store publish timing as `publish_time_raw`, `publish_time_cst`, and `publish_date`.
7. Create the Feishu video record with text/number/link fields first. `作者` must be `[{"id":"<creator_record_id>"}]`.
8. Upload only the cover file with `lark-cli base +record-upload-attachment`.
9. Read the Feishu record back and verify field values, linked author, and attachment names/tokens.

## Performance Rules

Keep quality, but avoid slow redundant work.

- Target runtime for one normal video: about 1-2 minutes after TikHub responds.
- Call `get_video_note_detail` first. Only call image/mixed detail endpoints if the video endpoint fails or returns no usable target note.
- Do not print large raw JSON, full transcripts, or full record payloads to the terminal. Save them to files and print short summaries only.
- Use `scripts/ingest_xhs_note.py` to parse TikHub data, download `cover_original.webp`, download subtitles, create `transcript_zh-CN.txt`, generate or accept `核心总结`, write the video link, and write metadata.
- Do not download or upload the video file by default. Use a browser-openable Xiaohongshu share URL in Feishu `视频链接` so the user can click through from the table.
- Do not include `视频文件本身` in new-record payloads unless the user explicitly asks for a local video archive. Leaving that field empty is the expected fast path.
- Download independent assets in parallel when practical: cover and subtitles do not depend on each other.
- Do one final record readback after all writes, not repeated readbacks after every small step unless debugging.
- Cache stable Feishu IDs in the user's local configuration and only list fields again when a write fails or the user changed the table.
- Add lightweight timing logs around TikHub request, local asset downloads, Feishu record create, attachment upload, and final verification when the user asks about speed.

## Field Mapping

- `视频标题`: TikHub `title`
- `作者`: link-cell value pointing to the creator record in `对标博主`, using `[{"id":"<creator_record_id>"}]`
- `视频链接`: browser-openable Xiaohongshu share URL. Prefer the original user-provided Xiaohongshu URL with `xsec_token` / `xsec_source`; if the input was an `xhslink.com` short link, write TikHub `share_info.link` / `canonical_link` after resolving. Use no-query `explore/<note_id>` only as a last resort.
- `视频时长`: formatted duration such as `3:31`; derive from the selected video's duration fields
- `发布时间`: date-only value from the note publish timestamp. Prefer TikHub selected note `time`; convert from Unix seconds to Asia/Shanghai date and write as `YYYY-MM-DD 00:00:00` for Feishu's date/datetime field.
- `简介`: full TikHub `desc`, not a shortened summary
- `核心总结`: bullet-point summary of the video's core framework and key ideas, 300 Chinese characters or fewer
- `文字内容`: cleaned `zh-CN` subtitle text; use `source` subtitle if `zh-CN` is absent
- `点赞量`: `liked_count`
- `评论量`: `comments_count`
- `收藏量`: `collected_count`
- `视频封面`: correct cover file; see cover rules below
- `视频文件本身`: legacy attachment field; leave empty for new records unless the user explicitly asks to upload the video file

## Video Link Policy

The Feishu `视频链接` field is for the user to click and watch the video in a browser. Openability beats visual cleanliness.

- Do not strip `xsec_token`, `xsec_source`, `app_platform`, `app_version`, `author_share`, `share_from_user_hidden`, or similar share-context parameters from Xiaohongshu URLs. Many notes show a QR-code page or "当前笔记暂时无法浏览" when opened as a bare `explore/<note_id>` URL.
- If the user provides a full Xiaohongshu share URL, write that original URL to Feishu.
- If the user provides an `xhslink.com/o/<code>` short link, resolve it through TikHub and write TikHub `share_info.link` / `canonical_link` to Feishu. Keep the original short link in `note_metadata.json` for audit.
- Use `https://www.xiaohongshu.com/explore/<note_id>` only when no contextual share URL is available.
- During final readback, inspect `视频链接`. If it is a bare no-query `explore/<note_id>` or `discovery/item/<note_id>`, update it to the original full share URL or TikHub canonical link before responding.

## Benchmark Creator Table

Keep creator-level analysis in a second table inside the same Feishu Base.

- Table name: `对标博主`
- Table id: use the configured `feishu.creator_table_id`
- Purpose: store creator profiles separately from individual video notes, then link video notes to the relevant creator through the `视频笔记`.`作者` link field.
- Required fields:
  - `博主名称`: text primary field
  - `小红书用户ID`: text stable user id from `user.userid` / `user.id`; use this as the first creator identity key
  - `小红书号`: text Red ID from `user.red_id` / profile `red_id`; use this as the second creator identity key
  - `主页链接`: text URL to the creator's Xiaohongshu profile
  - `头像`: attachment
  - `简介`: text
  - `主页背景图`: attachment
  - `粉丝量`: number, `precision: 0`
  - `获赞和收藏量`: number, `precision: 0`
  - `最近更新时间`: datetime, refreshed whenever the creator row is created or enriched
- Use integer display for creator metrics. Do not show `.00` or `.0`.
- For attachments, save avatar and background assets locally before uploading them to the record.
- In `视频笔记`, the visible `作者` field must be the link field to `对标博主`, not a plain text field.
- When creating or repairing the author link field on `视频笔记`, use Feishu's `link` field with `link_table`, for example `{"name":"作者","type":"link","link_table":"<creator_table_id>"}`. Do not use `table_id`; the field-create API rejects it for link fields.
- When writing a link-cell value, use `[{"id":"<creator_record_id>"}]`. Do not use `record_id` inside the cell value; Feishu rejects that shape.
- The CLI currently creates this as a one-way link (`bidirectional: false`). If the user wants reverse inline display inside the Feishu UI, document that UI-side adjustment separately instead of blocking ingestion.

Creator resolution SOP for every video ingestion:

1. Extract the creator identity from the selected note: `user.userid` / `user.id`, `user.nickname`, `user.red_id`, and avatar URL.
2. Search `对标博主` before creating anything.
   - First match exact `小红书用户ID`.
   - If absent or not found, match exact `小红书号`.
   - Only then match exact `博主名称` as a fallback, because creators can rename themselves.
3. If an existing creator row is found, reuse its record id and write the video row's `作者` link to that record.
4. Build `主页链接` as `https://www.xiaohongshu.com/user/profile/<user_id>` when `user_id` is available. If only `red_id` is available, leave the field blank rather than guessing an unsupported profile URL.
5. If the creator is new, call TikHub `get_user_info` with `user_id`, save the raw response under `小红书笔记采集/benchmark_creators/<creator_slug>/`, download avatar/background assets, create the `对标博主` row including `小红书用户ID`, `小红书号`, `主页链接`, and `最近更新时间`, upload attachments, and then write the video row's `作者` link.
6. If `get_user_info` returns a transient network/SSL/EOF error or a non-profile response, retry once before creating the creator row. Save both the failed response and the retry response locally.
7. Only create a minimal creator row from the video detail data (`博主名称`, `主页链接`, avatar when available) after retry also fails. Link the video to it, and note that the creator profile needs enrichment later.
8. Never write the creator into a separate plain-text author field. The `作者` column in `视频笔记` must be the linked creator record.

Create the benchmark creator table when missing:

```bash
lark-cli base +table-create --as user \
  --base-token <base_token> \
  --name "对标博主" \
  --fields '[{"name":"博主名称","type":"text"},{"name":"小红书用户ID","type":"text"},{"name":"小红书号","type":"text"},{"name":"主页链接","type":"text"},{"name":"头像","type":"attachment"},{"name":"简介","type":"text"},{"name":"主页背景图","type":"attachment"},{"name":"粉丝量","type":"number","style":{"type":"plain","precision":0,"thousands_separator":false,"percentage":false}},{"name":"获赞和收藏量","type":"number","style":{"type":"plain","precision":0,"thousands_separator":false,"percentage":false}},{"name":"最近更新时间","type":"datetime","style":{"format":"yyyy/MM/dd HH:mm"}}]'
```

Benchmark creator views:

- Rename the default grid view to `表格视图`.
- Create a gallery view named `卡片视图`.
- Set `卡片视图` cover field to `主页背景图`, not `头像`; the background image gives each creator card a stronger profile-page feel.
- In `卡片视图`, show fields in this order: `博主名称`, `主页链接`, `头像`, `简介`, `粉丝量`, `获赞和收藏量`, `最近更新时间`.
- In `表格视图`, show fields in this order: `博主名称`, `小红书用户ID`, `小红书号`, `主页链接`, `头像`, `简介`, `主页背景图`, `粉丝量`, `获赞和收藏量`, `最近更新时间`.
- Keep creator metric fields as integers with no decimals.

## Interaction Number Fields

Display interaction metrics as whole numbers.

- Configure `点赞量`, `评论量`, and `收藏量` as number fields with `precision: 0`.
- Do not show `.00` or `.0` in grid/card/detail views.
- When creating or repairing a Base, use number style `{"type":"plain","precision":0,"thousands_separator":false,"percentage":false}` for all three fields.
- Write integer values from TikHub counts; if TikHub returns strings, parse them to integers before creating the Feishu row.
- In `表格视图`, visually center-align short numeric/metric columns: `点赞量`, `评论量`, `收藏量`, and `视频时长`.
- If `lark-cli` cannot set cell alignment for a Base view, keep this as a required Feishu UI cleanup step and mention it instead of pretending the API handled it.

## Candidate Selection

TikHub can return a list of related notes instead of only the target note.

- Treat the first usable item as a candidate, not proof. Confirm it has the expected note id, title, author, or canonical `share_info.link` for the submitted xhslink.
- If there are several candidates, choose the one whose `share_info.link` or `note_id` corresponds to the share link. If the share link resolution is ambiguous, prefer the item whose title/author matches the opened target context.
- Save the full raw response before filtering so selection can be audited later.
- Put the chosen `note_id`, title, author, original short link, canonical link, and interaction counts into `note_metadata.json`.

## Duration

Capture each video's duration and write it to Feishu.

- Prefer `video_info_v2.media.video.duration` when present; it is usually seconds.
- If that is missing, use `widgets_context.video_duration` after parsing the JSON string.
- If only stream metadata is available, use `video_info_v2.media.stream.h264[0].duration` or another stream `duration`; treat values over 1000 as milliseconds and round to seconds.
- Store both `duration_seconds` and `duration_display` in `note_metadata.json`.
- Write `duration_display` to the Feishu `视频时长` field. Format under one hour as `M:SS`; format one hour or longer as `H:MM:SS`.

## Publish Date

Capture each video's publish date and write it to Feishu.

- Field name: `发布时间`.
- Feishu field type should be date/datetime with display format `yyyy/MM/dd`.
- Prefer the selected note's top-level TikHub `time` field. It is a Unix seconds timestamp.
- Convert the timestamp to Asia/Shanghai date. Store in local metadata:
  - `publish_time_raw`: original integer timestamp.
  - `publish_time_cst`: ISO-like timestamp with `+08:00`, for example `2026-07-04T18:01:47+08:00`.
  - `publish_date`: date-only string, for example `2026-07-04`.
- Write `发布时间` to Feishu as `YYYY-MM-DD 00:00:00` so it behaves as a sortable/filterable date field while visually showing only the年月日.
- Do not use `last_update_time` as publish date unless `time` is missing. If falling back, record `publish_date_source` in metadata.

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

- Use a contextual Xiaohongshu share URL as the default watch link in Feishu `视频链接`; it needs to open the right video in a desktop browser when clicked.
- Keep the original user input, short link, and TikHub canonical link in local metadata for auditing and candidate verification.
- Do not download `video.mp4` or upload video attachments unless the user explicitly asks for local/video-file archival.
- If the user explicitly asks for the video file, prefer `video_info_v2.media.stream.h264[0].master_url` for `video.mp4`; use backup URLs on failure. Use H.264 over H.265 for compatibility with Feishu previews.
- Save subtitles from `video_info_v2.media.video.subtitles`.
- TikHub subtitle data may be a list or a language-grouped object such as `{"zh-CN":[...],"source":[...],"en-US":[...]}`. Support both shapes and prefer `zh-CN`, then `source`, then any available subtitle.
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
- Make it scannable enough that the user can quickly understand what the video says and how it unfolds.
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
  --base-token <base_token> \
  --table-id <video_table_id> \
  --json '{"fields":["视频标题","作者","视频链接","视频时长","发布时间","简介","核心总结","文字内容","点赞量","评论量","收藏量"],"rows":[[...]]}'
```

Save this payload locally as `feishu_record_payload.json`, and save the creation response as `feishu_record_create.json`.

Upload attachments from the asset directory with relative paths:

```bash
lark-cli base +record-upload-attachment --as user \
  --base-token <base_token> \
  --table-id <video_table_id> \
  --record-id <record_id> \
  --field-id "视频封面" \
  --file ./cover_original.webp
```

The attachment command rejects absolute file paths; `cd` into the asset folder first.

To fix a wrong attachment:

```bash
lark-cli base +record-remove-attachment --as user \
  --base-token <base_token> \
  --table-id <video_table_id> \
  --record-id <record_id> \
  --field-id "视频封面" \
  --file-token <token> \
  --yes
```

Then upload the corrected file.

Read back the row once after all writes:

```bash
lark-cli base +record-get --as user \
  --base-token <base_token> \
  --table-id <video_table_id> \
  --record-id <record_id> \
  --format json
```

Save the readback as `feishu_record_get.json`. The response shape is array-based: `data.fields` contains field names, `data.data[0]` contains values in the same order, and `data.record_id_list[0]` contains the record id. Build a name-to-value map from those arrays. Do not assume a `.data.record.fields` object exists.

## Verification Checklist

Before final response, verify and report:

- Record ID
- Title and linked author
- Like/comment/favorite counts
- Video duration
- Publish date
- `核心总结` exists and is no more than 300 Chinese characters
- Full `简介` length or trailing content if completeness was questioned
- Subtitle text exists when available
- `视频封面` has a single correct cover attachment
- `视频链接` exists and uses a contextual Xiaohongshu share URL. Avoid bare no-query `explore/<note_id>` links unless no contextual link exists.
- `视频文件本身` is empty for normal runs unless the user explicitly requested video file archival
- Local folder path
- Feishu Base link from the configured `feishu.base_url`

## Final Response

After every successful ingestion, include both places the user needs next:

- Local folder path for the saved artifacts.
- Feishu Base link for opening the table.

Keep the final response concise. Mention the record id, title, author, interaction counts, video duration, the local folder path, and the Feishu Base link.

## Long Text Readability

Grid view is for scanning and will truncate long text cells. Do not treat this as missing data if record readback shows the full text.

- Name the main grid view `表格视图`.
- Name the gallery/card reading view `卡片视图`.
- Keep `表格视图` compact for scanning.
- For reading long `简介` or `文字内容` fields, create or maintain a gallery/card view named `卡片视图`.
- Set `视频封面` as the gallery cover field.
- Recommended visible field order: `视频标题`, `作者`, `视频封面`, `视频链接`, `视频时长`, `发布时间`, `点赞量`, `评论量`, `收藏量`, `核心总结`, `简介`, `文字内容`, `视频文件本身`.
- In `表格视图`, keep the metric/date columns visually consistent: `视频时长`, `发布时间`, `点赞量`, `评论量`, and `收藏量` should be centered in their cells, with compact column widths.
- If view configuration by field name fails, list fields and retry with field IDs.

## Record Detail Layout

When creating a new Feishu Base or rebuilding a table for this workflow, configure the record detail page with the recommended layout. Preserve an existing layout once the user has manually tuned it.

Use this structure:

1. Large title header
   - Use `视频标题` as the record title.
   - Keep it visually prominent at the top, using the detail page's large title style.
2. Section: `视频基础信息`
   - Layout: four columns across the row.
   - Fields, left to right: `视频标题`, `作者`, `视频封面`, `视频链接`.
   - Use a readable medium-large value size for title/author.
   - Show the cover as a visual preview card.
   - Show `视频链接` as a clickable URL so the user can jump to Xiaohongshu to watch.
3. Section: `视频数据`
   - Layout: four columns.
   - Fields, left to right: `发布时间`, `视频时长`, `评论量`, `收藏量`, `点赞量`.
   - Use date/number fields with clear labels and enough spacing. `发布时间` must show 年月日 only; `评论量`, `收藏量`, and `点赞量` must display as integers without decimal places.
   - Center-align `发布时间`, `视频时长`, `评论量`, `收藏量`, and `点赞量` so the metric block reads as a unified group.
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

Companion integrations:

- Treat this Skill and its CLI as the source of truth for ingestion behavior.
- Point companion browser extensions or services to the same configuration and command entry point instead of duplicating field mappings.
- Verify each companion integration after behavior changes before reporting that it matches the Skill.
