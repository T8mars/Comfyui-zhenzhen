"""Small paid smoke test for the concurrent image/video wrappers.

Run with the bundled ComfyUI Python and SEEDANCE_API_KEY in the process
environment. The script starts two image and two video tasks, checks that each
pair overlaps in time, and removes downloaded video files before exiting.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import threading
import time
import types

import torch


PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMFY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(COMFY_ROOT))

import comfy_api.latest  # noqa: E402,F401 - initialize public API before legacy imports


def load_modules():
    package_name = "zhenzhen_concurrent_live_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[package_name] = package
    loaded = {}
    for short_name in ("Comfly", "ComflyConcurrent"):
        module_name = f"{package_name}.{short_name}"
        spec = importlib.util.spec_from_file_location(
            module_name, PLUGIN_ROOT / f"{short_name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        loaded[short_name] = module
    return loaded["Comfly"], loaded["ComflyConcurrent"]


def run_pair(concurrent_module, mapping_key, method_name, kwargs_list, kind):
    submit_key = f"ComflyConcurrent_{mapping_key}_Submit"
    wrapper_class = concurrent_module.CONCURRENT_NODE_CLASS_MAPPINGS[submit_key]
    target_class = wrapper_class.ORIGINAL_NODE_CLASS
    original_method = getattr(target_class, method_name)
    intervals = []
    lock = threading.Lock()

    def timed_method(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return original_method(self, *args, **kwargs)
        finally:
            finished = time.perf_counter()
            with lock:
                intervals.append((started, finished))

    setattr(target_class, method_name, timed_method)
    try:
        tasks = [wrapper_class().submit(**kwargs)[0] for kwargs in kwargs_list]
        collector_class = (
            concurrent_module.ComflyConcurrentImageAwait
            if kind == "image"
            else concurrent_module.ComflyConcurrentVideoAwait
        )
        result = collector_class().wait_all(
            failure_mode="fail_fast",
            **{f"task_{index + 1}": task for index, task in enumerate(tasks)},
        )
    finally:
        setattr(target_class, method_name, original_method)

    if len(intervals) != 2:
        raise RuntimeError(f"Expected two {kind} timing intervals, got {len(intervals)}")
    overlap = min(end for _start, end in intervals) - max(
        start for start, _end in intervals
    )
    if overlap <= 0:
        raise RuntimeError(f"The two real {kind} requests did not overlap")
    return result, overlap


def remove_downloaded_videos(values):
    for value in values:
        source = None
        getter = getattr(value, "get_stream_source", None)
        if callable(getter):
            source = getter()
        elif getattr(value, "video_path", None):
            source = value.video_path
        if isinstance(source, (str, os.PathLike)):
            try:
                pathlib.Path(source).unlink()
            except OSError:
                pass


def main():
    api_key = os.environ.get("SEEDANCE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SEEDANCE_API_KEY is required")
    api_config = {"base_url": "https://api.seedance.nz", "api_key": api_key}
    _comfly, concurrent_module = load_modules()
    try:
        image_result, image_overlap = run_pair(
            concurrent_module,
            "Comfly_zhenzhen_image_nb_lowprice",
            "generate_image",
            [
                {
                    "model": "zhenzhen-image-nb-flash",
                    "prompt": "Minimal product photo of a blue glass cube on a white table",
                    "resolution": "1k",
                    "size": "1:1",
                    "n": 1,
                    "api_config": api_config,
                    "skip_error": False,
                },
                {
                    "model": "zhenzhen-image-nb-flash",
                    "prompt": "Minimal product photo of a red metal sphere on a white table",
                    "resolution": "1k",
                    "size": "1:1",
                    "n": 1,
                    "api_config": api_config,
                    "skip_error": False,
                },
            ],
            "image",
        )
        if not all(torch.is_tensor(value) for value in image_result[:2]):
            raise RuntimeError("Real image concurrency returned an invalid media type")
        print(f"real_image_pair=ok overlap_seconds={image_overlap:.2f}")

        video_result, video_overlap = run_pair(
            concurrent_module,
            "Comfly_zhenzhen_video_v31_lowprice",
            "generate",
            [
                {
                    "model": "zhenzhen-video-v31-lite",
                    "prompt": "A paper plane glides through warm sunrise clouds, smooth camera",
                    "seconds": "8",
                    "resolution": "720p",
                    "ratio": "16:9",
                    "api_config": api_config,
                    "skip_error": False,
                },
                {
                    "model": "zhenzhen-video-v31-lite",
                    "prompt": "City lights turn on at dusk, slow stable aerial camera movement",
                    "seconds": "8",
                    "resolution": "720p",
                    "ratio": "16:9",
                    "api_config": api_config,
                    "skip_error": False,
                },
            ],
            "video",
        )
        if any(value is None for value in video_result[:2]):
            raise RuntimeError("Real video concurrency returned an invalid media type")
        print(f"real_video_pair=ok overlap_seconds={video_overlap:.2f}")
        remove_downloaded_videos(video_result[:2])
    finally:
        concurrent_module._shutdown_executors()


if __name__ == "__main__":
    main()
