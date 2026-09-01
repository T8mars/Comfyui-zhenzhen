import asyncio
import copy
import sys
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = PLUGIN_ROOT.parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from execution_seed import (
    EXECUTION_SEED_MAX,
    EXECUTION_SEED_SPEC,
    install_execution_seed_controls,
)


class ExecutionSeedInstallerTests(unittest.TestCase):
    def test_missing_seed_is_appended_and_consumed_without_changing_payload(self):
        class ImageGenerator:
            RETURN_TYPES = ("IMAGE", "STRING")
            FUNCTION = "generate"

            @classmethod
            def INPUT_TYPES(cls):
                return {
                    "required": {"prompt": ("STRING", {"default": ""})},
                    "optional": {
                        "skip_error": ("BOOLEAN", {"default": False})
                    },
                }

            def generate(self, prompt, skip_error=False):
                return (prompt, skip_error)

        original_schema = copy.deepcopy(ImageGenerator.INPUT_TYPES())
        installed = install_execution_seed_controls({"image": ImageGenerator})

        self.assertEqual(installed, ("image",))
        inputs = ImageGenerator.INPUT_TYPES()
        self.assertEqual(inputs["required"], original_schema["required"])
        self.assertEqual(
            list(inputs["optional"]), ["skip_error", "seed"]
        )
        self.assertEqual(inputs["optional"]["seed"], EXECUTION_SEED_SPEC)
        self.assertTrue(
            inputs["optional"]["seed"][1]["control_after_generate"]
        )
        self.assertEqual(
            inputs["optional"]["seed"][1]["max"], EXECUTION_SEED_MAX
        )
        self.assertEqual(
            ImageGenerator().generate(
                prompt="same payload", skip_error=True, seed=123
            ),
            ("same payload", True),
        )

    def test_native_seed_and_non_generation_nodes_are_unchanged(self):
        class NativeSeedGenerator:
            RETURN_TYPES = ("IMAGE",)
            FUNCTION = "generate"

            @classmethod
            def INPUT_TYPES(cls):
                return {
                    "required": {
                        "seed": (
                            "INT",
                            {"default": -1, "min": -1, "max": 99},
                        )
                    }
                }

            def generate(self, seed):
                return (seed,)

        class ApiSettings:
            RETURN_TYPES = ("API_CONFIG",)
            FUNCTION = "configure"

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"api_key": ("STRING", {})}}

            def configure(self, api_key):
                return (api_key,)

        native_inputs = copy.deepcopy(NativeSeedGenerator.INPUT_TYPES())
        native_function = NativeSeedGenerator.generate
        settings_inputs = copy.deepcopy(ApiSettings.INPUT_TYPES())

        installed = install_execution_seed_controls(
            {"native": NativeSeedGenerator, "settings": ApiSettings}
        )

        self.assertEqual(installed, ())
        self.assertEqual(NativeSeedGenerator.INPUT_TYPES(), native_inputs)
        self.assertIs(NativeSeedGenerator.generate, native_function)
        self.assertEqual(ApiSettings.INPUT_TYPES(), settings_inputs)

    def test_explicit_cache_only_seed_is_consumed(self):
        class LayerGenerator:
            RETURN_TYPES = ("IMAGE",)
            FUNCTION = "generate"
            SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True

            @classmethod
            def INPUT_TYPES(cls):
                return {
                    "required": {"prompt": ("STRING", {})},
                    "optional": {"seed": EXECUTION_SEED_SPEC},
                }

            def generate(self, prompt):
                return (prompt,)

        installed = install_execution_seed_controls({"layer": LayerGenerator})

        self.assertEqual(installed, ("layer",))
        self.assertEqual(
            LayerGenerator().generate(prompt="same payload", seed=123),
            ("same payload",),
        )

    def test_known_media_processing_utility_does_not_receive_seed(self):
        class TopazUpscaler:
            RETURN_TYPES = ("IMAGE", "VIDEO")
            FUNCTION = "upscale"

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"image": ("IMAGE",)}}

            def upscale(self, image):
                return (image, None)

        original = copy.deepcopy(TopazUpscaler.INPUT_TYPES())
        installed = install_execution_seed_controls(
            {"Comfly_topaz_upscale_fal": TopazUpscaler}
        )

        self.assertEqual(installed, ())
        self.assertEqual(TopazUpscaler.INPUT_TYPES(), original)

    def test_aliases_and_repeated_installation_are_idempotent(self):
        class VideoGenerator:
            RETURN_TYPES = ("VIDEO",)
            FUNCTION = "generate"

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"prompt": ("STRING", {})}}

            def generate(self, prompt):
                return (prompt,)

        mappings = {"video": VideoGenerator, "video_alias": VideoGenerator}
        first = install_execution_seed_controls(mappings)
        wrapped_function = VideoGenerator.generate
        second = install_execution_seed_controls(mappings)

        self.assertEqual(first, ("video", "video_alias"))
        self.assertEqual(second, first)
        self.assertIs(VideoGenerator.generate, wrapped_function)
        self.assertEqual(list(VideoGenerator.INPUT_TYPES()["optional"]), ["seed"])

    def test_async_generation_remains_async(self):
        class AudioGenerator:
            RETURN_TYPES = ("AUDIO",)
            FUNCTION = "generate"

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {"text": ("STRING", {})}}

            async def generate(self, text):
                return (text,)

        install_execution_seed_controls({"audio": AudioGenerator})
        self.assertTrue(asyncio.iscoroutinefunction(AudioGenerator.generate))
        self.assertEqual(
            asyncio.run(AudioGenerator().generate(text="hello", seed=77)),
            ("hello",),
        )


class ComfyCacheSignatureTests(unittest.TestCase):
    def test_fixed_seed_reuses_signature_and_changed_seed_invalidates_it(self):
        sys.path.insert(0, str(COMFY_ROOT))
        import nodes
        from comfy_execution.caching import BasicCache, CacheKeySetInputSignature
        from comfy_execution.graph import DynamicPrompt

        class CacheProbeNode:
            RETURN_TYPES = ("IMAGE",)

            @classmethod
            def INPUT_TYPES(cls):
                return {
                    "required": {
                        "prompt": ("STRING", {}),
                        "seed": EXECUTION_SEED_SPEC,
                    }
                }

        class IsChangedCache:
            async def get(self, node_id):
                return False

        async def signature(seed):
            prompt = {
                "1": {
                    "class_type": "ComflyExecutionSeedCacheProbe",
                    "inputs": {"prompt": "same prompt", "seed": seed},
                }
            }
            key_set = CacheKeySetInputSignature(
                DynamicPrompt(prompt), ["1"], IsChangedCache()
            )
            await key_set.add_keys(["1"])
            return key_set.get_data_key("1")

        async def cached_result_after(seed_first, seed_second):
            cache = BasicCache(CacheKeySetInputSignature)

            def prompt(seed):
                return DynamicPrompt(
                    {
                        "1": {
                            "class_type": "ComflyExecutionSeedCacheProbe",
                            "inputs": {"prompt": "same prompt", "seed": seed},
                        }
                    }
                )

            changed = IsChangedCache()
            await cache.set_prompt(prompt(seed_first), ["1"], changed)
            cache.set_local("1", "completed API result")
            await cache.set_prompt(prompt(seed_second), ["1"], changed)
            return cache.get_local("1")

        key = "ComflyExecutionSeedCacheProbe"
        previous = nodes.NODE_CLASS_MAPPINGS.get(key)
        nodes.NODE_CLASS_MAPPINGS[key] = CacheProbeNode
        try:
            fixed_first = asyncio.run(signature(1234))
            fixed_second = asyncio.run(signature(1234))
            randomized = asyncio.run(signature(5678))
            fixed_result = asyncio.run(cached_result_after(1234, 1234))
            randomized_result = asyncio.run(cached_result_after(1234, 5678))
        finally:
            if previous is None:
                nodes.NODE_CLASS_MAPPINGS.pop(key, None)
            else:
                nodes.NODE_CLASS_MAPPINGS[key] = previous

        self.assertEqual(fixed_first, fixed_second)
        self.assertNotEqual(fixed_first, randomized)
        self.assertEqual(fixed_result, "completed API result")
        self.assertIsNone(randomized_result)


if __name__ == "__main__":
    unittest.main()
