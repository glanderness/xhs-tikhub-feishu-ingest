#!/usr/bin/env python3
"""Unified command entry point for the XHS ingestion project."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any, Sequence
from urllib.parse import urlsplit

import ingest_xhs_note
from xhs_config import DEFAULT_CONFIG_PATH, resolve_settings, update_toml_section


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_EXAMPLE = PROJECT_ROOT / "config.example.toml"

NUMBER_STYLE = {"type": "plain", "precision": 0, "thousands_separator": False, "percentage": False}
CREATOR_SCHEMA = [
    {"name": "博主名称", "type": "text"},
    {"name": "小红书用户ID", "type": "text"},
    {"name": "小红书号", "type": "text"},
    {"name": "主页链接", "type": "text"},
    {"name": "头像", "type": "attachment"},
    {"name": "简介", "type": "text"},
    {"name": "主页背景图", "type": "attachment"},
    {"name": "粉丝量", "type": "number", "style": NUMBER_STYLE},
    {"name": "获赞和收藏量", "type": "number", "style": NUMBER_STYLE},
    {"name": "最近更新时间", "type": "datetime", "style": {"format": "yyyy/MM/dd HH:mm"}},
]


def video_schema(creator_table_id: str) -> list[dict[str, Any]]:
    return [
        {"name": "视频标题", "type": "text"},
        {"name": "作者", "type": "link", "link_table": creator_table_id},
        {"name": "视频封面", "type": "attachment"},
        {"name": "视频链接", "type": "text"},
        {"name": "视频时长", "type": "text"},
        {"name": "发布时间", "type": "datetime", "style": {"format": "yyyy/MM/dd"}},
        {"name": "简介", "type": "text"},
        {"name": "核心总结", "type": "text"},
        {"name": "文字内容", "type": "text"},
        {"name": "点赞量", "type": "number", "style": NUMBER_STYLE},
        {"name": "评论量", "type": "number", "style": NUMBER_STYLE},
        {"name": "收藏量", "type": "number", "style": NUMBER_STYLE},
    ]


VIDEO_VISIBLE_FIELDS = [
    "视频标题",
    "作者",
    "视频封面",
    "视频链接",
    "视频时长",
    "发布时间",
    "点赞量",
    "评论量",
    "收藏量",
    "核心总结",
    "简介",
    "文字内容",
]
CREATOR_VISIBLE_FIELDS = [
    "博主名称",
    "小红书用户ID",
    "小红书号",
    "主页链接",
    "头像",
    "简介",
    "主页背景图",
    "粉丝量",
    "获赞和收藏量",
    "最近更新时间",
]


def write_initial_config(
    config_path: pathlib.Path,
    output_root: pathlib.Path | None = None,
    tikhub_env_file: pathlib.Path | None = None,
    force: bool = False,
) -> bool:
    if config_path.exists() and not force:
        return False
    template = CONFIG_EXAMPLE.read_text(encoding="utf-8")
    if output_root:
        template = template.replace('root = "~/xhs-ingest-output"', f'root = "{output_root.expanduser()}"')
    if tikhub_env_file:
        template = template.replace(
            'env_file = "~/.config/xhs-tikhub-feishu-ingest/tikhub.env"',
            f'env_file = "{tikhub_env_file.expanduser()}"',
        )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(template, encoding="utf-8")
    settings = resolve_settings(config_path=config_path, environ={})
    settings.output_root.mkdir(parents=True, exist_ok=True)
    return True


def _check(name: str, ok: bool, detail: str, required: bool = True) -> dict[str, Any]:
    return {"name": name, "ok": ok, "required": required, "detail": detail}


def build_doctor_report(config_path: pathlib.Path | None = None, skip_feishu: bool = False) -> dict[str, Any]:
    settings = resolve_settings(config_path=config_path)
    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "python",
            sys.version_info >= (3, 9),
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    checks.append(
        _check(
            "config",
            settings.config_path.exists(),
            str(settings.config_path),
        )
    )
    try:
        settings.output_root.mkdir(parents=True, exist_ok=True)
        output_ok = os.access(settings.output_root, os.W_OK)
    except OSError:
        output_ok = False
    checks.append(_check("output", output_ok, str(settings.output_root)))
    checks.append(
        _check(
            "tikhub_key",
            bool(settings.tikhub_api_key),
            "configured" if settings.tikhub_api_key else "set TIKHUB_API_KEY or tikhub.api_key",
        )
    )
    parsed_tikhub = urlsplit(settings.tikhub_base_url)
    checks.append(
        _check(
            "tikhub_url",
            parsed_tikhub.scheme in {"http", "https"} and bool(parsed_tikhub.netloc),
            settings.tikhub_base_url,
        )
    )

    lark_path = shutil.which("lark-cli")
    checks.append(
        _check(
            "lark_cli",
            bool(lark_path),
            lark_path or "install lark-cli before enabling Feishu",
            required=not skip_feishu,
        )
    )
    lark_auth_ok = False
    lark_auth_detail = "skipped"
    if lark_path and not skip_feishu:
        result = subprocess.run(
            [lark_path, "doctor", "--offline"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        lark_auth_ok = result.returncode == 0
        lark_auth_detail = "ready" if lark_auth_ok else "run lark-cli auth login"
    checks.append(
        _check(
            "lark_auth",
            lark_auth_ok or skip_feishu,
            lark_auth_detail,
            required=not skip_feishu,
        )
    )
    feishu_ready = all(
        [settings.feishu_base_token, settings.feishu_video_table_id, settings.feishu_creator_table_id]
    )
    checks.append(
        _check(
            "feishu_tables",
            feishu_ready or skip_feishu,
            "configured" if feishu_ready else "run setup-feishu or fill the Feishu table values",
            required=not skip_feishu,
        )
    )
    ok = all(item["ok"] for item in checks if item["required"])
    return {
        "ok": ok,
        "config_path": str(settings.config_path),
        "checks": checks,
    }


def print_doctor_report(report: dict[str, Any], json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    for item in report["checks"]:
        label = "OK" if item["ok"] else ("WARN" if not item["required"] else "FAIL")
        print(f"[{label}] {item['name']}: {item['detail']}")
    print("Ready" if report["ok"] else "Action required")


def lark_json(args: list[str]) -> dict[str, Any]:
    output = ingest_xhs_note.run_cli(["lark-cli", *args])
    return ingest_xhs_note.parse_cli_json(output)


def _find_value(value: Any, keys: set[str]) -> str:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str) and item:
                return item
        for item in value.values():
            found = _find_value(item, keys)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_value(item, keys)
            if found:
                return found
    return ""


def _tables(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") or {}
    tables = data.get("tables") or data.get("items") or []
    return [item for item in tables if isinstance(item, dict)]


def _fields(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") or {}
    fields = data.get("fields") or data.get("items") or []
    return [item for item in fields if isinstance(item, dict)]


def _views(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data") or {}
    views = data.get("views") or data.get("items") or []
    return [item for item in views if isinstance(item, dict)]


def _find_table(tables: list[dict[str, Any]], table_id: str, names: list[str]) -> dict[str, Any] | None:
    if table_id:
        matched = next((item for item in tables if item.get("id") == table_id), None)
        if matched:
            return matched
    return next((item for item in tables if item.get("name") in names), None)


def _create_table(
    runner: Any,
    base_token: str,
    name: str,
    schema: list[dict[str, Any]],
) -> str:
    response = runner(
        [
            "base",
            "+table-create",
            "--as",
            "user",
            "--base-token",
            base_token,
            "--name",
            name,
            "--fields",
            json.dumps(schema, ensure_ascii=False),
            "--format",
            "json",
        ]
    )
    table_id = _find_value(response, {"table_id", "id"})
    if not table_id.startswith("tbl"):
        raise RuntimeError(f"Could not read the table id after creating {name}")
    return table_id


def _ensure_fields(
    runner: Any,
    base_token: str,
    table_id: str,
    schema: list[dict[str, Any]],
    check_only: bool,
) -> tuple[list[str], list[str]]:
    existing = _fields(
        runner(
            [
                "base",
                "+field-list",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                table_id,
                "--format",
                "json",
            ]
        )
    )
    by_name = {str(item.get("name")): item for item in existing}
    created: list[str] = []
    issues: list[str] = []
    for field in schema:
        current = by_name.get(field["name"])
        if current:
            if current.get("type") != field["type"]:
                issues.append(
                    f"{field['name']}: expected {field['type']}, found {current.get('type') or 'unknown'}"
                )
            elif field["type"] == "link" and current.get("link_table") != field.get("link_table"):
                issues.append(f"{field['name']}: linked creator table does not match")
            continue
        if check_only:
            issues.append(f"{field['name']}: missing")
            continue
        runner(
            [
                "base",
                "+field-create",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                table_id,
                "--json",
                json.dumps(field, ensure_ascii=False),
                "--format",
                "json",
            ]
        )
        created.append(field["name"])
    return created, issues


def _ensure_views(
    runner: Any,
    base_token: str,
    table_id: str,
    visible_fields: list[str],
    cover_field: str,
    check_only: bool,
) -> tuple[list[str], list[str]]:
    views = _views(
        runner(
            [
                "base",
                "+view-list",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                table_id,
                "--format",
                "json",
            ]
        )
    )
    by_name = {str(item.get("name")): item for item in views}
    created: list[str] = []
    issues: list[str] = []
    grid = by_name.get("表格视图") or next((item for item in views if item.get("type") == "grid"), None)
    if not grid:
        if check_only:
            issues.append("表格视图: missing")
        else:
            response = runner(
                [
                    "base",
                    "+view-create",
                    "--as",
                    "user",
                    "--base-token",
                    base_token,
                    "--table-id",
                    table_id,
                    "--json",
                    json.dumps({"name": "表格视图", "type": "grid"}, ensure_ascii=False),
                    "--format",
                    "json",
                ]
            )
            grid = {"id": _find_value(response, {"view_id", "id"}), "name": "表格视图", "type": "grid"}
            created.append("表格视图")
    elif grid.get("name") != "表格视图" and not check_only:
        runner(
            [
                "base",
                "+view-rename",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                table_id,
                "--view-id",
                str(grid.get("id")),
                "--name",
                "表格视图",
                "--format",
                "json",
            ]
        )

    gallery = by_name.get("卡片视图") or next((item for item in views if item.get("type") == "gallery"), None)
    if not gallery:
        if check_only:
            issues.append("卡片视图: missing")
        else:
            response = runner(
                [
                    "base",
                    "+view-create",
                    "--as",
                    "user",
                    "--base-token",
                    base_token,
                    "--table-id",
                    table_id,
                    "--json",
                    json.dumps({"name": "卡片视图", "type": "gallery"}, ensure_ascii=False),
                    "--format",
                    "json",
                ]
            )
            gallery = {"id": _find_value(response, {"view_id", "id"}), "name": "卡片视图", "type": "gallery"}
            created.append("卡片视图")
    elif gallery.get("name") != "卡片视图" and not check_only:
        runner(
            [
                "base",
                "+view-rename",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                table_id,
                "--view-id",
                str(gallery.get("id")),
                "--name",
                "卡片视图",
                "--format",
                "json",
            ]
        )

    if check_only:
        return created, issues
    for view in (grid, gallery):
        if not view or not view.get("id"):
            continue
        runner(
            [
                "base",
                "+view-set-visible-fields",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                table_id,
                "--view-id",
                str(view["id"]),
                "--json",
                json.dumps({"visible_fields": visible_fields}, ensure_ascii=False),
                "--format",
                "json",
            ]
        )
    if gallery and gallery.get("id"):
        runner(
            [
                "base",
                "+view-set-card",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--table-id",
                table_id,
                "--view-id",
                str(gallery["id"]),
                "--json",
                json.dumps({"cover_field": cover_field}, ensure_ascii=False),
                "--format",
                "json",
            ]
        )
    return created, issues


def setup_feishu(
    config_path: pathlib.Path | None = None,
    base_token_override: str = "",
    base_url_override: str = "",
    base_name: str = "小红书视频素材库",
    video_table_name: str = "视频笔记",
    creator_table_name: str = "对标博主",
    check_only: bool = False,
    runner: Any = lark_json,
) -> dict[str, Any]:
    settings = resolve_settings(config_path=config_path)
    base_token = base_token_override or settings.feishu_base_token
    base_url = base_url_override or settings.feishu_base_url
    created_base = False
    initial_creator_id = ""
    if not base_token:
        if check_only:
            return {"ok": False, "issues": ["Feishu Base is not configured"]}
        response = runner(
            [
                "base",
                "+base-create",
                "--as",
                "user",
                "--name",
                base_name,
                "--table-name",
                creator_table_name,
                "--fields",
                json.dumps(CREATOR_SCHEMA, ensure_ascii=False),
                "--time-zone",
                "Asia/Shanghai",
                "--format",
                "json",
            ]
        )
        base_token = _find_value(response, {"base_token", "app_token"})
        initial_creator_id = _find_value(response, {"table_id"})
        base_url = base_url or _find_value(response, {"url", "base_url"})
        if not base_token:
            raise RuntimeError("Could not read the Base token after creation")
        created_base = True

    tables_response = runner(
        [
            "base",
            "+table-list",
            "--as",
            "user",
            "--base-token",
            base_token,
            "--format",
            "json",
        ]
    )
    tables = _tables(tables_response)
    creator = _find_table(tables, settings.feishu_creator_table_id or initial_creator_id, [creator_table_name])
    created_tables: list[str] = []
    issues: list[str] = []
    if not creator:
        if check_only:
            issues.append(f"{creator_table_name}: table missing")
            creator_id = ""
        else:
            creator_id = _create_table(runner, base_token, creator_table_name, CREATOR_SCHEMA)
            created_tables.append(creator_table_name)
    else:
        creator_id = str(creator.get("id") or "")

    creator_fields_created: list[str] = []
    creator_views_created: list[str] = []
    if creator_id:
        creator_fields_created, creator_field_issues = _ensure_fields(
            runner, base_token, creator_id, CREATOR_SCHEMA, check_only
        )
        issues.extend(f"{creator_table_name}.{item}" for item in creator_field_issues)
        creator_views_created, creator_view_issues = _ensure_views(
            runner,
            base_token,
            creator_id,
            CREATOR_VISIBLE_FIELDS,
            "主页背景图",
            check_only,
        )
        issues.extend(f"{creator_table_name}.{item}" for item in creator_view_issues)

    tables = _tables(
        runner(
            [
                "base",
                "+table-list",
                "--as",
                "user",
                "--base-token",
                base_token,
                "--format",
                "json",
            ]
        )
    )
    video = _find_table(tables, settings.feishu_video_table_id, [video_table_name, "视频拆解"])
    if not video:
        if check_only:
            issues.append(f"{video_table_name}: table missing")
            video_id = ""
        elif not creator_id:
            raise RuntimeError("Creator table is required before creating the video table")
        else:
            video_id = _create_table(runner, base_token, video_table_name, video_schema(creator_id))
            created_tables.append(video_table_name)
    else:
        video_id = str(video.get("id") or "")

    video_fields_created: list[str] = []
    video_views_created: list[str] = []
    if video_id and creator_id:
        video_fields_created, video_field_issues = _ensure_fields(
            runner, base_token, video_id, video_schema(creator_id), check_only
        )
        issues.extend(f"{video_table_name}.{item}" for item in video_field_issues)
        video_views_created, video_view_issues = _ensure_views(
            runner,
            base_token,
            video_id,
            VIDEO_VISIBLE_FIELDS,
            "视频封面",
            check_only,
        )
        issues.extend(f"{video_table_name}.{item}" for item in video_view_issues)

    if not check_only:
        update_toml_section(
            settings.config_path,
            "feishu",
            {
                "base_token": base_token,
                "video_table_id": video_id,
                "creator_table_id": creator_id,
                "base_url": base_url,
            },
        )
    return {
        "ok": not issues,
        "check_only": check_only,
        "created_base": created_base,
        "base_token_configured": bool(base_token),
        "base_url": base_url,
        "video_table_id": video_id,
        "creator_table_id": creator_id,
        "created_tables": created_tables,
        "created_fields": {
            video_table_name: video_fields_created,
            creator_table_name: creator_fields_created,
        },
        "created_views": {
            video_table_name: video_views_created,
            creator_table_name: creator_views_created,
        },
        "issues": issues,
    }


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("share_text", help="Xiaohongshu share URL, xhslink URL, or full share text")
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--expected-title", default="")
    parser.add_argument("--expected-author", default="")
    parser.add_argument("--summary-file", type=pathlib.Path)
    parser.add_argument("--summary-text", default="")
    parser.add_argument("--output-root", type=pathlib.Path)
    parser.add_argument("--tikhub-api-key")
    parser.add_argument("--tikhub-base-url")
    parser.add_argument("--tikhub-env-file", type=pathlib.Path)
    parser.add_argument("--base-token")
    parser.add_argument("--video-table-id")
    parser.add_argument("--creator-table-id")
    parser.add_argument("--base-url")
    parser.add_argument("--skip-feishu", action="store_true")
    parser.add_argument("--force-create", action="store_true")


def run_namespace_to_argv(args: argparse.Namespace) -> list[str]:
    values = vars(args)
    argv = [str(values["share_text"])]
    option_names = [
        "config",
        "expected_title",
        "expected_author",
        "summary_file",
        "summary_text",
        "output_root",
        "tikhub_api_key",
        "tikhub_base_url",
        "tikhub_env_file",
        "base_token",
        "video_table_id",
        "creator_table_id",
        "base_url",
    ]
    for name in option_names:
        value = values.get(name)
        if value not in (None, ""):
            argv.extend(["--" + name.replace("_", "-"), str(value)])
    if values.get("skip_feishu"):
        argv.append("--skip-feishu")
    if values.get("force_create"):
        argv.append("--force-create")
    return argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xhs-ingest", description="Xiaohongshu to local files and Feishu")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a user configuration file")
    init_parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG_PATH)
    init_parser.add_argument("--output-root", type=pathlib.Path)
    init_parser.add_argument("--tikhub-env-file", type=pathlib.Path)
    init_parser.add_argument("--force", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Check local configuration and required tools")
    doctor_parser.add_argument("--config", type=pathlib.Path)
    doctor_parser.add_argument("--skip-feishu", action="store_true")
    doctor_parser.add_argument("--json", action="store_true", dest="json_output")

    setup_parser = subparsers.add_parser("setup-feishu", help="Create or verify the required Feishu Base schema")
    setup_parser.add_argument("--config", type=pathlib.Path)
    setup_parser.add_argument("--base-token", default="")
    setup_parser.add_argument("--base-url", default="")
    setup_parser.add_argument("--base-name", default="小红书视频素材库")
    setup_parser.add_argument("--video-table-name", default="视频笔记")
    setup_parser.add_argument("--creator-table-name", default="对标博主")
    setup_parser.add_argument("--check", action="store_true", dest="check_only")

    run_parser = subparsers.add_parser("run", help="Collect one Xiaohongshu note")
    add_run_arguments(run_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        created = write_initial_config(
            args.config,
            output_root=args.output_root,
            tikhub_env_file=args.tikhub_env_file,
            force=args.force,
        )
        if created:
            print(f"Created {args.config}")
            print("Next: set TIKHUB_API_KEY, then run xhs-ingest doctor")
            return 0
        print(f"Configuration already exists: {args.config}")
        print("Use --force only when replacing it is intended")
        return 0
    if args.command == "doctor":
        report = build_doctor_report(args.config, skip_feishu=args.skip_feishu)
        print_doctor_report(report, json_output=args.json_output)
        return 0 if report["ok"] else 1
    if args.command == "setup-feishu":
        report = setup_feishu(
            config_path=args.config,
            base_token_override=args.base_token,
            base_url_override=args.base_url,
            base_name=args.base_name,
            video_table_name=args.video_table_name,
            creator_table_name=args.creator_table_name,
            check_only=args.check_only,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    if args.command == "run":
        return ingest_xhs_note.main(run_namespace_to_argv(args))
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
