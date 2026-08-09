"""Opt-in concurrent submit/collect nodes for Zhenzhen API nodes.

Original node mappings are never replaced. Each eligible IMAGE or VIDEO node
gets an additional submit node backed by a bounded worker pool. Collector nodes
wait for those tasks and restore the original slot order.
"""

from __future__ import annotations

import atexit
import asyncio
import concurrent.futures
import contextvars
import copy
import inspect
import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import torch

from . import Comfly as _comfly


IMAGE_TASK_TYPE = "COMFLY_IMAGE_FUTURE"
VIDEO_TASK_TYPE = "COMFLY_VIDEO_FUTURE"
ALLOWED_MODULES = {
    "Comfly",
    "fal_batch_nodes",
    "seedance_low_price_nodes",
    "midjourney_low_price_nodes",
}


def _bounded_int(env_name: str, default: int, minimum: int = 1, maximum: int = 128) -> int:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, min(maximum, int(raw)))
    except ValueError:
        print(f"[Zhenzhen Concurrent] Invalid {env_name}; using {default}.")
        return default


IMAGE_MAX_WORKERS = _bounded_int("COMFLY_IMAGE_CONCURRENCY", 30)
VIDEO_MAX_WORKERS = _bounded_int("COMFLY_VIDEO_CONCURRENCY", 10)
IMAGE_MAX_PENDING = _bounded_int(
    "COMFLY_IMAGE_PENDING", IMAGE_MAX_WORKERS, 0, 128
)
VIDEO_MAX_PENDING = _bounded_int(
    "COMFLY_VIDEO_PENDING", VIDEO_MAX_WORKERS, 0, 128
)


def _processing_interrupted() -> bool:
    try:
        import comfy.model_management

        return bool(comfy.model_management.processing_interrupted())
    except (ImportError, AttributeError):
        return False


class _BoundedExecutor:
    def __init__(self, max_workers: int, max_pending: int, prefix: str):
        self.max_workers = max_workers
        self.max_pending = max_pending
        self._capacity = threading.BoundedSemaphore(max_workers + max_pending)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=prefix,
        )
        self._shutdown_lock = threading.Lock()
        self._shutdown = False

    def submit(self, function, *args, **kwargs) -> concurrent.futures.Future:
        while not self._capacity.acquire(timeout=0.25):
            if self._shutdown:
                raise RuntimeError("Concurrent executor has been shut down.")
            if _processing_interrupted():
                raise RuntimeError("Concurrent submission interrupted.")

        with self._shutdown_lock:
            if self._shutdown:
                self._capacity.release()
                raise RuntimeError("Concurrent executor has been shut down.")
            try:
                future = self._executor.submit(function, *args, **kwargs)
            except Exception:
                self._capacity.release()
                raise
        future.add_done_callback(lambda _future: self._capacity.release())
        return future

    def shutdown(self, wait: bool = False) -> None:
        with self._shutdown_lock:
            if self._shutdown:
                return
            self._shutdown = True
        self._executor.shutdown(wait=wait, cancel_futures=True)


_previous_executors = getattr(_comfly, "_comfly_concurrent_executors", None)
if _previous_executors:
    for _previous_executor in _previous_executors:
        try:
            _previous_executor.shutdown(wait=False)
        except Exception:
            pass

IMAGE_EXECUTOR = _BoundedExecutor(
    IMAGE_MAX_WORKERS, IMAGE_MAX_PENDING, "zhenzhen-image"
)
VIDEO_EXECUTOR = _BoundedExecutor(
    VIDEO_MAX_WORKERS, VIDEO_MAX_PENDING, "zhenzhen-video"
)
_comfly._comfly_concurrent_executors = (IMAGE_EXECUTOR, VIDEO_EXECUTOR)


def _shutdown_executors() -> None:
    IMAGE_EXECUTOR.shutdown(wait=False)
    VIDEO_EXECUTOR.shutdown(wait=False)


atexit.register(_shutdown_executors)


@dataclass(frozen=True)
class ConcurrentTask:
    future: concurrent.futures.Future
    original_node_key: str
    media_kind: str

    def cancel(self) -> bool:
        return self.future.cancel()


def _invoke_original(target_class, kwargs: Dict[str, Any]) -> Any:
    node = target_class()
    function = getattr(node, target_class.FUNCTION)
    result = function(**kwargs)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    return result


def _type_name(value: Any) -> str:
    return str(getattr(value, "value", value)).upper()


def _primary_kind(target_class) -> Optional[str]:
    return_types = getattr(target_class, "RETURN_TYPES", ())
    if not return_types:
        return None
    primary_type = _type_name(return_types[0])
    if primary_type == "IMAGE":
        return "image"
    if primary_type == "VIDEO":
        return "video"
    return None


def _eligible(target_class) -> bool:
    if getattr(target_class, "COMFLY_CONCURRENT_DISABLED", False):
        return False
    module_name = str(getattr(target_class, "__module__", "")).split(".")[-1]
    category = str(getattr(target_class, "CATEGORY", "")).lower()
    return module_name in ALLOWED_MODULES and category.startswith("zhenzhen")


def _safe_class_name(mapping_key: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", mapping_key)


def _call_original_validator(target_class, kwargs: Dict[str, Any]) -> Any:
    validator = getattr(target_class, "VALIDATE_INPUTS")
    argspec = inspect.getfullargspec(validator)
    if argspec.varkw is not None:
        return validator(**kwargs)
    accepted = set(argspec.args).union(argspec.kwonlyargs)
    return validator(**{name: value for name, value in kwargs.items() if name in accepted})


def _make_submit_class(mapping_key: str, display_name: str, target_class, kind: str):
    executor = IMAGE_EXECUTOR if kind == "image" else VIDEO_EXECUTOR
    task_type = IMAGE_TASK_TYPE if kind == "image" else VIDEO_TASK_TYPE
    pool_size = IMAGE_MAX_WORKERS if kind == "image" else VIDEO_MAX_WORKERS
    original_category = str(getattr(target_class, "CATEGORY", "zhenzhen"))

    @classmethod
    def input_types(cls):
        return copy.deepcopy(target_class.INPUT_TYPES())

    def submit(self, **kwargs):
        context = contextvars.copy_context()
        future = executor.submit(
            context.run,
            _invoke_original,
            target_class,
            dict(kwargs),
        )
        return (ConcurrentTask(future, mapping_key, kind),)

    attrs = {
        "__module__": __name__,
        "INPUT_TYPES": input_types,
        "RETURN_TYPES": (task_type,),
        "RETURN_NAMES": ("task",),
        "FUNCTION": "submit",
        "CATEGORY": f"{original_category}/Concurrent Submit",
        "DESCRIPTION": f"Runs {display_name} in the shared {kind} pool ({pool_size}).",
        "ORIGINAL_NODE_KEY": mapping_key,
        "ORIGINAL_NODE_CLASS": target_class,
        "submit": submit,
    }
    if hasattr(target_class, "VALIDATE_INPUTS"):
        @classmethod
        def validate_inputs(cls, **kwargs):
            return _call_original_validator(target_class, kwargs)

        attrs["VALIDATE_INPUTS"] = validate_inputs
    if hasattr(target_class, "INPUT_IS_LIST"):
        attrs["INPUT_IS_LIST"] = target_class.INPUT_IS_LIST

    submit_class = type(
        f"ComflyConcurrentSubmit_{_safe_class_name(mapping_key)}",
        (),
        attrs,
    )
    return submit_class, f"Concurrent Submit | {display_name}"


def _unwrap_node_result(result: Any) -> Any:
    if isinstance(result, dict):
        if "result" not in result:
            raise RuntimeError("Concurrent task returned UI data without outputs.")
        result = result["result"]
    if isinstance(result, (tuple, list)):
        if not result:
            raise RuntimeError("Concurrent task returned no outputs.")
        return result[0]
    return result


def _normalize_image(value: Any) -> torch.Tensor:
    if isinstance(value, list) and value and all(torch.is_tensor(item) for item in value):
        try:
            value = torch.cat(value, dim=0)
        except RuntimeError:
            value = value[0]
    if not torch.is_tensor(value):
        raise TypeError(f"Expected IMAGE tensor, got {type(value).__name__}.")
    return value


def _empty_image() -> torch.Tensor:
    image = torch.zeros((1, 64, 64, 3), dtype=torch.float32, device="cpu")
    image[..., 0] = 1.0
    return image


def _empty_video():
    return _comfly.ComflyVideoAdapter("")


_KEY_PATTERN = re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}\b")
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


def _sanitize_message(value: Any) -> str:
    message = str(value or "")
    message = _KEY_PATTERN.sub("[REDACTED_API_KEY]", message)
    message = _URL_PATTERN.sub("[REDACTED_URL]", message)
    return message[:500]


def _as_task(value: Any, kind: str) -> ConcurrentTask:
    if isinstance(value, ConcurrentTask):
        if value.media_kind != kind:
            raise TypeError(f"Expected {kind} task, got {value.media_kind} task.")
        return value
    if isinstance(value, concurrent.futures.Future):
        return ConcurrentTask(value, "legacy-concurrent-task", kind)
    raise TypeError(f"Expected ConcurrentTask, got {type(value).__name__}.")


def _cancel_tasks(tasks: Iterable[ConcurrentTask]) -> None:
    for task in tasks:
        task.cancel()


def _throw_if_interrupted(tasks: Iterable[ConcurrentTask]) -> None:
    if not _processing_interrupted():
        return
    _cancel_tasks(tasks)
    try:
        import comfy.model_management

        comfy.model_management.throw_exception_if_processing_interrupted()
    except ImportError:
        raise RuntimeError("Concurrent collection interrupted.") from None


def _collect(kind: str, slot_count: int, failure_mode: str, kwargs: Dict[str, Any]):
    placeholder = _empty_image if kind == "image" else _empty_video
    outputs = [placeholder() for _ in range(slot_count)]
    statuses = [
        {"slot": index + 1, "status": "not_connected"}
        for index in range(slot_count)
    ]
    pending = {}
    tasks = []
    for index in range(slot_count):
        value = kwargs.get(f"task_{index + 1}")
        if value is None:
            continue
        task = _as_task(value, kind)
        tasks.append(task)
        pending[task.future] = (index, task)
        statuses[index] = {
            "slot": index + 1,
            "status": "pending",
            "node": task.original_node_key,
        }

    progress = None
    try:
        import comfy.utils

        progress = comfy.utils.ProgressBar(max(1, len(pending)))
    except (ImportError, AttributeError):
        pass

    completed = 0
    while pending:
        _throw_if_interrupted(tasks)
        done, _ = concurrent.futures.wait(
            tuple(pending), timeout=0.25, return_when=concurrent.futures.FIRST_COMPLETED
        )
        if not done:
            continue
        for future in done:
            index, task = pending.pop(future)
            try:
                primary = _unwrap_node_result(future.result())
                if kind == "image":
                    primary = _normalize_image(primary)
                elif primary is None:
                    raise RuntimeError("Video task returned an empty primary output.")
                outputs[index] = primary
                statuses[index] = {
                    "slot": index + 1,
                    "status": "success",
                    "node": task.original_node_key,
                }
            except Exception as exc:
                error = _sanitize_message(f"{type(exc).__name__}: {exc}")
                statuses[index] = {
                    "slot": index + 1,
                    "status": "failed",
                    "node": task.original_node_key,
                    "error": error,
                }
                if failure_mode == "fail_fast":
                    _cancel_tasks(
                        queued_task for _queued, queued_task in pending.values()
                    )
                    raise RuntimeError(
                        f"Concurrent {kind} task {index + 1} failed: {error}"
                    ) from None
            completed += 1
            if progress is not None:
                progress.update_absolute(completed, max(1, len(tasks)))

    summary = json.dumps(
        {"kind": kind, "completed": completed, "slots": statuses},
        ensure_ascii=False,
    )
    return tuple(outputs) + (summary,)


def _collector_input_types(task_type: str, slot_count: int):
    inputs = {
        "required": {
            "task_1": (task_type,),
            "failure_mode": (["fail_fast", "placeholder"], {"default": "fail_fast"}),
        },
        "optional": {},
    }
    for index in range(2, slot_count + 1):
        inputs["optional"][f"task_{index}"] = (task_type,)
    return inputs


class ComflyConcurrentImageAwait:
    @classmethod
    def INPUT_TYPES(cls):
        return _collector_input_types(IMAGE_TASK_TYPE, IMAGE_MAX_WORKERS)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    RETURN_TYPES = tuple(["IMAGE"] * IMAGE_MAX_WORKERS + ["STRING"])
    RETURN_NAMES = tuple(
        [f"image_{index}" for index in range(1, IMAGE_MAX_WORKERS + 1)]
        + ["status"]
    )
    FUNCTION = "wait_all"
    CATEGORY = "zhenzhen/Concurrent Collect"
    OUTPUT_NODE = True

    def wait_all(self, failure_mode: str, **kwargs):
        return _collect("image", IMAGE_MAX_WORKERS, failure_mode, kwargs)


class ComflyConcurrentVideoAwait:
    @classmethod
    def INPUT_TYPES(cls):
        return _collector_input_types(VIDEO_TASK_TYPE, VIDEO_MAX_WORKERS)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    RETURN_TYPES = tuple([_comfly.IO.VIDEO] * VIDEO_MAX_WORKERS + ["STRING"])
    RETURN_NAMES = tuple(
        [f"video_{index}" for index in range(1, VIDEO_MAX_WORKERS + 1)]
        + ["status"]
    )
    FUNCTION = "wait_all"
    CATEGORY = "zhenzhen/Concurrent Collect"
    OUTPUT_NODE = True

    def wait_all(self, failure_mode: str, **kwargs):
        return _collect("video", VIDEO_MAX_WORKERS, failure_mode, kwargs)


CONCURRENT_NODE_CLASS_MAPPINGS = {
    "ComflyConcurrent_Image_Await": ComflyConcurrentImageAwait,
    "ComflyConcurrent_Video_Await": ComflyConcurrentVideoAwait,
}
CONCURRENT_NODE_DISPLAY_NAME_MAPPINGS = {
    "ComflyConcurrent_Image_Await": f"Concurrent Collect Images ({IMAGE_MAX_WORKERS})",
    "ComflyConcurrent_Video_Await": f"Concurrent Collect Videos ({VIDEO_MAX_WORKERS})",
}


CONCURRENT_WRAPPED_NODE_KEYS = []
for original_key, original_class in tuple(_comfly.NODE_CLASS_MAPPINGS.items()):
    kind = _primary_kind(original_class)
    if kind is None or not _eligible(original_class):
        continue
    display_name = _comfly.NODE_DISPLAY_NAME_MAPPINGS.get(original_key, original_key)
    submit_class, submit_display_name = _make_submit_class(
        original_key, display_name, original_class, kind
    )
    submit_key = f"ComflyConcurrent_{original_key}_Submit"
    if submit_key in _comfly.NODE_CLASS_MAPPINGS:
        raise RuntimeError(f"Concurrent node key collision: {submit_key}")
    CONCURRENT_NODE_CLASS_MAPPINGS[submit_key] = submit_class
    CONCURRENT_NODE_DISPLAY_NAME_MAPPINGS[submit_key] = submit_display_name
    CONCURRENT_WRAPPED_NODE_KEYS.append(original_key)


print(
    f"[Zhenzhen Concurrent] Registered {len(CONCURRENT_WRAPPED_NODE_KEYS)} submit nodes "
    f"(image={IMAGE_MAX_WORKERS}, video={VIDEO_MAX_WORKERS})."
)


__all__ = [
    "CONCURRENT_NODE_CLASS_MAPPINGS",
    "CONCURRENT_NODE_DISPLAY_NAME_MAPPINGS",
    "CONCURRENT_WRAPPED_NODE_KEYS",
    "ConcurrentTask",
    "IMAGE_MAX_WORKERS",
    "VIDEO_MAX_WORKERS",
]
