from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(COMFY_ROOT))

import comfy_api.latest  # noqa: E402,F401


def _load_comfly():
    package_name = "zhenzhen_legacy_midjourney_test_package"
    for name in list(sys.modules):
        if name == package_name or name.startswith(f"{package_name}."):
            del sys.modules[name]

    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[package_name] = package
    module_name = f"{package_name}.Comfly"
    spec = importlib.util.spec_from_file_location(
        module_name, PLUGIN_ROOT / "Comfly.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _ProgressBar:
    def update_absolute(self, _value):
        return None


class LegacyMidjourneyHardeningTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.comfly = _load_comfly()

    def test_sync_polling_stops_after_repeated_fetch_failures(self):
        node = self.comfly.Comfly_Mj()
        submit = Mock(return_value="task-123")
        fetch = Mock(side_effect=RuntimeError("temporary poll failure"))

        with (
            patch.object(
                node, "midjourney_submit_imagine_task_sync", submit
            ),
            patch.object(node, "midjourney_fetch_task_result_sync", fetch),
            patch.object(self.comfly.time, "monotonic", return_value=0),
            patch.object(self.comfly.time, "sleep"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "polling failed repeatedly"
            ):
                node.process_text_midjourney_sync(
                    "prompt",
                    _ProgressBar(),
                    "1:1",
                    None,
                    None,
                    None,
                    None,
                    False,
                    1,
                    False,
                    None,
                    None,
                    None,
                    0,
                )

        self.assertEqual(
            fetch.call_count,
            self.comfly.LEGACY_MIDJOURNEY_MAX_CONSECUTIVE_POLL_FAILURES,
        )

    async def test_action_and_task_polling_have_deadlines(self):
        action_node = self.comfly.Comfly_Mju()
        initial_result = {
            "status": "SUCCESS",
            "properties": {"messageId": "message-123"},
        }
        with (
            patch.object(
                self.comfly,
                "LEGACY_MIDJOURNEY_POLL_TIMEOUT_SECONDS",
                0,
            ),
            patch.object(
                action_node,
                "midjourney_fetch_task_result",
                AsyncMock(return_value=initial_result),
            ),
            patch.object(
                action_node,
                "midjourney_submit_action",
                AsyncMock(return_value={"result": "new-task"}),
            ),
        ):
            with self.assertRaisesRegex(
                action_node.MidjourneyError, "polling timed out"
            ):
                await action_node.process_input("task-123", U1=True)

        task_node = self.comfly.Comfly_Mjv()
        with patch.object(
            self.comfly,
            "LEGACY_MIDJOURNEY_POLL_TIMEOUT_SECONDS",
            0,
        ):
            with self.assertRaisesRegex(TimeoutError, "polling timed out"):
                await task_node.process_task("task-123")

    def test_legacy_media_downloads_have_explicit_timeouts(self):
        response = Mock()
        response.iter_content.return_value = [b"video"]
        adapter = self.comfly.ComflyVideoAdapter(
            "https://cdn.example.invalid/result.mp4"
        )

        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "result.mp4"
            with patch.object(
                self.comfly.requests, "get", return_value=response
            ) as get:
                self.assertTrue(adapter.save_to(str(output_path)))
            self.assertEqual(output_path.read_bytes(), b"video")

        get.assert_called_once_with(
            "https://cdn.example.invalid/result.mp4",
            stream=True,
            timeout=300,
        )
        self.assertIn(
            "timeout=300", inspect.getsource(self.comfly.create_audio_object)
        )
        self.assertIn(
            "timeout=300",
            inspect.getsource(self.comfly.Comfly_Mju.process_input),
        )
        self.assertIn(
            "deadline",
            inspect.getsource(self.comfly.Comfly_Mju.process_custom_id),
        )


if __name__ == "__main__":
    unittest.main()
