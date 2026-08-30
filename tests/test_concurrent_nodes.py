import concurrent.futures
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import config_store
import seedance_low_price_nodes


class _FakeVideo:
    def __init__(self, value):
        self.value = value


class _FakeIO:
    VIDEO = "VIDEO"


class _ConcurrencyProbe:
    lock = threading.Lock()
    active = 0
    maximum = 0
    barrier = None

    @classmethod
    def reset(cls, parties):
        with cls.lock:
            cls.active = 0
            cls.maximum = 0
            cls.barrier = threading.Barrier(parties)

    @classmethod
    def enter(cls):
        with cls.lock:
            cls.active += 1
            cls.maximum = max(cls.maximum, cls.active)
            barrier = cls.barrier
        barrier.wait(timeout=10)

    @classmethod
    def leave(cls):
        with cls.lock:
            cls.active -= 1


class _FakeImageNode:
    __module__ = "Comfly"
    RETURN_TYPES = ("IMAGE", "STRING")
    FUNCTION = "run"
    CATEGORY = "zhenzhen/Test"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "index": ("INT", {"default": 0}),
                "delay": ("FLOAT", {"default": 0.01}),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(cls, index, delay):
        return True if index >= 0 and delay >= 0 else "invalid probe input"

    def run(self, index, delay):
        _ConcurrencyProbe.enter()
        try:
            time.sleep(delay)
            return (torch.full((1, 1, 1, 3), float(index)), f"aux-{index}")
        finally:
            _ConcurrencyProbe.leave()


class _FakeVideoNode:
    __module__ = "Comfly"
    RETURN_TYPES = ("VIDEO", "STRING")
    FUNCTION = "run"
    CATEGORY = "zhenzhen/Test"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"index": ("INT", {"default": 0})}}

    def run(self, index):
        _ConcurrencyProbe.enter()
        try:
            time.sleep(0.02)
            return (_FakeVideo(index), f"aux-{index}")
        finally:
            _ConcurrencyProbe.leave()


def _load_concurrent_module():
    package_name = "zhenzhen_concurrent_unit_package"
    for name in list(sys.modules):
        if name == package_name or name.startswith(f"{package_name}."):
            del sys.modules[name]

    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[package_name] = package

    fake_comfly = types.ModuleType(f"{package_name}.Comfly")
    fake_comfly.IO = _FakeIO
    fake_comfly.ComflyVideoAdapter = _FakeVideo
    fake_comfly.NODE_CLASS_MAPPINGS = {
        "FakeImage": _FakeImageNode,
        "FakeVideo": _FakeVideoNode,
    }
    fake_comfly.NODE_DISPLAY_NAME_MAPPINGS = {
        "FakeImage": "Fake Image",
        "FakeVideo": "Fake Video",
    }
    sys.modules[fake_comfly.__name__] = fake_comfly

    module_name = f"{package_name}.ComflyConcurrent"
    spec = importlib.util.spec_from_file_location(
        module_name, PLUGIN_ROOT / "ComflyConcurrent.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class ConcurrentNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.concurrent = _load_concurrent_module()

    @classmethod
    def tearDownClass(cls):
        cls.concurrent._shutdown_executors()

    def test_registration_is_additive_and_validation_is_proxied(self):
        mappings = self.concurrent.CONCURRENT_NODE_CLASS_MAPPINGS
        self.assertEqual(
            set(mappings),
            {
                "ComflyConcurrent_Image_Await",
                "ComflyConcurrent_Video_Await",
                "ComflyConcurrent_FakeImage_Submit",
                "ComflyConcurrent_FakeVideo_Submit",
            },
        )
        wrapper = mappings["ComflyConcurrent_FakeImage_Submit"]
        self.assertIs(wrapper.ORIGINAL_NODE_CLASS, _FakeImageNode)
        self.assertFalse(hasattr(wrapper, "IS_CHANGED"))
        self.assertTrue(wrapper.VALIDATE_INPUTS(index=1, delay=0.1))
        self.assertEqual(
            wrapper.VALIDATE_INPUTS(index=-1, delay=0.1),
            "invalid probe input",
        )
        copied = wrapper.INPUT_TYPES()
        copied["required"]["index"][1]["default"] = 99
        self.assertEqual(_FakeImageNode.INPUT_TYPES()["required"]["index"][1]["default"], 0)

    def test_image_pool_reaches_30_and_preserves_slot_order(self):
        self.assertEqual(self.concurrent.IMAGE_MAX_WORKERS, 30)
        _ConcurrencyProbe.reset(30)
        wrapper = self.concurrent.CONCURRENT_NODE_CLASS_MAPPINGS[
            "ComflyConcurrent_FakeImage_Submit"
        ]
        tasks = [wrapper().submit(index=index, delay=0.02)[0] for index in range(30)]
        kwargs = {f"task_{index + 1}": task for index, task in enumerate(tasks)}
        result = self.concurrent.ComflyConcurrentImageAwait().wait_all(
            failure_mode="fail_fast", **kwargs
        )
        self.assertEqual(_ConcurrencyProbe.maximum, 30)
        self.assertEqual(len(result), 31)
        for index, image in enumerate(result[:-1]):
            self.assertEqual(float(image[0, 0, 0, 0]), float(index))
        status = json.loads(result[-1])
        self.assertEqual(status["completed"], 30)
        self.assertTrue(all(slot["status"] == "success" for slot in status["slots"]))

    def test_video_pool_reaches_10_and_preserves_slot_order(self):
        self.assertEqual(self.concurrent.VIDEO_MAX_WORKERS, 10)
        _ConcurrencyProbe.reset(10)
        wrapper = self.concurrent.CONCURRENT_NODE_CLASS_MAPPINGS[
            "ComflyConcurrent_FakeVideo_Submit"
        ]
        tasks = [wrapper().submit(index=index)[0] for index in range(10)]
        kwargs = {f"task_{index + 1}": task for index, task in enumerate(tasks)}
        result = self.concurrent.ComflyConcurrentVideoAwait().wait_all(
            failure_mode="fail_fast", **kwargs
        )
        self.assertEqual(_ConcurrencyProbe.maximum, 10)
        self.assertEqual([video.value for video in result[:-1]], list(range(10)))

    def test_legacy_future_and_failure_modes_are_supported_and_redacted(self):
        successful = concurrent.futures.Future()
        successful.set_result((torch.ones((1, 1, 1, 3)), "kept internally"))
        result = self.concurrent.ComflyConcurrentImageAwait().wait_all(
            failure_mode="placeholder", task_1=successful
        )
        self.assertTrue(torch.equal(result[0], torch.ones((1, 1, 1, 3))))

        failed = concurrent.futures.Future()
        failed.set_exception(
            RuntimeError(
                "key " + "sk-" + "1234567890SECRET "
                "at https://example.invalid/file?token=secret"
            )
        )
        result = self.concurrent.ComflyConcurrentImageAwait().wait_all(
            failure_mode="placeholder", task_1=failed
        )
        status = result[-1]
        self.assertNotIn("1234567890SECRET", status)
        self.assertNotIn("example.invalid", status)
        self.assertIn("REDACTED_API_KEY", status)
        self.assertIn("REDACTED_URL", status)

        failed_fast = concurrent.futures.Future()
        failed_fast.set_exception(RuntimeError("expected failure"))
        with self.assertRaisesRegex(RuntimeError, "expected failure"):
            self.concurrent.ComflyConcurrentImageAwait().wait_all(
                failure_mode="fail_fast", task_1=failed_fast
            )


class ConcurrentSafetyTests(unittest.TestCase):
    def test_project_config_is_never_read_written_or_created(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = Path(temp_dir) / "Comflyapi.json"
            with patch.object(config_store, "CONFIG_PATH", test_path):
                test_path.write_text('{"api_key":"disk-key"}', encoding="utf-8")
                original = test_path.read_bytes()
                self.assertEqual(config_store.read_project_config(), {})
                config_store.write_project_config({"api_key": "workflow-key"})
                self.assertEqual(test_path.read_bytes(), original)

                test_path.unlink()
                config_store.write_project_config({"api_key": "workflow-key"})
                self.assertFalse(test_path.exists())

    def test_blank_seedance_workflow_key_never_falls_back(self):
        settings = seedance_low_price_nodes.Comfly_seedance2_low_price_settings()
        built = settings.build("https://api.seedance.nz", "")[0]
        self.assertEqual(built["api_key"], "")
        with patch.dict(
            os.environ,
            {"SEEDANCE_API_KEY": "environment-key"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                seedance_low_price_nodes.SeedanceLowPriceError,
                "empty api_key",
            ):
                seedance_low_price_nodes.resolve_config(built)

    def test_seedance_sessions_are_thread_local_with_sized_pools(self):
        barrier = threading.Barrier(2)

        def session_identity():
            first = seedance_low_price_nodes._get_session()
            second = seedance_low_price_nodes._get_session()
            barrier.wait(timeout=5)
            adapter = first.get_adapter("https://api.seedance.nz/")
            return id(first), id(second), adapter._pool_maxsize

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: session_identity(), range(2)))
        self.assertEqual(results[0][0], results[0][1])
        self.assertEqual(results[1][0], results[1][1])
        self.assertNotEqual(results[0][0], results[1][0])
        self.assertTrue(all(pool_size >= 30 for _, _, pool_size in results))

    def test_frontend_normalizes_submit_aliases_and_lists_domestic_nodes(self):
        dynamic_files = [
            "hailuo_h3_model_ui.js",
            "midjourney_action_ui.js",
            "suno_action_ui.js",
            "zhenzhen_nb_v31_ui.js",
            "zhenzhen_image_g2_api_key_link.js",
        ]
        for filename in dynamic_files:
            source = (PLUGIN_ROOT / "web" / "js" / filename).read_text(encoding="utf-8")
            self.assertIn("function originalNodeName(name)", source, filename)
            self.assertIn('const prefix = "ComflyConcurrent_"', source, filename)
            self.assertIn('const suffix = "_Submit"', source, filename)

        api_link = (PLUGIN_ROOT / "web" / "js" / "zhenzhen_image_g2_api_key_link.js").read_text(encoding="utf-8")
        for node_name in (
            "Comfly_hailuo_h3_video_lowprice",
            "Comfly_midjourney_lowprice",
            "Comfly_suno_music_lowprice",
            "Comfly_zhenzhen_image_nb_lowprice",
        ):
            self.assertIn(f'"{node_name}"', api_link)

    def test_concurrent_workflows_are_connected_and_contain_no_runtime_secrets(self):
        expectations = {
            "并发示例-图片多任务（30路上限）.json": (
                "COMFLY_IMAGE_FUTURE",
                "ComflyConcurrent_Image_Await",
            ),
            "并发示例-视频多任务（10路上限）.json": (
                "COMFLY_VIDEO_FUTURE",
                "ComflyConcurrent_Video_Await",
            ),
        }
        for filename, (task_type, collector_type) in expectations.items():
            path = PLUGIN_ROOT / "workflow" / filename
            source = path.read_text(encoding="utf-8")
            workflow = json.loads(source)
            node_types = [node["type"] for node in workflow["nodes"]]
            self.assertEqual(sum(name.endswith("_Submit") for name in node_types), 2)
            self.assertIn(collector_type, node_types)
            self.assertEqual(sum(link[5] == task_type for link in workflow["links"]), 2)
            self.assertNotRegex(source, r"sk-[A-Za-z0-9_-]{8,}")
            self.assertNotIn("task_id\": \"", source)
            settings = next(node for node in workflow["nodes"] if node["type"] == "T8Zhenzhen_API_Settings")
            self.assertEqual(settings["widgets_values"][1], "")


if __name__ == "__main__":
    unittest.main()
