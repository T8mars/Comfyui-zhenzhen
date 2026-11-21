import json
from pathlib import Path
import unittest
from unittest.mock import patch

import torch

from nov08_fixture import ROOT, module

api = module("seedance_low_price_nodes")
h3 = module("h3_comfy_low_price_nodes")
tts = module("doubao_tts_low_price_nodes")
flash = module("seedance25_flash_contracts")
image = torch.zeros(1, 8, 8, 3)
audio = {"waveform": torch.zeros(1, 1, 48000), "sample_rate": 24000}


class Nov17Contracts(unittest.TestCase):
    def test_catalog_and_legacy_prefix(self):
        self.assertEqual(len(api.SEEDANCE25_MODELS), 12)
        self.assertEqual(set(api.SEEDANCE25_MODELS[6:]), set(flash.MODELS))
        fields = list(api.Comfly_seedance25_standard_low_price.INPUT_TYPES()["optional"])
        self.assertEqual(fields[-6:], ["generate_audio", "return_last_frame", "seed", "skip_error", "draft", "omni_reference_task_type"])

    def test_flash_per_model_rejections_before_upload(self):
        node = api.Comfly_seedance25_standard_low_price()
        defaults = {"model": "seedance-2.5-flash-multi", "resolution": "480p", "ratio": "adaptive", "prompt": "animate", "seconds": "4", "image1": image}
        for values in ({"image11": image}, {"video6": object()}, {"audio6": audio}, {"resolution": "native1080p"}, {"draft": True}, {"audio1": {"waveform": torch.zeros(1, 1, 24000), "sample_rate": 24000}}, {"image1": image.expand(2, -1, -1, -1)}):
            with self.subTest(values=list(values)), patch.object(node, "_upload") as upload, self.assertRaises(api.SeedanceLowPriceError):
                node.collect_media({**defaults, **values}, {})
            upload.assert_not_called()
        for model in flash.MODELS:
            with self.subTest(model=model):
                self.assertTrue(flash.validate({"model": model, "ratio": "adaptive", "resolution": "720p"}))
                self.assertIsNot(api.Comfly_seedance25_standard_low_price.VALIDATE_INPUTS(model=model, prompt="animate", resolution="4k"), True)

    def test_flash_payload_and_auto_duration(self):
        for model in flash.MODELS:
            media = {"images": ["https://example.test/a.png"], "content": [{"type": "image_url", "image_url": {"url": "https://example.test/a.png"}}]}
            body = api.Comfly_seedance25_standard_low_price.build_payload({"model": model, "prompt": "animate", "seconds": "-1", "resolution": "720p", "ratio": "adaptive", "seed": 0, "omni_reference_task_type": "reference"}, media)
            self.assertNotIn("seconds", body)
            self.assertEqual(body["metadata"]["duration"], -1)
            self.assertNotIn("draft", body["metadata"])
            self.assertEqual(body["metadata"]["seed"], 0)
            if model.endswith("-multi"):
                self.assertEqual(body["metadata"]["omni_reference_task_type"], "reference")
                self.assertEqual(body["metadata"]["content"], media["content"])

    def test_flash_video_edit_validation(self):
        values = {"model": flash.MODELS[2], "image1": image, "video1": object(), "ratio": "adaptive", "omni_reference_task_type": "edit", "seconds": "-1"}
        self.assertTrue(flash.validate(values, strict=True))
        for extra in ({"seconds": "4"}, {"video1": None}, {"ratio": "16:9"}):
            with self.assertRaises(api.SeedanceLowPriceError):
                flash.validate({**values, **extra}, strict=True)

    def test_h3_distinct_limits_frames_and_seed(self):
        c = h3.contracts
        self.assertEqual([c.PROFILES[k]["images"] for k in ("charswap", "wuxi", "wf", "selflift")], [9, 9, 6, 9])
        self.assertEqual([c.PROFILES[k]["videos"] for k in ("charswap", "wuxi", "wf", "selflift")], [1, 3, 0, 0])
        values = {"prompt": "Replace <Picture 1>", "image1": image, "video_urls": "https://example.test/source.mp4", "duration_mode": "frames", "frames": 124, "seed": 0}
        body = c.payload("charswap", values, ["https://example.test/reference.png"], [], ["https://example.test/source.mp4"])
        self.assertNotIn("seconds", body)
        self.assertEqual(body["metadata"]["frames"], 124)
        self.assertEqual(body["metadata"]["seed"], 0)
        for values in ({"prompt": "animate"}, {"prompt": "animate", "image1": image, "audio1": audio}, {"prompt": "animate", "image1": image, "video_urls": "https://example.test/a.mp4\nhttps://example.test/b.mp4"}):
            with self.assertRaises(api.SeedanceLowPriceError):
                c.validate("charswap", values, True)
        for frame in (21, 23, 363, True):
            with self.assertRaises(api.SeedanceLowPriceError):
                c.validate("charswap", {**values, "duration_mode": "frames", "frames": frame}, True)

    def test_h3_cross_media_and_reference_tags(self):
        c = h3.contracts
        for kind, values in (("wuxi", {"video1": object()}), ("selflift", {"audio1": audio}), ("wf", {"image7": image}), ("charswap", {"audio1": audio}), ("wf", {"video1": object()}), ("wf", {"prompt": "<Picture 2>", "image1": image}), ("wuxi", {"prompt": "<Audio 1>", "audio1": audio})):
            with self.subTest(kind=kind), self.assertRaises(api.SeedanceLowPriceError):
                c.validate(kind, {"prompt": "animate", **values}, True)
        for kind in ("wf", "selflift"):
            body = c.payload(kind, {"prompt": "<Picture 1> follows <Audio 1>", "image1": image, "audio1": audio, "seed": 123}, ["image"], ["audio"], [])
            self.assertNotIn("seed", body["metadata"])

    def test_h3_resolution_specific_ratios(self):
        c = h3.contracts
        self.assertEqual(c.ratios("charswap", "auto"), ["auto"])
        self.assertIn("21:9", c.ratios("charswap", "768p"))
        self.assertNotIn("21:9", c.ratios("charswap", "1088p"))
        self.assertEqual(c.ratios("wf", "480p"), ["16:9", "9:16"])

    def test_converted_placeholder_validation(self):
        for cls in [*h3.CLASSES.values(), tts.T8ZhenzhenDoubaoSeedTTS20]:
            self.assertIs(cls.VALIDATE_INPUTS(prompt=None, resolution=None, ratio=None, seed=None, speaker=None), True)
            self.assertIsNot(cls.VALIDATE_INPUTS(prompt="", strict=True), True)
        self.assertIsNot(h3.T8ZhenzhenH3WF.VALIDATE_INPUTS(prompt="animate", resolution=None, strict=True), True)

    def test_tts_catalog_and_payload(self):
        c = tts.contracts
        self.assertEqual(len(c.VOICES), 473)
        self.assertTrue(all("uranus" in value for value in c.VOICES))
        body = c.payload({"prompt": "你好", "speaker": c.VIVI, "context_texts": "温柔地说", "explicit_dialect": "sichuan", "disable_markdown_filter": "enabled", "disable_emoji_filter": "disabled", "seed": 123})
        self.assertEqual(body["metadata"]["context_texts"], "温柔地说")
        self.assertIs(body["metadata"]["disable_markdown_filter"], True)
        self.assertIs(body["metadata"]["disable_emoji_filter"], False)
        self.assertNotIn("seed", body["metadata"])
        body = c.payload({"prompt": "你好", "speaker": "trained_voice", "voice_model": "seed-tts-2.0-standard", "context_texts": "not forwarded"})
        self.assertNotIn("context_texts", body["metadata"])

    def test_tts_invalid_combinations(self):
        for values in ({"speaker": ""}, {"prompt": None}, {"prompt": "a" * 10001}, {"context_texts": "a" * 501}, {"voice_model": "seed-tts-2.0-standard"}, {"ssml": "<speak>hi</speak>"}, {"speaker": "en_male_tim_uranus_bigtts", "explicit_dialect": "sichuan"}, {"latex_parser": "v2"}, {"bit_rate": 16000}, {"speech_rate": float("nan")}):
            with self.subTest(values=list(values)), self.assertRaises(api.SeedanceLowPriceError):
                tts.contracts.validate({"prompt": "hello", **values}, True)

    def test_registration_concurrency_and_no_duplicate_api_button(self):
        plugin, parallel = module("Comfly"), module("ComflyConcurrent")
        buttons = (ROOT / "web/js/zhenzhen_image_g2_api_key_link.js").read_text(encoding="utf-8")
        for kind, key in h3.KEYS.items():
            self.assertIs(plugin.NODE_CLASS_MAPPINGS[key], h3.CLASSES[kind])
            wrapped = parallel.CONCURRENT_NODE_CLASS_MAPPINGS["ComflyConcurrent_" + key + "_Submit"]
            self.assertFalse(hasattr(wrapped, "VALIDATE_INPUTS"))
            self.assertEqual(buttons.count('"' + key + '"'), 1)
        self.assertIs(plugin.NODE_CLASS_MAPPINGS[tts.KEY], tts.T8ZhenzhenDoubaoSeedTTS20)
        self.assertEqual(buttons.count('"' + tts.KEY + '"'), 1)

    def test_26_examples_have_blank_keys_and_registered_sinks(self):
        from generate_nov08_workflows import MAPPINGS
        prefixes = ("seedance-2.5-flash-", "seedance-2.5-global-flash-", "minimax-h3-comfyui-charswap-",
                    "minimax-h3-comfyui-wuxi-", "minimax-h3-comfyui-max-10020-", "minimax-h3-comfyui-max-10021-",
                    "doubao-seed-tts-2.0-")
        paths = [path for path in (ROOT / "workflow").glob("*.json")
                 if path.name.startswith("zhenzhen-") and path.name.removeprefix("zhenzhen-").startswith(prefixes)
                 and "-token-" not in path.name]
        self.assertEqual(len(paths), 26)
        models = set()
        for path in paths:
            graph = json.loads(path.read_text(encoding="utf-8"))
            settings = next(node for node in graph["nodes"] if node["type"] == "T8Zhenzhen_API_Settings")
            self.assertEqual(settings["widgets_values"], ["seedance_low_price", "", "", False])
            for node in graph["nodes"]:
                if node["type"].startswith(("T8Zhenzhen", "Comfly")):
                    self.assertIn(node["type"], MAPPINGS)
                if node["type"] == "Comfly_seedance25_standard_low_price":
                    models.add(node["widgets_values"][0])
        self.assertEqual(models, set(flash.MODELS))


if __name__ == "__main__":
    unittest.main()
