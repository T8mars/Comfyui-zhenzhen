import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import midjourney_low_price_nodes as nodes


EXPECTED_OPERATIONS = [
    "midjourney-imagine",
    "midjourney-blend",
    "midjourney-describe",
    "midjourney-edits",
    "midjourney-upscale",
    "midjourney-variation",
    "midjourney-high-variation",
    "midjourney-low-variation",
    "midjourney-reroll",
    "midjourney-zoom",
    "midjourney-pan",
    "midjourney-inpaint",
    "midjourney-modal",
    "midjourney-video",
    "midjourney-remix-strong",
    "midjourney-remix-subtle",
]


def base_values():
    values = {
        name: spec[1].get("default")
        for name, spec in nodes.Comfly_midjourney_lowprice.INPUT_TYPES()[
            "required"
        ].items()
    }
    values.pop("operation")
    values.update(
        {
            "prompt": "a small red paper boat on a quiet lake",
            "task_id": "source-task",
            "index": 1,
            "direction": "left",
        }
    )
    return values


def materials(images=None, end_url="", mask_url=""):
    return {
        "image_urls": list(images or []),
        "end_url": end_url,
        "mask_url": mask_url,
    }


def valid_case(operation):
    values = base_values()
    refs = materials()
    if operation == "midjourney-imagine":
        values["task_id"] = ""
    elif operation == "midjourney-blend":
        refs = materials(
            ["https://example.test/a.png", "https://example.test/b.png"]
        )
    elif operation == "midjourney-describe":
        refs = materials(["https://example.test/a.png"])
    elif operation == "midjourney-edits":
        refs = materials(["https://example.test/a.png"])
    elif operation == "midjourney-modal":
        refs = materials(mask_url="https://example.test/mask.png")
    elif operation == "midjourney-video":
        values["task_id"] = ""
        values["index"] = -1
        refs = materials(["https://example.test/start.png"])
    return values, refs


def response(status_code, data):
    result = MagicMock()
    result.status_code = status_code
    result.text = json.dumps(data)
    result.json.return_value = data
    return result


class MidjourneyContractTests(unittest.TestCase):
    def setUp(self):
        self.node = nodes.Comfly_midjourney_lowprice()

    def test_catalog_matches_online_registry(self):
        self.assertEqual(nodes.MIDJOURNEY_OPERATIONS, EXPECTED_OPERATIONS)
        self.assertEqual(len(nodes.MIDJOURNEY_ACTION_SPECS), 16)
        for operation in EXPECTED_OPERATIONS:
            self.assertEqual(
                nodes.MIDJOURNEY_ACTION_SPECS[operation]["action"],
                operation.removeprefix("midjourney-"),
            )

    def test_node_uses_domestic_config_and_fixed_outputs(self):
        inputs = self.node.INPUT_TYPES()
        self.assertEqual(
            inputs["optional"]["api_config"][0],
            "ZHENZHEN_SEEDANCE2_CONFIG",
        )
        self.assertEqual(len(self.node.RETURN_TYPES), 17)
        self.assertEqual(
            self.node.RETURN_NAMES[:5],
            ("image1", "image2", "image3", "image4", "grid_image"),
        )

    def test_every_action_builds_only_whitelisted_fields(self):
        for operation in EXPECTED_OPERATIONS:
            values, refs = valid_case(operation)
            with self.subTest(operation=operation):
                payload = self.node._build_payload(
                    operation, refs, **values
                )
                allowed = set(
                    nodes.MIDJOURNEY_ACTION_SPECS[operation][
                        "allowed_fields"
                    ]
                )
                self.assertTrue(set(payload).issubset(allowed))
                self.assertNotIn("model", payload)

    def test_hidden_values_do_not_leak_to_unrelated_actions(self):
        values = base_values()
        values.update(
            {
                "version": "8.1",
                "style": "raw",
                "metadata_json": "",
            }
        )
        payload = self.node._build_payload(
            "midjourney-describe",
            materials(["https://example.test/a.png"]),
            **values,
        )
        self.assertEqual(
            payload, {"image_urls": ["https://example.test/a.png"]}
        )

    def test_structured_version_gates(self):
        cases = [
            ({"version": "5", "raw": True}, "raw"),
            ({"version": "6.1", "draft": True}, "draft"),
            ({"version": "7", "hd": True}, "hd"),
            ({"version": "8.1", "stop": 50}, "stop"),
            ({"version": "8.1", "niji": True}, "niji"),
        ]
        for overrides, message in cases:
            values = base_values()
            values.update({"task_id": "", **overrides})
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(
                    nodes.SeedanceLowPriceError, message
                ):
                    self.node._build_payload(
                        "midjourney-imagine",
                        materials(),
                        **values,
                    )

    def test_blend_describe_and_edits_image_counts(self):
        values = base_values()
        with self.assertRaisesRegex(
            nodes.SeedanceLowPriceError, "2-4"
        ):
            self.node._build_payload(
                "midjourney-blend",
                materials(["https://example.test/a.png"]),
                **values,
            )
        with self.assertRaisesRegex(
            nodes.SeedanceLowPriceError, "exactly one"
        ):
            self.node._build_payload(
                "midjourney-describe",
                materials(
                    [
                        "https://example.test/a.png",
                        "https://example.test/b.png",
                    ]
                ),
                **values,
            )
        with self.assertRaisesRegex(
            nodes.SeedanceLowPriceError, "image_urls|1-4"
        ):
            self.node._build_payload(
                "midjourney-edits", materials(), **values
            )

    def test_video_modes_validate_source_index_and_end_frame(self):
        values = base_values()
        values.update({"task_id": "", "index": -1})
        payload = self.node._build_payload(
            "midjourney-video",
            materials(
                ["https://example.test/start.png"],
                end_url="https://example.test/end.png",
            ),
            **values,
        )
        self.assertEqual(
            payload["video_type"], "vid_1.1_i2v_start_end_480"
        )
        values.update(
            {
                "task_id": "source-task",
                "index": 0,
                "animate_mode": "auto",
            }
        )
        payload = self.node._build_payload(
            "midjourney-video", materials(), **values
        )
        self.assertEqual(payload["index"], 0)
        with self.assertRaisesRegex(
            nodes.SeedanceLowPriceError, "exactly one source"
        ):
            self.node._build_payload(
                "midjourney-video",
                materials(["https://example.test/start.png"]),
                **values,
            )

    def test_comfy_mask_white_becomes_transparent(self):
        mask = torch.tensor([[[0.0, 1.0]]], dtype=torch.float32)
        encoded = nodes.mask_to_midjourney_png_bytes(mask)
        from PIL import Image
        from io import BytesIO

        image = Image.open(BytesIO(encoded)).convert("RGBA")
        self.assertEqual(image.getpixel((0, 0))[3], 255)
        self.assertEqual(image.getpixel((1, 0))[3], 0)


class MidjourneyClientTests(unittest.TestCase):
    def test_submit_uses_explicit_route_and_no_model(self):
        session = MagicMock()
        session.post.return_value = response(
            200,
            {
                "data": [
                    {"task_id": "task-one", "status": "submitted"}
                ]
            },
        )
        config = {
            "base_url": "https://api.seedance.nz",
            "api_key": "test-only",
            "timeout": 60,
        }
        with patch.object(
            nodes, "_midjourney_session", return_value=session
        ):
            task_id, _ = nodes.submit_midjourney_action(
                "imagine", {"prompt": "test"}, config
            )
        self.assertEqual(task_id, "task-one")
        args, kwargs = session.post.call_args
        self.assertEqual(
            args[0],
            "https://api.seedance.nz/v1/midjourney/generations/imagine",
        )
        self.assertNotIn("model", kwargs["json"])

    def test_poll_falls_back_then_pins_successful_route(self):
        session = MagicMock()
        session.get.side_effect = [
            response(404, {"message": "not found"}),
            response(
                200,
                {"data": [{"status": "SUBMITTED", "progress": 10}]},
            ),
            response(
                200,
                {
                    "data": [
                        {
                            "status": "SUCCESS",
                            "image_urls": [
                                "https://example.test/result.png"
                            ],
                        }
                    ]
                },
            ),
        ]
        config = {
            "base_url": "https://api.seedance.nz",
            "api_key": "test-only",
            "poll_interval": 0,
            "max_poll_time": 20,
        }
        with patch.object(
            nodes, "_midjourney_session", return_value=session
        ):
            final = nodes.poll_midjourney_task(
                "source-task", config, sleep=lambda _: None
            )
        self.assertEqual(
            nodes.extract_midjourney_results(final)["status"], "SUCCESS"
        )
        urls = [call.args[0] for call in session.get.call_args_list]
        self.assertTrue(urls[0].endswith("/v1/midjourney/source-task"))
        self.assertTrue(
            urls[1].endswith(
                "/v1/midjourney/tasks/source-task"
            )
        )
        self.assertEqual(urls[1], urls[2])

    def test_poll_stops_on_modal_for_inpaint(self):
        session = MagicMock()
        session.get.return_value = response(
            200,
            {"data": [{"task_id": "modal-task", "status": "MODAL"}]},
        )
        config = {
            "base_url": "https://api.seedance.nz",
            "api_key": "test-only",
            "poll_interval": 0,
            "max_poll_time": 20,
        }
        with patch.object(
            nodes, "_midjourney_session", return_value=session
        ):
            result = nodes.poll_midjourney_task(
                "modal-task",
                config,
                stop_on_modal=True,
                sleep=lambda _: None,
            )
        self.assertEqual(nodes._unwrap_task_data(result)["status"], "MODAL")

    def test_result_extraction_preserves_top_status_and_nested_text(self):
        observed = {
            "status": "SUCCESS",
            "task_id": "describe-task",
            "result": {
                "description": "A red boat on a calm lake",
                "metadata": {
                    "echoed_url": "https://example.test/do-not-return.png"
                },
            },
        }
        result = nodes.extract_midjourney_results(observed)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["text"], "A red boat on a calm lake")
        self.assertEqual(result["image_urls"], [])

    def test_cancelled_status_is_terminal_failure(self):
        session = MagicMock()
        session.get.return_value = response(
            200,
            {
                "data": [
                    {
                        "task_id": "cancelled-task",
                        "status": "CANCELLED",
                    }
                ]
            },
        )
        config = {
            "base_url": "https://api.seedance.nz",
            "api_key": "test-only",
            "poll_interval": 0,
            "max_poll_time": 20,
        }
        with patch.object(
            nodes, "_midjourney_session", return_value=session
        ):
            with self.assertRaisesRegex(
                nodes.SeedanceLowPriceError, "failed"
            ):
                nodes.poll_midjourney_task(
                    "cancelled-task",
                    config,
                    sleep=lambda _: None,
                )


class MidjourneyExecutionTests(unittest.TestCase):
    def test_sync_describe_does_not_poll(self):
        node = nodes.Comfly_midjourney_lowprice()
        values = base_values()
        values.update(
            {
                "task_id": "",
                "image_url1": "https://example.test/input.png",
            }
        )
        submitted = {
            "status": "SUCCESS",
            "description": "A quiet red paper boat",
        }
        with (
            patch.object(
                nodes,
                "resolve_config",
                return_value={
                    "base_url": "https://api.seedance.nz",
                    "api_key": "test-only",
                },
            ),
            patch.object(
                nodes,
                "submit_midjourney_action",
                return_value=(None, submitted),
            ),
            patch.object(nodes, "poll_midjourney_task") as poll,
        ):
            result = node._execute_inner(
                "midjourney-describe", None, values
            )
        poll.assert_not_called()
        self.assertEqual(result["result"][9], "A quiet red paper boat")

    def test_describe_task_without_submit_text_is_polled(self):
        node = nodes.Comfly_midjourney_lowprice()
        values = base_values()
        values.update(
            {
                "task_id": "",
                "image_url1": "https://example.test/input.png",
            }
        )
        submitted = {
            "status": "SUCCESS",
            "task_id": "describe-task",
        }
        final = {
            "status": "SUCCESS",
            "task_id": "describe-task",
            "result": {"description": "A red paper boat"},
        }
        with (
            patch.object(
                nodes,
                "resolve_config",
                return_value={
                    "base_url": "https://api.seedance.nz",
                    "api_key": "test-only",
                },
            ),
            patch.object(
                nodes,
                "submit_midjourney_action",
                return_value=("describe-task", submitted),
            ),
            patch.object(
                nodes,
                "poll_midjourney_task",
                return_value=final,
            ) as poll,
        ):
            result = node._execute_inner(
                "midjourney-describe", None, values
            )
        poll.assert_called_once()
        self.assertEqual(result["result"][9], "A red paper boat")

    def test_skip_error_returns_image_and_video_placeholders(self):
        node = nodes.Comfly_midjourney_lowprice()
        result = node.execute(
            operation="midjourney-imagine",
            prompt="",
            skip_error=True,
        )
        self.assertEqual(tuple(result["result"][0].shape), (1, 512, 512, 3))
        self.assertIsNotNone(result["result"][5])
        self.assertIn("error", result["result"][-1])


class MidjourneyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.paths = sorted(
            (PLUGIN_ROOT / "workflow").glob(
                "midjourney-*（贞贞的平价AI小屋）.json"
            )
        )

    def test_nineteen_workflows_cover_sixteen_operations(self):
        self.assertEqual(len(self.paths), 19)
        selected = set()
        for path in self.paths:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            for node in workflow["nodes"]:
                if node["type"] == "Comfly_midjourney_lowprice":
                    selected.add(node["widgets_values"][0])
                if (
                    node["type"]
                    == "Comfly_seedance2_low_price_settings"
                ):
                    self.assertEqual(
                        node["widgets_values"],
                        ["https://api.seedance.nz", ""],
                    )
        self.assertEqual(selected, set(EXPECTED_OPERATIONS))

    def test_task_actions_are_connected_and_workflows_have_no_runtime_data(self):
        task_actions = set(EXPECTED_OPERATIONS) - {
            "midjourney-imagine",
            "midjourney-blend",
            "midjourney-describe",
            "midjourney-edits",
            "midjourney-video",
        }
        for path in self.paths:
            raw = path.read_text(encoding="utf-8")
            self.assertNotRegex(raw, r"sk-[A-Za-z0-9_-]{12,}")
            self.assertNotRegex(raw, r"task_[A-Za-z0-9_-]{8,}")
            workflow = json.loads(raw)
            for node in workflow["nodes"]:
                if node["type"] != "Comfly_midjourney_lowprice":
                    continue
                operation = node["widgets_values"][0]
                if operation not in task_actions:
                    continue
                task_input = next(
                    value
                    for value in node["inputs"]
                    if value["name"] == "task_id"
                )
                self.assertIsNotNone(
                    task_input["link"], (path.name, operation)
                )

    def test_registration_button_and_dynamic_ui(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        api_link = (
            PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        dynamic_ui = (
            PLUGIN_ROOT / "web/js/midjourney_action_ui.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"Comfly_midjourney_lowprice"', comfly)
        self.assertIn(
            '"Comfly_midjourney_lowprice": "zhenzhen-midjourney-lowprice"',
            comfly,
        )
        self.assertIn('"Comfly_midjourney_lowprice"', api_link)
        for operation in EXPECTED_OPERATIONS:
            self.assertIn(f'"{operation}"', dynamic_ui)


if __name__ == "__main__":
    unittest.main()
