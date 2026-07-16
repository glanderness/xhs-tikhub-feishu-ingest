#!/usr/bin/env python3
"""Collect one Xiaohongshu note through TikHub and append/update Lucas's Feishu Base."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any


BASE_TOKEN = "OHDKbmvo7aaqUlssdXncKTHCnDc"
VIDEO_TABLE_ID = "tbl1gfUEArDaQQun"
CREATOR_TABLE_ID = "tblwou5tJyHf4tMg"
BASE_URL = "https://scnitw8fqog4.feishu.cn/base/OHDKbmvo7aaqUlssdXncKTHCnDc"
DEFAULT_OUTPUT_ROOT = pathlib.Path("/Users/lucas/Documents/国内自媒体运营/小红书笔记采集")
TIKHUB_ENV = pathlib.Path.home() / ".codex/mcp/tikhub/tikhub.env"


VIDEO_FIELDS = [
    "视频标题",
    "作者",
    "视频链接",
    "视频时长",
    "发布时间",
    "简介",
    "核心总结",
    "文字内容",
    "点赞量",
    "评论量",
    "收藏量",
]

CREATOR_FIELDS = [
    "博主名称",
    "小红书用户ID",
    "小红书号",
    "主页链接",
    "简介",
    "粉丝量",
    "获赞和收藏量",
    "最近更新时间",
]


def eprint(*parts: Any) -> None:
    print(*parts, file=sys.stderr)


def load_env(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def http_json(url: str, headers: dict[str, str], timeout: int = 60) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def download(url: str, dest: pathlib.Path, timeout: int = 60) -> bool:
    if not url:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.xiaohongshu.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        dest.write_bytes(response.read())
    return True


def slugify(value: str, fallback: str = "creator") -> str:
    value = re.sub(r"[\\/:*?\"<>|\n\r\t]+", "_", value).strip(" ._")
    return value or fallback


def extract_first_url(text: str) -> str:
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0).strip("，。)）]】>") if match else text.strip()


def extract_note_id(text: str) -> str:
    patterns = [
        r"/(?:discovery/item|explore)/([0-9a-fA-F]{24})",
        r"item/([0-9a-fA-F]{24})",
        r"note_id=([0-9a-fA-F]{24})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def extract_xhslink_code(text: str) -> str:
    match = re.search(r"xhslink\.com/o/([A-Za-z0-9_-]+)", text)
    return match.group(1) if match else ""


def watch_video_link(original_text: str, note_id: str, canonical_link: str = "") -> str:
    first_url = extract_first_url(original_text)
    short_code = extract_xhslink_code(first_url)
    if short_code:
        return canonical_link or first_url
    if first_url and "xiaohongshu.com" in first_url and "?" in first_url:
        return first_url
    if canonical_link:
        return canonical_link
    if note_id:
        return f"https://www.xiaohongshu.com/explore/{note_id}"
    parsed = urllib.parse.urlsplit(first_url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def parse_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    multipliers = {"万": 10000, "w": 10000, "W": 10000, "k": 1000, "K": 1000}
    for suffix, multiplier in multipliers.items():
        if text.endswith(suffix):
            return int(float(text[:-1]) * multiplier)
    match = re.search(r"\d+(?:\.\d+)?", text)
    return int(float(match.group(0))) if match else 0


def nested(obj: Any, path: list[Any], default: Any = None) -> Any:
    cur = obj
    for part in path:
        if isinstance(cur, dict):
            cur = cur.get(part, default)
        elif isinstance(cur, list) and isinstance(part, int) and len(cur) > part:
            cur = cur[part]
        else:
            return default
    return cur


def duration_seconds(note: dict[str, Any]) -> int:
    candidates = [
        nested(note, ["video_info_v2", "media", "video", "duration"]),
        nested(note, ["video_info_v2", "capa", "duration"]),
        nested(note, ["video_info_v2", "media", "stream", "h264", 0, "duration"]),
        nested(note, ["video_info_v2", "media", "stream", "h265", 0, "duration"]),
    ]
    widgets_context = note.get("widgets_context")
    if isinstance(widgets_context, str):
        try:
            candidates.append(json.loads(widgets_context).get("video_duration"))
        except json.JSONDecodeError:
            pass
    for value in candidates:
        if value is None:
            continue
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if seconds > 1000:
            seconds /= 1000
        if seconds > 0:
            return int(round(seconds))
    return 0


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def publish_time(note: dict[str, Any]) -> dict[str, Any]:
    source = "time"
    raw = note.get("time")
    if raw is None:
        raw = note.get("last_update_time")
        source = "last_update_time"
    try:
        timestamp = int(float(raw))
    except (TypeError, ValueError):
        return {
            "publish_time_raw": "",
            "publish_time_cst": "",
            "publish_date": "",
            "publish_date_source": "",
            "feishu_publish_time": "",
        }
    if timestamp > 10_000_000_000:
        timestamp = round(timestamp / 1000)
    cst = timezone(timedelta(hours=8))
    published = datetime.fromtimestamp(timestamp, tz=cst)
    return {
        "publish_time_raw": timestamp,
        "publish_time_cst": published.isoformat(timespec="seconds"),
        "publish_date": published.strftime("%Y-%m-%d"),
        "publish_date_source": source,
        "feishu_publish_time": published.strftime("%Y-%m-%d 00:00:00"),
    }


def response_candidates(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return [item for item in data["data"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def fetch_detail(share_text: str, env: dict[str, str]) -> tuple[dict[str, Any], str]:
    base = env.get("TIKHUB_BASE_URL", "https://api.tikhub.io").rstrip("/")
    key = env.get("TIKHUB_API_KEY")
    if not key:
        raise RuntimeError("TIKHUB_API_KEY is missing")
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "Codex xhs-tikhub-feishu-ingest",
    }
    endpoints = [
        "/api/v1/xiaohongshu/app_v2/get_video_note_detail",
        "/api/v1/xiaohongshu/app_v2/get_mixed_note_detail",
        "/api/v1/xiaohongshu/app_v2/get_image_note_detail",
    ]
    last_response: dict[str, Any] = {}
    last_endpoint = endpoints[0]
    for endpoint in endpoints:
        url = base + endpoint + "?" + urllib.parse.urlencode({"share_text": share_text})
        t0 = time.time()
        response = http_json(url, headers=headers)
        eprint(f"TikHub {endpoint} returned {len(response_candidates(response))} candidate(s) in {time.time() - t0:.2f}s")
        last_response = response
        last_endpoint = endpoint
        if response_candidates(response):
            return response, endpoint
    return last_response, last_endpoint


def select_note(
    candidates: list[dict[str, Any]],
    note_id_hint: str = "",
    expected_title: str = "",
    expected_author: str = "",
) -> dict[str, Any]:
    for item in candidates:
        if note_id_hint and (item.get("id") or item.get("note_id")) == note_id_hint:
            return item
    for item in candidates:
        title = item.get("title") or ""
        user = item.get("user") or {}
        author = user.get("nickname") or user.get("name") or ""
        if expected_title and expected_title in title:
            if not expected_author or expected_author == author:
                return item
    if candidates:
        return candidates[0]
    raise RuntimeError("No usable note candidate returned")


def cover_url(note: dict[str, Any]) -> str:
    images = note.get("images_list") or []
    if images and isinstance(images[0], dict):
        first = images[0]
        url = first.get("original") or first.get("url") or ""
        if url:
            return url
    share_image = nested(note, ["share_info", "image"], "")
    if share_image:
        parsed = urllib.parse.urlsplit(share_image)
        bare = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        return bare + "?imageView2/2/w/5000/h/5000/format/webp/q/90"
    return nested(note, ["video_info_v2", "image", "first_frame"], "") or nested(
        note, ["video_info_v2", "image", "thumbnail"], ""
    )


def subtitle_items(note: dict[str, Any]) -> list[dict[str, str]]:
    subtitles = nested(note, ["video_info_v2", "media", "video", "subtitles"], {})
    items: list[dict[str, str]] = []
    if isinstance(subtitles, dict):
        for group, values in subtitles.items():
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, dict) and item.get("url"):
                        items.append(
                            {
                                "group": str(group),
                                "language": str(item.get("language") or group),
                                "url": str(item["url"]),
                            }
                        )
    elif isinstance(subtitles, list):
        for item in subtitles:
            if isinstance(item, dict) and item.get("url"):
                language = str(item.get("language") or item.get("lang") or "source")
                items.append({"group": language, "language": language, "url": str(item["url"])})
    return items


def srt_to_text(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.isdigit() or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = unescape(line).strip()
        if line:
            lines.append(line)
    cleaned: list[str] = []
    for line in lines:
        if not cleaned or cleaned[-1] != line:
            cleaned.append(line)
    return "\n".join(cleaned)


def download_subtitles(note: dict[str, Any], assets_dir: pathlib.Path) -> tuple[list[dict[str, str]], str]:
    records: list[dict[str, str]] = []
    for item in subtitle_items(note):
        safe = slugify(item.get("group") or item.get("language") or "source", "source")
        path = assets_dir / f"subtitle_{safe}.srt"
        record = dict(item)
        try:
            download(item["url"], path)
            record["file"] = str(path)
        except Exception as exc:  # noqa: BLE001
            record["error"] = f"{type(exc).__name__}: {exc}"
        records.append(record)

    chosen: dict[str, str] | None = None
    for preferred in ("zh-CN", "source", "zh", "en-US"):
        for record in records:
            if not record.get("file"):
                continue
            if record.get("group") == preferred or record.get("language") == preferred:
                chosen = record
                break
        if chosen:
            break
    if not chosen:
        chosen = next((record for record in records if record.get("file")), None)
    if not chosen:
        return records, ""
    return records, srt_to_text(pathlib.Path(chosen["file"]).read_text(errors="ignore"))


def auto_summary(note: dict[str, Any], transcript: str) -> str:
    chapters = nested(note, ["video_info_v2", "consumer", "chapters"], [])
    chapter_titles = [str(item.get("text", "")).strip() for item in chapters if isinstance(item, dict)]
    chapter_titles = [title for title in chapter_titles if title]
    title = note.get("title") or "视频"
    if len(chapter_titles) >= 3:
        first = chapter_titles[0]
        second = chapter_titles[1]
        third = "、".join(chapter_titles[2:4])
        summary = (
            f"1、先交代主题\n作者围绕「{title}」说明这条视频要解决的具体使用场景。\n\n"
            f"2、展开关键步骤\n视频依次讲到{first}、{second}等内容，把工具和操作路径展示出来。\n\n"
            f"3、补充实际用法\n后半段重点落在{third}，说明怎么把想法变成可执行的工作流。\n\n"
            f"4、结论\n核心价值是按自己的需求定制流程，让 AI 帮忙把复杂任务整理清楚。"
        )
    elif transcript:
        first_line = transcript.splitlines()[0][:28]
        summary = (
            "1、说明背景\n"
            f"视频从「{first_line}」切入，交代作者要解决的真实问题。\n\n"
            "2、展示过程\n作者围绕工具选择、操作步骤和实际效果，说明如何把想法落到具体流程里。\n\n"
            "3、结论\n这类内容的重点是把零散任务变成更清楚、可持续推进的工作方式。"
        )
    else:
        summary = (
            "1、内容概览\n当前视频没有可用字幕，先保留标题和简介作为基础信息。\n\n"
            "2、结论\n后续如果补到字幕，应基于完整文字内容重写核心总结。"
        )
    return summary[:300]


def run_cli(args: list[str], cwd: pathlib.Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stdout}")
    return result.stdout


def parse_cli_json(output: str) -> dict[str, Any]:
    start = output.find("{")
    end = output.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError(f"CLI output did not contain JSON:\n{output}")
    return json.loads(output[start : end + 1])


def lark_list_records(base_token: str, table_id: str, fields: list[str], limit: int = 200) -> dict[str, Any]:
    args = [
        "lark-cli",
        "base",
        "+record-list",
        "--as",
        "user",
        "--base-token",
        base_token,
        "--table-id",
        table_id,
        "--limit",
        str(limit),
        "--format",
        "json",
    ]
    for field in fields:
        args.extend(["--field-id", field])
    return parse_cli_json(run_cli(args))


def rows_as_maps(response: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    data = response.get("data") or {}
    fields = data.get("fields") or []
    rows = data.get("data") or []
    record_ids = data.get("record_id_list") or []
    return [(record_id, dict(zip(fields, row))) for record_id, row in zip(record_ids, rows)]


def find_creator(base_token: str, creator_table_id: str, name: str, user_id: str = "", red_id: str = "") -> str:
    response = lark_list_records(
        base_token,
        creator_table_id,
        ["博主名称", "主页链接", "小红书用户ID", "小红书号"],
    )
    if user_id:
        for record_id, row in rows_as_maps(response):
            if str(row.get("小红书用户ID") or "") == user_id:
                return record_id
    if red_id:
        for record_id, row in rows_as_maps(response):
            if str(row.get("小红书号") or "") == red_id:
                return record_id
    for record_id, row in rows_as_maps(response):
        if str(row.get("博主名称") or "") == name:
            return record_id
    return ""


def get_user_info(user_id: str, env: dict[str, str], creator_dir: pathlib.Path) -> dict[str, Any]:
    base = env.get("TIKHUB_BASE_URL", "https://api.tikhub.io").rstrip("/")
    key = env.get("TIKHUB_API_KEY")
    if not key:
        return {}
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "Codex xhs-tikhub-feishu-ingest",
    }
    endpoint = "/api/v1/xiaohongshu/app_v2/get_user_info"
    url = base + endpoint + "?" + urllib.parse.urlencode({"user_id": user_id})
    last_response: dict[str, Any] = {}
    for attempt in range(2):
        try:
            response = http_json(url, headers=headers)
            suffix = "" if attempt == 0 else "_retry"
            (creator_dir / f"raw_get_user_info_user_id{suffix}.json").write_text(
                json.dumps(response, ensure_ascii=False, indent=2)
            )
            last_response = response
            profile = nested(response, ["data", "data"], {})
            if isinstance(profile, dict) and (profile.get("userid") or profile.get("nickname")):
                return profile
        except Exception as exc:  # noqa: BLE001
            (creator_dir / f"raw_get_user_info_user_id_error_{attempt + 1}.txt").write_text(
                f"{type(exc).__name__}: {exc}"
            )
    profile = nested(last_response, ["data", "data"], {})
    return profile if isinstance(profile, dict) else {}


def create_creator(
    base_token: str,
    creator_table_id: str,
    env: dict[str, str],
    note_user: dict[str, Any],
    output_root: pathlib.Path,
) -> str:
    name = note_user.get("nickname") or note_user.get("name") or "unknown"
    user_id = note_user.get("userid") or note_user.get("id") or ""
    creator_dir = output_root / "benchmark_creators" / slugify(name)
    assets_dir = creator_dir / "assets"
    creator_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    profile = get_user_info(user_id, env, creator_dir) if user_id else {}
    user_id = profile.get("userid") or profile.get("user_id") or user_id
    red_id = profile.get("red_id") or note_user.get("red_id") or ""
    desc = profile.get("desc") or ""
    fans = parse_int(profile.get("fans"))
    likes_and_collects = 0
    for item in profile.get("interactions") or []:
        if isinstance(item, dict) and item.get("type") == "interaction":
            likes_and_collects = parse_int(item.get("count"))
    profile_url = profile.get("share_link") or (f"https://www.xiaohongshu.com/user/profile/{user_id}" if user_id else "")
    avatar_url = profile.get("imageb") or profile.get("image") or note_user.get("image_size_large") or note_user.get("image") or ""
    banner_url = nested(profile, ["banner_info", "image"], "")

    avatar_file = assets_dir / "avatar.webp"
    background_file = assets_dir / "homepage_background.jpg"
    try:
        download(avatar_url, avatar_file)
    except Exception as exc:  # noqa: BLE001
        eprint(f"Avatar download skipped: {type(exc).__name__}: {exc}")
    try:
        download(banner_url, background_file)
    except Exception as exc:  # noqa: BLE001
        eprint(f"Background download skipped: {type(exc).__name__}: {exc}")

    metadata = {
        "user_id": user_id,
        "red_id": red_id,
        "name": name,
        "desc": desc,
        "fans": fans,
        "likes_and_collects": likes_and_collects,
        "avatar_url": avatar_url,
        "banner_url": banner_url,
        "profile_url": profile_url,
    }
    (creator_dir / "creator_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))

    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "fields": CREATOR_FIELDS,
        "rows": [[name, user_id, red_id, profile_url, desc, fans, likes_and_collects, updated_at]],
    }
    (creator_dir / "feishu_creator_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    output = run_cli(
        [
            "lark-cli",
            "base",
            "+record-batch-create",
            "--as",
            "user",
            "--base-token",
            base_token,
            "--table-id",
            creator_table_id,
            "--json",
            json.dumps(payload, ensure_ascii=False),
            "--format",
            "json",
        ]
    )
    (creator_dir / "feishu_creator_create.json").write_text(output)
    record_id = parse_cli_json(output)["data"]["record_id_list"][0]

    if avatar_file.exists():
        output = run_cli(
            [
                "lark-cli",
                "base",
                "+record-upload-attachment",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                creator_table_id,
                "--record-id",
                record_id,
                "--field-id",
                "头像",
                "--file",
                "./avatar.webp",
                "--format",
                "json",
            ],
            cwd=assets_dir,
        )
        (creator_dir / "feishu_avatar_attachment.json").write_text(output)
    if background_file.exists():
        output = run_cli(
            [
                "lark-cli",
                "base",
                "+record-upload-attachment",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                creator_table_id,
                "--record-id",
                record_id,
                "--field-id",
                "主页背景图",
                "--file",
                "./homepage_background.jpg",
                "--format",
                "json",
            ],
            cwd=assets_dir,
        )
        (creator_dir / "feishu_background_attachment.json").write_text(output)
    return record_id


def find_video_record(base_token: str, video_table_id: str, note_id: str, title: str, watch_link: str) -> str:
    response = lark_list_records(base_token, video_table_id, ["视频标题", "视频链接"])
    for record_id, row in rows_as_maps(response):
        row_title = str(row.get("视频标题") or "")
        row_link = str(row.get("视频链接") or "")
        if watch_link and row_link == watch_link:
            return record_id
        if note_id and note_id in row_link:
            return record_id
        if title and row_title == title:
            return record_id
    return ""


def get_record(base_token: str, table_id: str, record_id: str) -> dict[str, Any]:
    output = run_cli(
        [
            "lark-cli",
            "base",
            "+record-get",
            "--as",
            "user",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--format",
            "json",
        ]
    )
    return parse_cli_json(output)


def record_map(record_response: dict[str, Any]) -> dict[str, Any]:
    data = record_response.get("data") or {}
    fields = data.get("fields") or []
    rows = data.get("data") or []
    if not rows:
        return {}
    return dict(zip(fields, rows[0]))


def create_or_update_video(
    base_token: str,
    video_table_id: str,
    out_dir: pathlib.Path,
    fields: dict[str, Any],
    note_id: str,
    force_create: bool = False,
) -> tuple[str, str]:
    existing_id = "" if force_create else find_video_record(
        base_token,
        video_table_id,
        note_id,
        str(fields.get("视频标题") or ""),
        str(fields.get("视频链接") or ""),
    )
    if existing_id:
        output = run_cli(
            [
                "lark-cli",
                "base",
                "+record-upsert",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                video_table_id,
                "--record-id",
                existing_id,
                "--json",
                json.dumps(fields, ensure_ascii=False),
                "--format",
                "json",
            ]
        )
        (out_dir / "feishu_record_update.json").write_text(output)
        return existing_id, "updated"

    payload = {"fields": VIDEO_FIELDS, "rows": [[fields.get(field) for field in VIDEO_FIELDS]]}
    (out_dir / "feishu_record_payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    output = run_cli(
        [
            "lark-cli",
            "base",
            "+record-batch-create",
            "--as",
            "user",
            "--base-token",
            base_token,
            "--table-id",
            video_table_id,
            "--json",
            json.dumps(payload, ensure_ascii=False),
            "--format",
            "json",
        ]
    )
    (out_dir / "feishu_record_create.json").write_text(output)
    record_id = parse_cli_json(output)["data"]["record_id_list"][0]
    return record_id, "created"


def upload_cover_if_needed(base_token: str, video_table_id: str, record_id: str, out_dir: pathlib.Path) -> None:
    record = get_record(base_token, video_table_id, record_id)
    existing = record_map(record).get("视频封面") or []
    if any(isinstance(item, dict) and item.get("name") == "cover_original.webp" for item in existing):
        return
    assets_dir = out_dir / "assets"
    output = run_cli(
        [
            "lark-cli",
            "base",
            "+record-upload-attachment",
            "--as",
            "user",
            "--base-token",
            base_token,
            "--table-id",
            video_table_id,
            "--record-id",
            record_id,
            "--field-id",
            "视频封面",
            "--file",
            "./cover_original.webp",
            "--format",
            "json",
        ],
        cwd=assets_dir,
    )
    (out_dir / "feishu_cover_attachment.json").write_text(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a Xiaohongshu note and write it to Lucas's Feishu Base.")
    parser.add_argument("share_text", help="Xiaohongshu share URL, xhslink URL, or full share text")
    parser.add_argument("--expected-title", default="", help="Optional title hint for candidate selection")
    parser.add_argument("--expected-author", default="", help="Optional author hint for candidate selection")
    parser.add_argument("--summary-file", type=pathlib.Path, help="Use this file as 核心总结")
    parser.add_argument("--summary-text", default="", help="Use this text as 核心总结")
    parser.add_argument("--output-root", type=pathlib.Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--base-token", default=BASE_TOKEN)
    parser.add_argument("--video-table-id", default=VIDEO_TABLE_ID)
    parser.add_argument("--creator-table-id", default=CREATOR_TABLE_ID)
    parser.add_argument("--skip-feishu", action="store_true", help="Only create local artifacts")
    parser.add_argument("--force-create", action="store_true", help="Create a new Feishu row even if a matching row exists")
    args = parser.parse_args()

    env = load_env(TIKHUB_ENV)
    note_id_hint = extract_note_id(args.share_text)
    xhslink_code = extract_xhslink_code(args.share_text)

    t0 = time.time()
    detail, endpoint = fetch_detail(args.share_text, env)
    candidates = response_candidates(detail)
    note = select_note(candidates, note_id_hint, args.expected_title, args.expected_author)
    note_id = str(note.get("id") or note.get("note_id") or note_id_hint)
    user = note.get("user") or {}
    author_name = str(user.get("nickname") or user.get("name") or "")
    title = str(note.get("title") or "")
    canonical = nested(note, ["share_info", "link"], "")
    watch_link = watch_video_link(args.share_text, note_id, canonical)

    folder_name = f"xhslink_{xhslink_code}" if xhslink_code else f"xhs_{note_id}"
    out_dir = args.output_root / folder_name
    assets_dir = out_dir / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw_video.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2))

    cover = cover_url(note)
    cover_file = assets_dir / "cover_original.webp"
    if cover:
        download(cover, cover_file)
    subtitle_records, transcript = download_subtitles(note, assets_dir)
    (out_dir / "transcript_zh-CN.txt").write_text(transcript)

    if args.summary_file:
        summary = args.summary_file.read_text().strip()
    elif args.summary_text:
        summary = args.summary_text.strip()
    else:
        summary = auto_summary(note, transcript)
    if len(summary) > 300:
        raise RuntimeError("核心总结 is longer than 300 characters")
    (out_dir / "core_summary.txt").write_text(summary)

    seconds = duration_seconds(note)
    published = publish_time(note)
    liked = parse_int(note.get("liked_count"))
    comments = parse_int(note.get("comments_count"))
    collected = parse_int(note.get("collected_count"))
    desc = str(note.get("desc") or "")
    metadata = {
        "source_share_text": args.share_text,
        "original_share_link": extract_first_url(args.share_text),
        "video_link": watch_link,
        "watch_video_link": watch_link,
        "note_id": note_id,
        "title": title,
        "author": user,
        "author_name": author_name,
        "desc": desc,
        "canonical_link": canonical,
        "liked_count": liked,
        "comments_count": comments,
        "collected_count": collected,
        "duration_seconds": seconds,
        "duration_display": format_duration(seconds),
        **published,
        "cover_url": cover,
        "cover_file": str(cover_file) if cover_file.exists() else "",
        "cover_size": cover_file.stat().st_size if cover_file.exists() else 0,
        "subtitles": subtitle_records,
        "transcript_chars": len(transcript),
        "summary_chars": len(summary),
        "tikhub": {"router": detail.get("router") or endpoint, "cache_url": detail.get("cache_url")},
    }
    (out_dir / "note_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    (out_dir / "note.md").write_text(
        f"# {title}\n\n"
        f"作者：{author_name}\n\n"
        f"链接：{watch_link}\n\n"
        f"时长：{format_duration(seconds)}\n\n"
        f"发布时间：{published.get('publish_date')}\n\n"
        f"点赞：{liked}\n评论：{comments}\n收藏：{collected}\n\n"
        f"## 简介\n\n{desc}\n\n"
        f"## 核心总结\n\n{summary}\n\n"
        f"## 文字内容\n\n{transcript}\n"
    )

    report: dict[str, Any] = {
        "ok": True,
        "local_folder": str(out_dir),
        "base_url": BASE_URL,
        "note_id": note_id,
        "title": title,
        "author": author_name,
        "duration": format_duration(seconds),
        "publish_date": published.get("publish_date"),
        "liked_count": liked,
        "comments_count": comments,
        "collected_count": collected,
        "transcript_chars": len(transcript),
        "summary_chars": len(summary),
        "video_link": watch_link,
        "elapsed_seconds": None,
    }

    if not args.skip_feishu:
        creator_user_id = str(user.get("userid") or user.get("id") or "")
        creator_red_id = str(user.get("red_id") or "")
        creator_record_id = find_creator(
            args.base_token,
            args.creator_table_id,
            author_name,
            creator_user_id,
            creator_red_id,
        )
        if not creator_record_id:
            creator_record_id = create_creator(args.base_token, args.creator_table_id, env, user, args.output_root)
        fields = {
            "视频标题": title,
            "作者": [{"id": creator_record_id}],
            "视频链接": watch_link,
            "视频时长": format_duration(seconds),
            "发布时间": published.get("feishu_publish_time"),
            "简介": desc,
            "核心总结": summary,
            "文字内容": transcript,
            "点赞量": liked,
            "评论量": comments,
            "收藏量": collected,
        }
        video_record_id, action = create_or_update_video(
            args.base_token,
            args.video_table_id,
            out_dir,
            fields,
            note_id,
            force_create=args.force_create,
        )
        if cover_file.exists():
            upload_cover_if_needed(args.base_token, args.video_table_id, video_record_id, out_dir)
        final_record = get_record(args.base_token, args.video_table_id, video_record_id)
        (out_dir / "feishu_record_get.json").write_text(json.dumps(final_record, ensure_ascii=False, indent=2))
        final = record_map(final_record)
        report.update(
            {
                "creator_record_id": creator_record_id,
                "video_record_id": video_record_id,
                "feishu_action": action,
                "cover_attachments": final.get("视频封面"),
                "video_file_field_present": "视频文件本身" in final,
            }
        )

    report["elapsed_seconds"] = round(time.time() - t0, 2)
    (out_dir / "ingest_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
