from __future__ import annotations

import base64
import importlib.util
import io
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import torch
from PIL import Image


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(COMFY_ROOT))

import comfy_api.latest  # noqa: E402,F401


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self.payload


class _ProgressBar:
    def __init__(self, _total):
        self.values = []

    def update_absolute(self, value):
        self.values.append(value)


def _load_comfly():
    package_name = "zhenzhen_nano_banana2_test_package"
    for name in list(sys.modules):
        if name == package_name or name.startswith(f"{package_name}."):
            del sys.modules[name]

    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[package_name] = package
    module_name = f"{package_name}.Comfly"
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_ROOT / "Comfly.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _encoded_png(size=(3, 2), color=(25, 100, 220)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class NanoBanana2AsyncCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comfly = _load_comfly()

    def setUp(self):
        self.node_class = self.comfly.NODE_CLASS_MAPPINGS[
            "Comfly_nano_banana2_edit"
        ]

    def test_original_node_key_maps_to_compatible_subclass_without_schema_changes(self):
        self.assertIs(
            self.node_class,
            self.comfly.Comfly_nano_banana2_edit_async_compatible,
        )
        self.assertTrue(
            issubclass(
                self.node_class,
                self.comfly.Comfly_nano_banana2_edit,
            )
        )
        inputs = self.node_class.INPUT_TYPES()
        self.assertEqual(
            inputs["required"]["model"][0],
            [
                "nano-banana-2",
                "nano-banana-pro",
                "nano-banana-pro-2k",
                "nano-banana-pro-4k",
            ],
        )
        self.assertEqual(self.node_class.RETURN_TYPES, ("IMAGE", "STRING", "STRING"))

    def test_edit_accepts_task_response_polls_and_downloads_nested_result(self):
        result_url = "https://example.invalid/generated.png"
        post = Mock(return_value=_Response({"data": {"task_id": "task-123"}}))
        get = Mock(
            side_effect=[
                _Response({"data": {"status": "processing"}}),
                _Response(
                    {
                        "data": {
                            "status": "completed",
                            "result": {"images": [{"url": result_url}]},
                        }
                    }
                ),
            ]
        )
        downloaded = Image.new("RGB", (5, 4), (10, 20, 30))

        with (
            patch.object(self.comfly.requests, "post", post),
            patch.object(self.comfly.requests, "get", get),
            patch.object(
                self.comfly,
                "download_image_with_retry",
                return_value=downloaded,
            ) as download,
            patch.object(self.comfly.time, "sleep"),
            patch.object(self.comfly.comfy.utils, "ProgressBar", _ProgressBar),
        ):
            image, response, image_url = self.node_class().generate_image(
                prompt="turn the square blue",
                mode="img2img",
                model="nano-banana-pro",
                aspect_ratio="1:1",
                image_size="1K",
                image1=torch.zeros((1, 8, 8, 3), dtype=torch.float32),
                apikey="workflow-key",
                response_format="url",
                seed=7,
            )

        self.assertEqual(tuple(image.shape), (1, 4, 5, 3))
        self.assertEqual(image_url, result_url)
        self.assertIn("Task status: completed", response)
        post_kwargs = post.call_args.kwargs
        self.assertEqual(post.call_args.args[0], f"{self.comfly.baseurl}/v1/images/edits")
        self.assertEqual(post_kwargs["params"], {"async": "true"})
        self.assertEqual(len(post_kwargs["files"]), 1)
        self.assertEqual(post_kwargs["data"]["seed"], "7")
        self.assertEqual(
            get.call_args_list[-1].args[0],
            f"{self.comfly.baseurl}/v1/images/tasks/task-123",
        )
        download.assert_called_once_with(result_url, timeout=600)

    def test_synchronous_base64_response_remains_supported(self):
        post = Mock(
            return_value=_Response(
                {"data": [{"b64_json": _encoded_png(size=(6, 3))}]}
            )
        )
        with (
            patch.object(self.comfly.requests, "post", post),
            patch.object(self.comfly.requests, "get") as get,
            patch.object(self.comfly.comfy.utils, "ProgressBar", _ProgressBar),
        ):
            image, response, image_url = self.node_class().generate_image(
                prompt="a blue square",
                mode="text2img",
                model="nano-banana-pro",
                aspect_ratio="1:1",
                image_size="1K",
                apikey="workflow-key",
                response_format="b64_json",
            )

        self.assertEqual(tuple(image.shape), (1, 3, 6, 3))
        self.assertEqual(image_url, "")
        self.assertIn("Base64 data", response)
        self.assertNotIn("params", post.call_args.kwargs)
        get.assert_not_called()

    def test_response_normalizers_cover_nested_json_and_task_id_shapes(self):
        result_url = "https://example.invalid/nested.png"
        result = {
            "data": {
                "output": json.dumps(
                    {"image_urls": [result_url, result_url]}
                )
            }
        }
        self.assertEqual(
            self.comfly._comfly_collect_image_items(result),
            [{"url": result_url}],
        )
        self.assertEqual(self.comfly._comfly_image_task_id({"data": "task-456"}), "task-456")
        self.assertEqual(
            self.comfly._comfly_image_task_id(
                {"result": {"output": {"taskId": 789}}}
            ),
            "789",
        )

    def test_failed_async_task_is_not_reported_as_a_missing_image(self):
        post = Mock(return_value=_Response({"data": "task-failed"}))
        get = Mock(
            return_value=_Response(
                {
                    "data": {
                        "status": "failed",
                        "error": {"message": "upstream rejected image"},
                    }
                }
            )
        )
        with (
            patch.object(self.comfly.requests, "post", post),
            patch.object(self.comfly.requests, "get", get),
            patch.object(self.comfly.comfy.utils, "ProgressBar", _ProgressBar),
        ):
            with self.assertRaisesRegex(RuntimeError, "upstream rejected image"):
                self.node_class().generate_image(
                    prompt="edit",
                    mode="img2img",
                    image1=torch.zeros((1, 8, 8, 3), dtype=torch.float32),
                    apikey="workflow-key",
                )


if __name__ == "__main__":
    unittest.main()
