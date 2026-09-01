"""Load the real plugin mappings without starting the optional AI helper."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import pathlib
import sys
import types


PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMFY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(COMFY_ROOT))

import comfy_api.latest  # noqa: E402,F401


def load_module(package_name, short_name):
    module_name = f"{package_name}.{short_name}"
    spec = importlib.util.spec_from_file_location(
        module_name, PLUGIN_ROOT / f"{short_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def default_validation_kwargs(node_class):
    values = {}
    input_types = node_class.INPUT_TYPES()
    for section in ("required", "optional"):
        for name, definition in input_types.get(section, {}).items():
            input_type = definition[0]
            options = definition[1] if len(definition) > 1 else {}
            if "default" in options:
                values[name] = options["default"]
            elif isinstance(input_type, list) and input_type:
                values[name] = input_type[0]
    return values


def call_validator(node_class, values):
    validator = node_class.VALIDATE_INPUTS
    argspec = inspect.getfullargspec(validator)
    if argspec.varkw is not None:
        return validator(**values)
    accepted = set(argspec.args).union(argspec.kwonlyargs)
    return validator(**{key: value for key, value in values.items() if key in accepted})


def main():
    package_name = "zhenzhen_concurrent_probe_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[package_name] = package

    comfly = load_module(package_name, "Comfly")
    original_mappings = dict(comfly.NODE_CLASS_MAPPINGS)
    explicit_cache_seed_inputs = {
        "Comfly_seedream_v5_pro_layer_decomposition_lowprice": [
            "api_config",
            "skip_error",
            "seed",
            "model",
        ],
        "Comfly_fashvsr_video_upscale_lowprice": [
            "input_video",
            "api_config",
            "skip_error",
            "seed",
        ],
    }
    assert len(comfly.EXECUTION_SEED_NODE_KEYS) == 62
    assert set(explicit_cache_seed_inputs).issubset(
        comfly.EXECUTION_SEED_NODE_KEYS
    )
    for key in comfly.EXECUTION_SEED_NODE_KEYS:
        node_class = original_mappings[key]
        new_inputs = node_class.INPUT_TYPES()
        if key in explicit_cache_seed_inputs:
            assert list(new_inputs.get("optional", {})) == (
                explicit_cache_seed_inputs[key]
            )
            assert (
                new_inputs["optional"]["seed"][1]["control_after_generate"]
                is True
            )
            assert getattr(
                getattr(node_class, node_class.FUNCTION),
                "__wrapped__",
                None,
            ) is not None
            continue
        old_inputs = node_class.INPUT_TYPES.__wrapped__()
        assert new_inputs.get("required", {}) == old_inputs.get("required", {}), key
        assert new_inputs.get("hidden", {}) == old_inputs.get("hidden", {}), key
        assert list(new_inputs.get("optional", {})) == (
            list(old_inputs.get("optional", {})) + ["seed"]
        ), key
        for input_name, definition in old_inputs.get("optional", {}).items():
            assert new_inputs["optional"][input_name] == definition, (
                key,
                input_name,
            )
        assert new_inputs["optional"]["seed"][1]["control_after_generate"] is True
        assert "seed" not in old_inputs.get("optional", {}), key
        if hasattr(node_class, "VALIDATE_INPUTS"):
            values_with_seed = default_validation_kwargs(node_class)
            values_without_seed = dict(values_with_seed)
            values_without_seed.pop("seed", None)
            assert call_validator(node_class, values_with_seed) == call_validator(
                node_class, values_without_seed
            ), key

    assert "Comfly_qwen_image_3_0_lowprice" not in comfly.EXECUTION_SEED_NODE_KEYS
    assert (
        original_mappings["Comfly_qwen_image_3_0_lowprice"]
        .INPUT_TYPES()["required"]["seed"][1]["default"]
        == -1
    )
    for settings_key in (
        "T8Zhenzhen_API_Settings",
        "Zhenzhen_api_set",
        "Comfly_api_set",
        "Comfly_seedance2_low_price_settings",
    ):
        settings_inputs = original_mappings[settings_key].INPUT_TYPES()
        assert all(
            "seed" not in settings_inputs.get(section, {})
            for section in ("required", "optional", "hidden")
        ), settings_key
    for utility_key in (
        "Comfly_zhenzhen_upscaler_lowprice",
        "Comfly_topaz_upscale_fal",
        "Comfly_bria_video_background_removal_v3_fal",
        "Comfly_pixelcut_video_background_removal_fal",
    ):
        utility_inputs = original_mappings[utility_key].INPUT_TYPES()
        assert all(
            "seed" not in utility_inputs.get(section, {})
            for section in ("required", "optional", "hidden")
        ), utility_key

    concurrent_module = load_module(package_name, "ComflyConcurrent")
    concurrent_mappings = concurrent_module.CONCURRENT_NODE_CLASS_MAPPINGS

    for key in (
        "Comfly_zhenzhen_video_g_omni_flash_lowprice_v2",
        "Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice",
        "Comfly_hunyuan3d_v3_1_lowprice",
        "Comfly_zhenzhen_image_gk_v2_region_edit_lowprice",
    ):
        assert key in original_mappings
        seed_input = original_mappings[key].INPUT_TYPES()["optional"]["seed"]
        assert seed_input[1]["control_after_generate"] is True
    assert "Comfly_zhenzhen_image_gk_v2_segment_lowprice" in original_mappings
    assert (
        "Comfly_zhenzhen_image_gk_v2_segment_lowprice"
        not in comfly.EXECUTION_SEED_NODE_KEYS
    )
    for key in (
        "Comfly_zhenzhen_video_g_omni_flash_lowprice_v2",
        "Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice",
        "Comfly_zhenzhen_image_gk_v2_region_edit_lowprice",
    ):
        assert key in concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS

    for key in (
        "Comfly_zhenzhen_image_gk_v2_lowprice",
        "Comfly_wan_2_7_global_image_lowprice",
        "Comfly_qwen3_tts_lowprice",
        "Comfly_minimax_audio_lowprice",
        "Comfly_mureka_bgm_lowprice",
    ):
        assert key in original_mappings
        assert key in comfly.EXECUTION_SEED_NODE_KEYS
    for key in (
        "Comfly_zhenzhen_image_gk_v2_lowprice",
        "Comfly_wan_2_7_global_image_lowprice",
    ):
        assert key in concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS
    for key in (
        "Comfly_qwen3_tts_lowprice",
        "Comfly_minimax_audio_lowprice",
        "Comfly_mureka_bgm_lowprice",
    ):
        assert key not in concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS

    assert "Comfly_minimax_h3_ow_fast_video_lowprice" in original_mappings
    assert (
        "Comfly_minimax_h3_ow_fast_video_lowprice"
        in concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS
    )
    wan30_key = "Comfly_wan_3_0_video_lowprice"
    assert wan30_key in original_mappings
    assert wan30_key in concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS
    wan30_wrapper = concurrent_mappings[
        f"ComflyConcurrent_{wan30_key}_Submit"
    ]
    assert wan30_wrapper.RETURN_TYPES == (
        concurrent_module.VIDEO_TASK_TYPE,
    )
    assert wan30_wrapper.ORIGINAL_NODE_CLASS is original_mappings[wan30_key]
    fashvsr_key = "Comfly_fashvsr_video_upscale_lowprice"
    assert fashvsr_key in original_mappings
    assert fashvsr_key in concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS
    fashvsr_wrapper = concurrent_mappings[
        f"ComflyConcurrent_{fashvsr_key}_Submit"
    ]
    assert fashvsr_wrapper.RETURN_TYPES == (
        concurrent_module.VIDEO_TASK_TYPE,
    )
    assert fashvsr_wrapper.ORIGINAL_NODE_CLASS is original_mappings[fashvsr_key]
    nano_banana_key = "Comfly_nano_banana2_edit"
    assert (
        original_mappings[nano_banana_key]
        is comfly.Comfly_nano_banana2_edit_async_compatible
    )
    assert nano_banana_key in concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS
    nano_banana_wrapper = concurrent_mappings[
        f"ComflyConcurrent_{nano_banana_key}_Submit"
    ]
    assert nano_banana_wrapper.ORIGINAL_NODE_CLASS is original_mappings[nano_banana_key]
    for preserved_key in (
        "Comfly_seedance25_standard_low_price",
        "Comfly_flowmusic_lowprice",
        "Comfly_zhenzhen_image_gk_v2_edit_lowprice",
    ):
        assert preserved_key in original_mappings
    assert len(concurrent_mappings) == (
        len(concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS) + 2
    )
    assert not set(original_mappings).intersection(concurrent_mappings)
    assert concurrent_module.IMAGE_MAX_WORKERS == 30
    assert concurrent_module.VIDEO_MAX_WORKERS == 10

    validator_count = 0
    for key, node_class in original_mappings.items():
        submit_key = f"ComflyConcurrent_{key}_Submit"
        if submit_key not in concurrent_mappings:
            continue
        wrapper = concurrent_mappings[submit_key]
        assert wrapper.INPUT_TYPES() == node_class.INPUT_TYPES(), key
        assert not hasattr(wrapper, "IS_CHANGED"), key
        if hasattr(node_class, "VALIDATE_INPUTS"):
            validator_count += 1
            values = default_validation_kwargs(node_class)
            assert call_validator(wrapper, values) == call_validator(
                node_class, values
            ), key

    merged = dict(original_mappings)
    merged.update(concurrent_mappings)
    assert len(merged) == len(original_mappings) + len(concurrent_mappings)
    for key, node_class in original_mappings.items():
        assert merged[key] is node_class
        function = getattr(node_class, getattr(node_class, "FUNCTION", ""), None)
        if getattr(function, "_comfly_workflow_key_reset", False):
            assert inspect.iscoroutinefunction(function) == inspect.iscoroutinefunction(
                function.__wrapped__
            ), key

    class ReusedNodeProbe:
        FUNCTION = "run"

        def __init__(self):
            self.api_key = "stale-key"

        def run(self, api_key=""):
            return self.api_key

    assert comfly._install_workflow_api_key_reset({"probe": ReusedNodeProbe}) == 1
    reused = ReusedNodeProbe()
    assert reused.run(api_key="new-workflow-key") == "new-workflow-key"
    assert reused.run(api_key="") == ""

    class AsyncReusedNodeProbe:
        FUNCTION = "run"

        def __init__(self):
            self.api_key = "stale-key"

        async def run(self, apikey=""):
            return self.api_key

    assert comfly._install_workflow_api_key_reset(
        {"async_probe": AsyncReusedNodeProbe}
    ) == 1
    assert inspect.iscoroutinefunction(AsyncReusedNodeProbe.run)
    async_reused = AsyncReusedNodeProbe()
    assert asyncio.run(async_reused.run(apikey="")) == ""

    settings = comfly.T8Zhenzhen_API_Settings()
    _key, config = settings.set_api_base("zhenzhen", apikey="")
    assert config["api_key"] == ""

    for legacy_class in (comfly.Zhenzhen_api_set, comfly.Comfly_api_set):
        legacy_settings = legacy_class()
        legacy_key, legacy_config = legacy_settings.set_api_base(
            "seedance_low_price",
            apikey="",
        )
        assert legacy_key == ""
        assert legacy_config["base_url"] == "https://api.seedance.nz"

    print(
        f"plugin_probe=ok original={len(original_mappings)} "
        f"submit={len(concurrent_module.CONCURRENT_WRAPPED_NODE_KEYS)} "
        f"total={len(merged)} "
        f"validators={validator_count} "
        f"workflow_key_nodes={comfly.WORKFLOW_API_KEY_RESET_NODE_COUNT}"
    )
    concurrent_module._shutdown_executors()


if __name__ == "__main__":
    main()
