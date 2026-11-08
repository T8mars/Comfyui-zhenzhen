import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import torch

from nov08_fixture import api, image, nodes, kling, flash, module, ROOT


IMAGE = torch.zeros(1, 16, 16, 3)
URL = "https://example.test/result"
CONFIG = {"base_url": "https://example.test", "api_key": "test-key", "poll_interval": 0}
OMNI_KEY = "T8Zhenzhen_Video_G_Omni_12_Flash_LowPrice"
KLING_KEY = "T8Zhenzhen_Kling_V4_Omni_LowPrice"


class G26UpdateTests(unittest.TestCase):
    def test_static_tiers_quality_format_and_no_cache_seed(self):
        for resolution in ("1k", "2k", "4k"):
            for quality in image.QUALITIES:
                for output in ("png", "jpeg", "webp"):
                    result = image.g26_payload({"prompt": "Product", "resolution": resolution,
                        "quality": quality, "output_format": output, "seed": 42, "n": 4,
                        "complexity": "high", "frame_count": 12, "mask_url": URL}, [])
                    self.assertEqual(result, {"model": image.G26_MODELS[0], "prompt": "Product", "size": "1:1",
                        "n": 1, "resolution": resolution, "quality": quality, "output_format": output})

    def test_sixteen_ordered_references_and_seventeenth_rejected(self):
        values = {"prompt": "Combine", **{f"image{i}": IMAGE for i in range(16, 0, -1)}}
        self.assertIs(image.validate_g26(values, True), True)
        self.assertEqual([i for i, _ in nodes.common.references(values, 16)], list(range(1, 17)))
        urls = [f"{URL}/{i}.png" for i in range(16)]
        self.assertEqual(image.g26_payload(values, urls)["images"], urls)
        self.assertIsNot(image.validate_g26(dict(values, image17=IMAGE), True), True)
        with self.assertRaises(api.SeedanceLowPriceError):
            image.g26_payload(values, urls + [URL])

    def test_lowprice_gif_explicit_format_auto_size_and_no_frame_fields(self):
        result = image.g26_payload({"prompt": "Moving ball", "mode": "gif", "size": "1:1",
            "resolution": "2k", "frame_count": 9, "frame_duration_ms": 200}, [])
        self.assertEqual((result["size"], result["output_format"], result["resolution"]), ("auto", "gif", "2k"))
        self.assertFalse(set(result) & {"images", "frame_count", "frame_duration_ms"})
        self.assertIn("looping GIF", result["prompt"])
        for model in image.G26_MODELS:
            self.assertIsNot(image.validate_g26({"model": model, "mode": "gif", "image1": IMAGE}), True)

    def test_invalid_controls_and_unresolved_prompt(self):
        for values in ({"resolution": "8k"}, {"quality": "invalid"}, {"output_format": "svg"}, {"size": "custom"}):
            self.assertIsNot(image.validate_g26(values), True)
        self.assertIs(nodes.T8ZhenzhenImageG26.VALIDATE_INPUTS(prompt=None), True)
        self.assertIsNot(nodes.T8ZhenzhenImageG26.VALIDATE_INPUTS(strict=True, prompt=None), True)
        with patch.object(api, "upload_media") as upload, patch.object(nodes.common, "submit_request") as submit:
            with self.assertRaises(api.SeedanceLowPriceError):
                nodes.T8ZhenzhenImageG26().generate(prompt="GIF", mode="gif", image1=IMAGE)
        upload.assert_not_called()
        submit.assert_not_called()

    def test_original_schema_and_official_payloads(self):
        schema = nodes.T8ZhenzhenImageG26.INPUT_TYPES()
        self.assertEqual(list(schema["optional"]), [*[f"image{i}" for i in range(1, 17)], "api_config", "skip_error", "seed"])
        self.assertEqual(len(nodes.T8ZhenzhenImageG26.RETURN_TYPES), 8)
        for model in image.G26_MODELS[1:]:
            result = image.g26_payload({"model": model, "prompt": "Edit", "n": 4, "resolution": "4k"}, [URL] * 16)
            self.assertEqual((result["n"], result["resolution"], len(result["images"])), (4, "4k", 16))
            gif = image.g26_payload({"model": model, "prompt": "Ball", "mode": "gif", "frame_count": 2}, [])
            self.assertEqual((gif["frame_count"], gif["frame_duration_ms"]), (2, 200))


class FlashVideoTests(unittest.TestCase):
    def test_payloads_and_ignored_legacy_controls(self):
        for model in flash.PROFILES:
            values = {"prompt": "Robot waves", "seconds": 3, "seed": 42, "watermark": "enabled",
                "generation_type": "reference", "nsfw_check": True}
            expected = {"model": model, "prompt": "Robot waves", "seconds": "3", "resolution": "720p", "aspect_ratio": "16:9"}
            self.assertEqual(flash.payload(model, values, {}), expected)
            self.assertEqual(flash.payload(model, values, {"images": [URL]}), dict(expected, images=[URL]))
            self.assertEqual(flash.payload(model, values, {"videos": [URL]}), dict(expected, metadata={"video_url": [URL]}))

    def test_profiles_and_numeric_boundaries(self):
        for model, maximum in ((flash.KLING_MODEL, 20), (flash.OMNI_MODEL, 15)):
            for seconds in (3, maximum):
                flash.validate(model, {"seconds": seconds})
            for seconds in (2, maximum + 1, True, 3.5, "3"):
                with self.assertRaises(api.SeedanceLowPriceError):
                    flash.validate(model, {"seconds": seconds})
        for resolution in ("360p", "1080p", "4k"):
            flash.validate(flash.OMNI_MODEL, {"resolution": resolution})
            with self.assertRaises(api.SeedanceLowPriceError):
                flash.validate(flash.KLING_MODEL, {"resolution": resolution})
        for ratio in ("1:1", "21:9"):
            flash.validate(flash.KLING_MODEL, {"ratio": ratio})
            with self.assertRaises(api.SeedanceLowPriceError):
                flash.validate(flash.OMNI_MODEL, {"ratio": ratio})

    def test_media_counts_types_ids_and_mutual_exclusion(self):
        for model, profile in flash.PROFILES.items():
            flash.validate(model, {f"image{i}": IMAGE for i in range(1, 11)})
            flash.validate(model, {f"video{i}": object() for i in range(1, profile["videos"] + 1)})
            for invalid in ({"image11": IMAGE}, {f"video{profile['videos'] + 1}": object()},
                {"image1": IMAGE, "video1": object()}, {"image1": IMAGE, "video_urls": URL},
                {"video_urls": "file:///bad.mp4"}, {"video_urls": "[bad"}, {"voice_ids": "voice"},
                {"image_element_ids": "element"}, {"video_element_ids": "element"}, {"prompt": 42}):
                with self.assertRaises(api.SeedanceLowPriceError):
                    flash.validate(model, invalid)
            with self.assertRaises(api.SeedanceLowPriceError):
                flash.payload(model, {"prompt": "Robot"}, {"images": [URL], "videos": [URL]})

    def test_legacy_default_and_widget_prefix(self):
        schema = kling.T8ZhenzhenKling4Omni.INPUT_TYPES()
        self.assertEqual(list(schema["optional"])[-4:], ["api_config", "skip_error", "seed", "model"])
        self.assertEqual(schema["optional"]["model"][1]["default"], "kling-v4-omni")
        result = kling.T8ZhenzhenKling4Omni.build_payload({"prompt": "Robot", "voice_ids": "voice"}, {"images": [URL], "videos": [URL]})
        self.assertEqual(result["model"], "kling-v4-omni")
        self.assertEqual(result["metadata"]["voiceIds"], ["voice"])
        self.assertEqual(len(kling.T8ZhenzhenKling4Omni.RETURN_TYPES), 4)

    def test_flash_local_video_order_without_legacy_duration_cap(self):
        with patch.object(api, "video_to_upload_bytes", side_effect=[(b"one", "mp4"), (b"two", "mp4")]), \
             patch.object(kling, "validate_local_video", return_value={"duration": 20}):
            prepared = flash.prepare_media(flash.KLING_MODEL, {"prompt": "Robot", "video2": object(), "video1": object(), "video_urls": URL})
        self.assertEqual(prepared["videos"], [(b"one", "mp4"), (b"two", "mp4")])
        with patch.object(api, "upload_media", side_effect=["one", "two"]):
            media = kling.upload_prepared(prepared, {}, lambda value: None)
        self.assertEqual(media["videos"], ["one", "two", URL])

    def test_all_media_validated_before_any_upload(self):
        with patch.object(api, "upload_media") as upload, patch.object(api, "_get_session") as session:
            with self.assertRaises(api.SeedanceLowPriceError):
                flash.T8ZhenzhenOmni12FlashLowPrice().generate(prompt="Robot", image1=IMAGE, image10=torch.zeros(2, 16, 16, 3))
        upload.assert_not_called()
        session.assert_not_called()

    def test_endpoints_close_responses_and_do_not_retry_submission(self):
        for endpoint in ("video/generations", "videos"):
            submitted = Mock(status_code=200)
            submitted.json.return_value = {"id": "fixture"}
            completed = Mock(status_code=200)
            completed.json.return_value = {"status": "completed", "metadata": {"url": URL}}
            with patch.object(api, "_get_session") as session:
                session.return_value.post.return_value = submitted
                session.return_value.get.return_value = completed
                identifier, _ = kling.submit_kling_task({}, CONFIG, endpoint=endpoint)
                kling.poll_kling_task(identifier, CONFIG, endpoint=endpoint, sleep=lambda value: None)
            self.assertEqual(session.return_value.post.call_args.args[0], f"{CONFIG['base_url']}/v1/{endpoint}")
            self.assertTrue(session.return_value.get.call_args.args[0].endswith(f"/{endpoint}/fixture"))
            submitted.close.assert_called_once()
            completed.close.assert_called_once()
        with patch.object(api, "_get_session") as session:
            session.return_value.post.side_effect = api.requests.ReadTimeout("ambiguous")
            with self.assertRaises(api.SeedanceLowPriceError):
                kling.submit_kling_task({}, CONFIG, endpoint="videos")
            self.assertEqual(session.return_value.post.call_count, 1)

    def test_actual_node_dispatch_and_four_outputs(self):
        for cls, values in ((kling.T8ZhenzhenKling4Omni, {}),
            (kling.T8ZhenzhenKling4Omni, {"model": flash.KLING_MODEL}), (flash.T8ZhenzhenOmni12FlashLowPrice, {})):
            with patch.object(api, "resolve_config", return_value=CONFIG), \
                 patch.object(kling, "submit_kling_task", return_value=("fixture", {})) as submit, \
                 patch.object(kling, "poll_kling_task", return_value={"metadata": {"url": URL}}), \
                 patch.object(api, "download_video", return_value="video"):
                result = cls().generate(prompt="Robot", seed=42, **values)
            self.assertEqual(len(result), 4)
            self.assertNotIn("seed", submit.call_args.args[0])
            self.assertEqual(submit.call_args.kwargs.get("endpoint"), None if not values and cls is kling.T8ZhenzhenKling4Omni else "videos")


class PluginCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = module("Comfly")
        cls.concurrent = module("ComflyConcurrent")

    def test_unique_registration_concurrent_schema_and_preflight(self):
        for key in (OMNI_KEY, KLING_KEY, "T8Zhenzhen_Image_G26_LowPrice"):
            cls = self.plugin.NODE_CLASS_MAPPINGS[key]
            wrapper = self.concurrent.CONCURRENT_NODE_CLASS_MAPPINGS[f"ComflyConcurrent_{key}_Submit"]
            self.assertEqual(cls.INPUT_TYPES(), wrapper.INPUT_TYPES())
            self.assertFalse(hasattr(wrapper, "VALIDATE_INPUTS"))
            with patch.object(self.concurrent.VIDEO_EXECUTOR if key != "T8Zhenzhen_Image_G26_LowPrice" else self.concurrent.IMAGE_EXECUTOR, "submit") as worker:
                with self.assertRaises(ValueError):
                    wrapper().submit(prompt="")
                worker.assert_not_called()

    def test_examples_parse_links_and_blank_keys(self):
        paths = [path for prefix in (flash.KLING_MODEL, flash.OMNI_MODEL) for path in (ROOT / "workflow").glob(prefix + "*.json")]
        self.assertEqual(len(paths), 8)
        for path in paths:
            source = path.read_text(encoding="utf-8")
            workflow = json.loads(source)
            settings = next(node for node in workflow["nodes"] if node["type"] == "T8Zhenzhen_API_Settings")
            self.assertEqual(settings["widgets_values"][1], "")
            by_id = {node["id"]: node for node in workflow["nodes"]}
            for link, origin, slot, target, target_slot, kind in workflow["links"]:
                self.assertIn(link, by_id[origin]["outputs"][slot]["links"])
                self.assertEqual(by_id[target]["inputs"][target_slot]["link"], link)
            self.assertNotRegex(source, r"sk-[A-Za-z0-9]{12,}|X-Amz-Signature")

    def test_concurrent_workers_and_collector_keep_slot_order(self):
        with patch.object(api, "resolve_config", return_value=CONFIG), \
             patch.object(kling, "submit_kling_task", side_effect=lambda request, config, **kwargs: (request["model"], {})), \
             patch.object(kling, "poll_kling_task", return_value={"metadata": {"url": URL}}), \
             patch.object(api, "download_video", return_value="decoded-video"):
            tasks = []
            for key, values in ((KLING_KEY, {"model": flash.KLING_MODEL}), (OMNI_KEY, {})):
                wrapper = self.concurrent.CONCURRENT_NODE_CLASS_MAPPINGS[f"ComflyConcurrent_{key}_Submit"]
                tasks.append(wrapper().submit(prompt="Robot", seed=42, **values)[0])
            result = self.concurrent.ComflyConcurrentVideoAwait().wait_all("fail_fast", task_1=tasks[0], task_2=tasks[1])
        self.assertEqual(result[:2], ("decoded-video", "decoded-video"))
        self.assertEqual(len(result), 11)
        self.assertEqual([slot["node"] for slot in json.loads(result[-1])["slots"][:2]], [KLING_KEY, OMNI_KEY])


if __name__ == "__main__":
    unittest.main()
