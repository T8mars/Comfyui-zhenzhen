import copy
import functools
import inspect
from typing import Any, Dict, Mapping, Tuple


EXECUTION_SEED_NAME = "seed"
EXECUTION_SEED_MAX = 0xFFFFFFFFFFFFFFFF
EXECUTION_SEED_SPEC = (
    "INT",
    {
        "default": 0,
        "min": 0,
        "max": EXECUTION_SEED_MAX,
        "step": 1,
        "control_after_generate": True,
        "tooltip": (
            "Execution seed for ComfyUI cache control. Fixed reuses the cached result; "
            "randomize/increment/decrement requests a new run. This compatibility seed "
            "is not sent to APIs that do not expose a native seed parameter."
        ),
    },
)

_GENERATION_OUTPUT_TYPES = frozenset({"IMAGE", "VIDEO", "AUDIO", "FILE_3D"})
_INPUT_SECTIONS = ("required", "optional", "hidden")
_INSTALLED_MARKER = "_comfly_execution_seed_installed"
_NON_GENERATION_NODE_KEYS = frozenset(
    {
        "Comfly_zhenzhen_upscaler_lowprice",
        "Comfly_topaz_upscale_fal",
        "Comfly_bria_video_background_removal_v3_fal",
        "Comfly_pixelcut_video_background_removal_fal",
    }
)


def _type_name(value: Any) -> str:
    return str(getattr(value, "value", value)).upper()


def _has_generation_output(node_class: type) -> bool:
    return any(
        _type_name(return_type) in _GENERATION_OUTPUT_TYPES
        for return_type in getattr(node_class, "RETURN_TYPES", ())
    )


def _has_seed(input_types: Mapping[str, Mapping[str, Any]]) -> bool:
    return any(
        EXECUTION_SEED_NAME in input_types.get(section, {})
        for section in _INPUT_SECTIONS
    )


def _wrap_execution_function(node_class: type) -> bool:
    function_name = str(getattr(node_class, "FUNCTION", ""))
    if not function_name:
        return False

    original = inspect.getattr_static(node_class, function_name, None)
    descriptor_type = None
    if isinstance(original, (classmethod, staticmethod)):
        descriptor_type = type(original)
        original = original.__func__
    if not callable(original):
        return False

    if inspect.iscoroutinefunction(original):
        @functools.wraps(original)
        async def execution_seed_function(*args, __function=original, **kwargs):
            kwargs.pop(EXECUTION_SEED_NAME, None)
            return await __function(*args, **kwargs)
    else:
        @functools.wraps(original)
        def execution_seed_function(*args, __function=original, **kwargs):
            kwargs.pop(EXECUTION_SEED_NAME, None)
            return __function(*args, **kwargs)

    if descriptor_type is not None:
        setattr(node_class, function_name, descriptor_type(execution_seed_function))
    else:
        setattr(node_class, function_name, execution_seed_function)
    return True


def _install_on_class(node_class: type) -> bool:
    if node_class.__dict__.get(_INSTALLED_MARKER, False):
        return True
    if not _has_generation_output(node_class):
        return False

    original_input_types = getattr(node_class, "INPUT_TYPES", None)
    if not callable(original_input_types):
        return False
    current_input_types = original_input_types()
    if _has_seed(current_input_types):
        return False
    if not _wrap_execution_function(node_class):
        return False

    @classmethod
    @functools.wraps(original_input_types)
    def input_types(cls, __input_types=original_input_types):
        inputs = copy.deepcopy(__input_types())
        optional = inputs.setdefault("optional", {})
        optional[EXECUTION_SEED_NAME] = copy.deepcopy(EXECUTION_SEED_SPEC)
        return inputs

    node_class.INPUT_TYPES = input_types
    setattr(node_class, _INSTALLED_MARKER, True)
    return True


def install_execution_seed_controls(
    node_mappings: Mapping[str, type],
) -> Tuple[str, ...]:
    """Append a cache-only seed to media generation nodes that do not have one."""
    excluded_classes = {
        node_mappings[key]
        for key in _NON_GENERATION_NODE_KEYS
        if key in node_mappings
    }
    installed_classes: Dict[type, bool] = {}
    installed_keys = []
    for mapping_key, node_class in node_mappings.items():
        if node_class in excluded_classes:
            installed_classes[node_class] = False
            continue
        if node_class not in installed_classes:
            installed_classes[node_class] = _install_on_class(node_class)
        if installed_classes[node_class]:
            installed_keys.append(mapping_key)
    return tuple(installed_keys)


__all__ = [
    "EXECUTION_SEED_MAX",
    "EXECUTION_SEED_NAME",
    "EXECUTION_SEED_SPEC",
    "install_execution_seed_controls",
]
