import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import torch

from nov08_fixture import ROOT, module

nodes = module("nov19_low_price_nodes")
images, speech, api = nodes.images, nodes.speech, nodes.api
llm = module("llm_low_price_presets")
IMAGE = torch.zeros(1, 384, 384, 3)
AUDIO = {"waveform": torch.zeros(1, 1, 48000), "sample_rate": 24000}
CONFIG = {"base_url": api.DEFAULT_BASE_URL, "api_key": "test-key"}
URL = "https://example.test/result.png"


class Nov19Contracts(unittest.TestCase):
    def test_exact_models_and_voice_catalog(self):
        self.assertEqual(images.KLING_MODEL, "kling-v4-image")
        self.assertEqual(images.MAI_MODELS, ["mai-image-2-7", "mai-image-2-7-flash"])
        self.assertEqual([len(speech.VOICES[key]) for key in (speech.FLASH, speech.PLUS)], [69, 4])
        self.assertEqual(len(set(speech.VOICES[speech.FLASH])), 69)
        self.assertEqual(llm.PRESETS[:3], ["custom", "zhenzhen/g6.2-astra", "zhenzhen/g6.2-sol"])

    def test_kling_image_limits(self):
        images.payload("kling", {"prompt": "a" * 50000})
        images.payload("kling", {"prompt": "中" * 21000})
        for values in ({"prompt": "a" * 50001}, {"prompt": "中" * 21001}, {"n": 10}, {"resolution": "1k"}, {"size": "1024x1024"}, {"nsfw_check": 1}, {"image11": IMAGE}, {"prompt": "@Image2", "image1": IMAGE}):
            with self.subTest(fields=list(values)), self.assertRaises(api.SeedanceLowPriceError):
                images.payload("kling", {"prompt": "draw", **values})
        for image in (torch.zeros(1, 299, 384, 3), torch.zeros(1, 300, 751, 3), IMAGE.expand(2, -1, -1, -1)):
            with self.assertRaises(api.SeedanceLowPriceError):
                images.encode_references("kling", {"image1": image})

    def test_group_payload_does_not_forward_independent_n(self):
        body = images.payload("kling", {"prompt": "related views", "sequential_image_generation": "auto", "max_images": 4, "n": 9, "seed": 123})
        self.assertNotIn("n", body)
        self.assertNotIn("seed", body)
        self.assertEqual(body["sequential_image_generation_options"], {"max_images": 4})

    def test_mai_text_and_edit_contracts(self):
        body = images.payload("mai", {"prompt": "draw", "size": "custom_pixels", "width": 2050, "height": 1025})
        self.assertEqual((body["width"], body["height"]), (2048, 1024))
        for extra in ({"size": "auto"}, {"resolution": "4k"}, {"background": "transparent"}, {"size": "custom_pixels", "width": 2049, "height": 2048}, {"image6": IMAGE}, {"prompt": "x" * 20001}):
            with self.subTest(fields=list(extra)), self.assertRaises(api.SeedanceLowPriceError):
                images.payload("mai", {"prompt": "draw", **extra})
        body = images.payload("mai", {"prompt": "edit", "image1": IMAGE, "size": "auto", "resolution": "4k", "web_grounding": True}, [URL])
        self.assertEqual(set(body), {"model", "prompt", "images", "n", "nsfw_check", "background"})

    def test_complete_kling_list_is_returned(self):
        final = {"urls": [URL, URL + "?two"]}
        with patch.object(api, "submit_image_task", return_value=("test-task", {})), patch.object(api, "poll_image_task", return_value=final), patch.object(api, "extract_image_urls", return_value=final["urls"]), patch.object(api, "download_image", return_value=IMAGE) as download:
            response = nodes.T8ZhenzhenKlingV4Image().execute(api_config=CONFIG, prompt="three views", n=3)
        result = response["result"]
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(result[1], final["urls"])
        self.assertIn("2 images instead of 3", response["ui"]["text"][0])
        self.assertEqual(download.call_count, 2)
        self.assertEqual(nodes.T8ZhenzhenKlingV4Image.OUTPUT_IS_LIST, (True, True, False, False))

    def test_qwen_profile_specific_metadata(self):
        for model in speech.MODELS:
            body = speech.payload({"model": model, "prompt": "hello", "seed": 0})
            self.assertEqual(body["seed"], 0)
            if model == speech.NEXT:
                self.assertNotIn("voice", body["metadata"])
                self.assertNotIn("pitch", body["metadata"])
                self.assertEqual(body["metadata"]["sample_rate"], "48000")
            else:
                self.assertIn(body["metadata"]["voice"], speech.VOICES[model])
                self.assertEqual(body["metadata"]["sample_rate"], "22050")

    def test_qwen_invalid_combinations(self):
        for values in ({"audio1": AUDIO}, {"seed": 65536}, {"voice": "custom_voice"}, {"output_format": "opus", "sample_rate": "22050"}, {"enable_ssml": True}, {"rate": float("nan")}):
            with self.subTest(fields=list(values)), self.assertRaises(api.SeedanceLowPriceError):
                speech.payload({"prompt": "hello", **values})
        for values in ({"prompt": "x" * 3001}, {"prompt": "@voice1"}, {"audio4": AUDIO}, {"output_format": "opus"}, {"sample_rate": "22050"}, {"channels": "3"}):
            with self.subTest(fields=list(values)), self.assertRaises(api.SeedanceLowPriceError):
                speech.payload({"model": speech.NEXT, "prompt": "chime", **values})
        body = speech.payload({"model": speech.NEXT, "prompt": "@voice2", "audio1": AUDIO, "audio_urls": "https://example.test/b.wav"}, ["https://example.test/a.wav"])
        self.assertEqual(body["metadata"]["audio_urls"], ["https://example.test/a.wav", "https://example.test/b.wav"])

    def test_pcm_stereo_layout(self):
        data = np.array([1000, -1000, 2000, -2000], dtype="<i2").tobytes()
        result = api.audio_bytes_to_comfy(data, "pcm", 24000, pcm_channels=2)
        self.assertEqual(tuple(result["waveform"].shape), (1, 2, 2))
        self.assertAlmostEqual(float(result["waveform"][0, 1, 0]), -1000 / 32768)
        with self.assertRaises(api.SeedanceLowPriceError):
            api.audio_bytes_to_comfy(b"123", "pcm", 24000, pcm_channels=2)

    def test_new_media_submissions_do_not_replay_ambiguous_server_errors(self):
        for submit in (api.submit_image_task, api.submit_audio_task):
            session = Mock()
            session.post.return_value = Mock(status_code=502, text="Bad gateway")
            session.post.return_value.json.return_value = {"message": "Bad gateway"}
            with patch.object(api, "_get_session", return_value=session):
                with self.assertRaisesRegex(api.SeedanceLowPriceError, "check the provider task list"):
                    submit({"model": "test-model"}, CONFIG, sleep=lambda _: None, retry_server_errors=False)
            session.post.assert_called_once()

    def test_linked_widget_placeholders_and_strict_checks(self):
        for cls in nodes.CLASSES.values():
            self.assertIs(cls.VALIDATE_INPUTS(prompt=None, model=None, resolution=None, seed=None), True)
            self.assertIsNot(cls.VALIDATE_INPUTS(prompt="", strict=True), True)

    def test_llm_legacy_prefix_and_opt_in_route(self):
        plugin = module("Comfly")
        schema = plugin.Comfly_LLm_API.INPUT_TYPES()
        self.assertEqual(list(schema["required"]), ["api_baseurl", "api_key", "model", "role", "prompt", "temperature", "seed"])
        self.assertEqual(list(schema["optional"])[:3], ["ref_image", "video", "skip_error"])
        self.assertEqual(schema["optional"]["model_preset"][1]["default"], "custom")
        with patch.object(llm, "call_g62", return_value="OK") as call:
            result = plugin.Comfly_LLm_API().Zhenzhen_run_llmapi("legacy", "", "legacy", "system", "hello", .6, 100, model_preset=llm.MODELS[0], api_config=CONFIG)
        self.assertEqual(result, ("OK",))
        self.assertEqual(call.call_args.args[0], llm.MODELS[0])

    def test_llm_sdk_request_has_no_forced_temperature_or_seed(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])
        with patch("openai.OpenAI", return_value=client) as factory:
            self.assertEqual(llm.call_g62(llm.MODELS[0], "hello", "system", api_key="test-key"), "OK")
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertNotIn("temperature", kwargs)
        self.assertNotIn("seed", kwargs)
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        client.close.assert_called_once()

    def test_llm_rejects_blank_key_wrong_channel_and_video(self):
        for extra in ({}, {"video": object(), "api_key": "test-key"}, {"api_config": {"base_url": "https://ai.t8star.org", "api_key": "test-key"}}):
            with self.assertRaises(api.SeedanceLowPriceError):
                llm.call_g62(llm.MODELS[0], "hello", "system", **extra)

    def test_unique_registration_and_safe_concurrent_support(self):
        plugin, parallel = module("Comfly"), module("ComflyConcurrent")
        for kind, key in nodes.KEYS.items():
            self.assertIs(plugin.NODE_CLASS_MAPPINGS[key], nodes.CLASSES[kind])
        self.assertIn("ComflyConcurrent_" + nodes.KEYS["mai"] + "_Submit", parallel.CONCURRENT_NODE_CLASS_MAPPINGS)
        self.assertNotIn("ComflyConcurrent_" + nodes.KEYS["kling"] + "_Submit", parallel.CONCURRENT_NODE_CLASS_MAPPINGS)


if __name__ == "__main__":
    unittest.main()
