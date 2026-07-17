#!/usr/bin/env python3
"""Configuration loading for the XHS TikHub Feishu ingestion tools."""

from __future__ import annotations

import ast
import json
import os
import pathlib
from dataclasses import dataclass
from typing import Any, Mapping


APP_NAME = "xhs-tikhub-feishu-ingest"
DEFAULT_CONFIG_PATH = pathlib.Path.home() / ".config" / APP_NAME / "config.toml"
DEFAULT_OUTPUT_ROOT = pathlib.Path.home() / "xhs-ingest-output"
LEGACY_TIKHUB_ENV = pathlib.Path.home() / ".codex" / "mcp" / "tikhub" / "tikhub.env"


def _parse_value(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value[0:1] in {'"', "'"}:
        parsed = ast.literal_eval(value)
        if not isinstance(parsed, str):
            raise ValueError(f"Expected a string value, got: {raw}")
        return parsed
    try:
        return int(value)
    except ValueError:
        return value


def load_toml(path: pathlib.Path) -> dict[str, Any]:
    """Read the small TOML subset used by this project without extra packages."""
    if not path.exists():
        return {}
    data: dict[str, Any] = {}
    section: dict[str, Any] = data
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            if not section_name or "." in section_name:
                raise ValueError(f"Unsupported section on line {line_number}: {raw}")
            section = data.setdefault(section_name, {})
            if not isinstance(section, dict):
                raise ValueError(f"Invalid section on line {line_number}: {raw}")
            continue
        if "=" not in line:
            raise ValueError(f"Invalid configuration line {line_number}: {raw}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Missing key on line {line_number}: {raw}")
        section[key] = _parse_value(value)
    return data


def load_env_file(path: pathlib.Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def update_toml_section(path: pathlib.Path, section: str, values: Mapping[str, Any]) -> None:
    """Update simple scalar keys in one TOML section while preserving other content."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    header = f"[{section}]"
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(header)
        start = len(lines) - 1
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break

    remaining = dict(values)
    for index in range(start + 1, end):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            lines[index] = f"{key} = {json.dumps(str(remaining.pop(key)), ensure_ascii=False)}"
    additions = [f"{key} = {json.dumps(str(value), ensure_ascii=False)}" for key, value in remaining.items()]
    lines[end:end] = additions
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _nested(config: Mapping[str, Any], section: str, key: str, default: Any = "") -> Any:
    values = config.get(section)
    if not isinstance(values, Mapping):
        return default
    return values.get(key, default)


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return ""


def _expand_path(value: Any, default: pathlib.Path | None = None) -> pathlib.Path | None:
    chosen = value if value not in (None, "") else default
    if chosen is None:
        return None
    return pathlib.Path(os.path.expandvars(str(chosen))).expanduser()


@dataclass(frozen=True)
class Settings:
    config_path: pathlib.Path
    output_root: pathlib.Path
    tikhub_api_key: str
    tikhub_base_url: str
    tikhub_env_file: pathlib.Path | None
    feishu_base_token: str
    feishu_video_table_id: str
    feishu_creator_table_id: str
    feishu_base_url: str

    @property
    def tikhub_env(self) -> dict[str, str]:
        return {
            "TIKHUB_API_KEY": self.tikhub_api_key,
            "TIKHUB_BASE_URL": self.tikhub_base_url,
        }


def resolve_settings(
    cli: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    config_path: pathlib.Path | str | None = None,
) -> Settings:
    cli = cli or {}
    environ = environ or os.environ
    selected_config = _expand_path(
        _first(config_path, cli.get("config"), environ.get("XHS_INGEST_CONFIG")),
        DEFAULT_CONFIG_PATH,
    )
    assert selected_config is not None
    config = load_toml(selected_config)

    env_file = _expand_path(
        _first(
            cli.get("tikhub_env_file"),
            environ.get("TIKHUB_ENV_FILE"),
            _nested(config, "tikhub", "env_file"),
        )
    )
    if env_file is None:
        local_default = selected_config.parent / "tikhub.env"
        env_file = LEGACY_TIKHUB_ENV if LEGACY_TIKHUB_ENV.exists() else local_default
    file_env = load_env_file(env_file)

    output_root = _expand_path(
        _first(
            cli.get("output_root"),
            environ.get("XHS_OUTPUT_ROOT"),
            _nested(config, "output", "root"),
        ),
        DEFAULT_OUTPUT_ROOT,
    )
    assert output_root is not None

    return Settings(
        config_path=selected_config,
        output_root=output_root,
        tikhub_api_key=str(
            _first(
                cli.get("tikhub_api_key"),
                environ.get("TIKHUB_API_KEY"),
                _nested(config, "tikhub", "api_key"),
                file_env.get("TIKHUB_API_KEY"),
            )
        ),
        tikhub_base_url=str(
            _first(
                cli.get("tikhub_base_url"),
                environ.get("TIKHUB_BASE_URL"),
                _nested(config, "tikhub", "base_url"),
                file_env.get("TIKHUB_BASE_URL"),
                "https://api.tikhub.io",
            )
        ).rstrip("/"),
        tikhub_env_file=env_file,
        feishu_base_token=str(
            _first(
                cli.get("base_token"),
                environ.get("FEISHU_BASE_TOKEN"),
                _nested(config, "feishu", "base_token"),
            )
        ),
        feishu_video_table_id=str(
            _first(
                cli.get("video_table_id"),
                environ.get("FEISHU_VIDEO_TABLE_ID"),
                _nested(config, "feishu", "video_table_id"),
            )
        ),
        feishu_creator_table_id=str(
            _first(
                cli.get("creator_table_id"),
                environ.get("FEISHU_CREATOR_TABLE_ID"),
                _nested(config, "feishu", "creator_table_id"),
            )
        ),
        feishu_base_url=str(
            _first(
                cli.get("base_url"),
                environ.get("FEISHU_BASE_URL"),
                _nested(config, "feishu", "base_url"),
            )
        ),
    )
