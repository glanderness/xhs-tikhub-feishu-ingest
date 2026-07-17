import argparse
import os
import pathlib
import tempfile
import unittest
from unittest import mock


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
os.sys.path.insert(0, str(SCRIPT_DIR))

import xhs_ingest  # noqa: E402


class CliTests(unittest.TestCase):
    def test_init_creates_config_and_output_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            config_path = root / "config.toml"
            output_root = root / "output"
            created = xhs_ingest.write_initial_config(config_path, output_root=output_root)
            self.assertTrue(created)
            self.assertTrue(config_path.exists())
            self.assertTrue(output_root.exists())
            self.assertIn(str(output_root), config_path.read_text(encoding="utf-8"))

    def test_init_keeps_existing_config_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config_path = pathlib.Path(temp) / "config.toml"
            config_path.write_text("original", encoding="utf-8")
            created = xhs_ingest.write_initial_config(config_path)
            self.assertFalse(created)
            self.assertEqual(config_path.read_text(encoding="utf-8"), "original")

    def test_doctor_reports_missing_required_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "xhs_ingest.shutil.which", return_value=None
        ), mock.patch("xhs_config.LEGACY_TIKHUB_ENV", pathlib.Path(temp) / "missing.env"):
            report = xhs_ingest.build_doctor_report(pathlib.Path(temp) / "missing.toml")
        self.assertFalse(report["ok"])
        failed = {item["name"] for item in report["checks"] if item["required"] and not item["ok"]}
        self.assertIn("config", failed)
        self.assertIn("tikhub_key", failed)
        self.assertIn("lark_cli", failed)

    def test_run_arguments_are_forwarded(self) -> None:
        args = argparse.Namespace(
            command="run",
            share_text="https://xhslink.com/o/example",
            config=pathlib.Path("/tmp/config.toml"),
            expected_title="Title",
            expected_author="",
            summary_file=None,
            summary_text="",
            output_root=None,
            tikhub_api_key=None,
            tikhub_base_url=None,
            tikhub_env_file=None,
            base_token=None,
            video_table_id=None,
            creator_table_id=None,
            base_url=None,
            skip_feishu=True,
            force_create=False,
        )
        forwarded = xhs_ingest.run_namespace_to_argv(args)
        self.assertEqual(forwarded[0], "https://xhslink.com/o/example")
        self.assertIn("--config", forwarded)
        self.assertIn("--expected-title", forwarded)
        self.assertIn("--skip-feishu", forwarded)

    def test_schema_uses_creator_table_for_author_link(self) -> None:
        author = next(field for field in xhs_ingest.video_schema("tblCreator") if field["name"] == "作者")
        self.assertEqual(author["type"], "link")
        self.assertEqual(author["link_table"], "tblCreator")

    def test_find_table_prefers_configured_id(self) -> None:
        tables = [
            {"id": "tblA", "name": "视频笔记"},
            {"id": "tblB", "name": "自定义名称"},
        ]
        self.assertEqual(xhs_ingest._find_table(tables, "tblB", ["视频笔记"])["id"], "tblB")

    def test_setup_feishu_creates_base_tables_fields_views_and_updates_config(self) -> None:
        state = {
            "tables": [],
            "fields": {},
            "views": {},
            "set_card_calls": [],
            "set_visible_calls": [],
        }

        def runner(args):
            command = args[1]
            if command == "+base-create":
                state["tables"] = [{"id": "tblCreator", "name": "对标博主"}]
                state["fields"]["tblCreator"] = list(xhs_ingest.CREATOR_SCHEMA)
                state["views"]["tblCreator"] = []
                return {
                    "data": {
                        "app_token": "baseNew",
                        "table_id": "tblCreator",
                        "url": "https://example.feishu.cn/base/baseNew",
                    }
                }
            if command == "+table-list":
                return {"data": {"tables": list(state["tables"])}}
            if command == "+table-create":
                name = args[args.index("--name") + 1]
                table_id = "tblVideo" if name == "视频笔记" else "tblOther"
                schema = __import__("json").loads(args[args.index("--fields") + 1])
                state["tables"].append({"id": table_id, "name": name})
                state["fields"][table_id] = schema
                state["views"][table_id] = []
                return {"data": {"table_id": table_id}}
            table_id = args[args.index("--table-id") + 1]
            if command == "+field-list":
                return {"data": {"fields": list(state["fields"].get(table_id, []))}}
            if command == "+field-create":
                field = __import__("json").loads(args[args.index("--json") + 1])
                state["fields"].setdefault(table_id, []).append(field)
                return {"data": {"field_id": "fldNew"}}
            if command == "+view-list":
                return {"data": {"views": list(state["views"].get(table_id, []))}}
            if command == "+view-create":
                view = __import__("json").loads(args[args.index("--json") + 1])
                view_id = f"vew{len(state['views'].setdefault(table_id, [])) + 1}"
                state["views"][table_id].append({"id": view_id, **view})
                return {"data": {"view_id": view_id}}
            if command == "+view-set-card":
                state["set_card_calls"].append(args)
                return {"data": {}}
            if command == "+view-set-visible-fields":
                state["set_visible_calls"].append(args)
                return {"data": {}}
            raise AssertionError(f"Unexpected command: {command}")

        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "xhs_config.LEGACY_TIKHUB_ENV", pathlib.Path(temp) / "missing.env"
        ):
            config_path = pathlib.Path(temp) / "config.toml"
            xhs_ingest.write_initial_config(config_path)
            report = xhs_ingest.setup_feishu(config_path=config_path, runner=runner)
            settings = __import__("xhs_config").resolve_settings(config_path=config_path, environ={})

        self.assertTrue(report["ok"])
        self.assertTrue(report["created_base"])
        self.assertEqual(settings.feishu_base_token, "baseNew")
        self.assertEqual(settings.feishu_creator_table_id, "tblCreator")
        self.assertEqual(settings.feishu_video_table_id, "tblVideo")
        self.assertEqual(len(state["set_card_calls"]), 2)
        self.assertEqual(len(state["set_visible_calls"]), 4)


if __name__ == "__main__":
    unittest.main()
