import os
import pathlib
import tempfile
import unittest
from unittest import mock


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
os.sys.path.insert(0, str(SCRIPT_DIR))

from xhs_config import resolve_settings, update_toml_section  # noqa: E402


class SettingsTests(unittest.TestCase):
    def write_config(self, root: pathlib.Path) -> pathlib.Path:
        path = root / "config.toml"
        path.write_text(
            """
[tikhub]
api_key = "from-config"
base_url = "https://config.example"

[feishu]
base_token = "base-config"
video_table_id = "video-config"
creator_table_id = "creator-config"
base_url = "https://feishu.example/base/base-config"

[output]
root = "~/configured-output"
""".strip(),
            encoding="utf-8",
        )
        return path

    def test_config_values_are_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_config(pathlib.Path(temp))
            settings = resolve_settings(config_path=path, environ={})
        self.assertEqual(settings.tikhub_api_key, "from-config")
        self.assertEqual(settings.feishu_base_token, "base-config")
        self.assertEqual(settings.output_root, pathlib.Path.home() / "configured-output")

    def test_environment_overrides_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_config(pathlib.Path(temp))
            settings = resolve_settings(
                config_path=path,
                environ={
                    "TIKHUB_API_KEY": "from-env",
                    "FEISHU_BASE_TOKEN": "base-env",
                    "XHS_OUTPUT_ROOT": "/tmp/from-env",
                },
            )
        self.assertEqual(settings.tikhub_api_key, "from-env")
        self.assertEqual(settings.feishu_base_token, "base-env")
        self.assertEqual(settings.output_root, pathlib.Path("/tmp/from-env"))

    def test_cli_overrides_environment_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_config(pathlib.Path(temp))
            settings = resolve_settings(
                cli={
                    "tikhub_api_key": "from-cli",
                    "base_token": "base-cli",
                    "output_root": pathlib.Path("/tmp/from-cli"),
                },
                config_path=path,
                environ={"TIKHUB_API_KEY": "from-env", "FEISHU_BASE_TOKEN": "base-env"},
            )
        self.assertEqual(settings.tikhub_api_key, "from-cli")
        self.assertEqual(settings.feishu_base_token, "base-cli")
        self.assertEqual(settings.output_root, pathlib.Path("/tmp/from-cli"))

    def test_missing_config_uses_portable_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp, mock.patch(
            "xhs_config.LEGACY_TIKHUB_ENV", pathlib.Path(temp) / "missing.env"
        ):
            path = pathlib.Path(temp) / "missing.toml"
            settings = resolve_settings(config_path=path, environ={})
        self.assertEqual(settings.output_root, pathlib.Path.home() / "xhs-ingest-output")
        self.assertEqual(settings.feishu_base_token, "")
        self.assertEqual(settings.tikhub_base_url, "https://api.tikhub.io")

    def test_update_toml_section_preserves_other_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_config(pathlib.Path(temp))
            update_toml_section(
                path,
                "feishu",
                {"base_token": "new-base", "video_table_id": "new-video"},
            )
            settings = resolve_settings(config_path=path, environ={})
        self.assertEqual(settings.tikhub_api_key, "from-config")
        self.assertEqual(settings.feishu_base_token, "new-base")
        self.assertEqual(settings.feishu_video_table_id, "new-video")


if __name__ == "__main__":
    unittest.main()
