import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


CONFIG = {"base_url": "https://api.seedance.nz", "api_key": "test-key"}


def build_payload(model, **overrides):
    values = {
        "model": model,
        "prompt": "a silver paper airplane crossing a clean studio",
        "seconds": "5",
        "resolution": "hd",
        "ratio": "16:9",
        "draft": False,
        "audio_mode": "api_default",
        "safety_tolerance": "api_default",
        "image_urls": None,
        "uploaded_video_url": "",
        "draft_cache": "",
    }
    values.update(overrides)
    return nodes.build_flux3_payload(**values)


class Flux3ContractTests(unittest.TestCase):
    def test_exact_documented_model_catalog_and_inputs(self):
        self.assertEqual(
            nodes.FLUX3_VIDEO_MODELS,
            [
                "flux-3-video-t2v",
                "flux-3-video-i2v",
                "flux-3-video-v2v",
                "flux-3-video-draft-enhance",
                "flux-3-video-global-t2v",
                "flux-3-video-global-i2v",
                "flux-3-video-global-v2v",
                "flux-3-video-global-draft-enhance",
            ],
        )
        inputs = nodes.Comfly_flux3_video_lowprice.INPUT_TYPES()
        self.assertEqual(inputs["required"]["seconds"][0], [str(value) for value in range(5, 21)])
        self.assertEqual(inputs["required"]["resolution"][0], ["hd", "fhd"])
        self.assertEqual(inputs["required"]["ratio"][0], nodes.FLUX3_RATIOS)
        self.assertEqual(
            list(inputs["optional"]),
            [
                "api_config",
                *[f"image{index}" for index in range(1, 11)],
                "input_video",
                "video_url",
                "draft_cache",
                "skip_error",
            ],
        )

    def test_t2v_payload_forwards_documented_optional_controls(self):
        payload = build_payload(
            "flux-3-video-t2v",
            draft=True,
            audio_mode="disabled",
            safety_tolerance="3",
        )
        self.assertEqual(
            payload,
            {
                "model": "flux-3-video-t2v",
                "prompt": "a silver paper airplane crossing a clean studio",
                "seconds": "5",
                "metadata": {
                    "resolution": "hd",
                    "ratio": "16:9",
                    "draft": True,
                    "generate_audio": False,
                    "safety_tolerance": 3,
                },
            },
        )

    def test_i2v_payload_accepts_ten_ordered_keyframes(self):
        urls = [f"https://example.test/keyframe-{index}.png" for index in range(1, 11)]
        payload = build_payload(
            "flux-3-video-global-i2v",
            image_urls=urls,
        )
        self.assertEqual(payload["images"], urls)
        self.assertNotIn("video_url", payload["metadata"])

    def test_v2v_payload_maps_one_video_url_into_metadata(self):
        payload = build_payload(
            "flux-3-video-v2v",
            uploaded_video_url="https://example.test/source.mp4",
        )
        self.assertEqual(
            payload["metadata"]["video_url"],
            "https://example.test/source.mp4",
        )
        self.assertNotIn("images", payload)

    def test_draft_enhance_uses_cache_without_prompt(self):
        payload = build_payload(
            "flux-3-video-global-draft-enhance",
            prompt="",
            draft=True,
            draft_cache="cache-for-test",
        )
        self.assertEqual(
            payload,
            {
                "model": "flux-3-video-global-draft-enhance",
                "seconds": "5",
                "metadata": {
                    "resolution": "hd",
                    "ratio": "16:9",
                    "draft_cache": "cache-for-test",
                },
            },
        )

    def test_mode_specific_validation(self):
        cases = (
            ("flux-3-video-t2v", {}, "requires a prompt"),
            ("flux-3-video-i2v", {"prompt": "valid"}, "requires image1"),
            (
                "flux-3-video-v2v",
                {"prompt": "valid"},
                "requires input_video or video_url",
            ),
            (
                "flux-3-video-draft-enhance",
                {"prompt": ""},
                "requires draft_cache",
            ),
        )
        for model, overrides, message in cases:
            with self.subTest(model=model):
                values = {"prompt": ""}
                values.update(overrides)
                with self.assertRaisesRegex(nodes.SeedanceLowPriceError, message):
                    build_payload(model, **values)

    def test_i2v_execution_uploads_connected_images_in_slot_order(self):
        final = {
            "status": "completed",
            "metadata": {"url": "https://example.test/result.mp4"},
        }
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(nodes, "image_to_png_bytes", return_value=b"png"),
            patch.object(
                nodes,
                "upload_media",
                side_effect=[
                    "https://example.test/1.png",
                    "https://example.test/2.png",
                    "https://example.test/10.png",
                ],
            ) as upload,
            patch.object(nodes, "submit_task", return_value=("safe-task", {"id": "safe-task"})) as submit,
            patch.object(nodes, "poll_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_flux3_video_lowprice().generate(
                model="flux-3-video-global-i2v",
                prompt="move smoothly between the keyframes",
                seconds="5",
                resolution="hd",
                ratio="16:9",
                draft=False,
                audio_mode="api_default",
                safety_tolerance="api_default",
                image1=object(),
                image2=object(),
                image10=object(),
            )
        self.assertEqual(upload.call_count, 3)
        self.assertEqual(
            submit.call_args.args[0]["images"],
            [
                "https://example.test/1.png",
                "https://example.test/2.png",
                "https://example.test/10.png",
            ],
        )
        self.assertEqual(result[0], "downloaded-video")

    def test_v2v_direct_url_skips_upload_and_draft_cache_is_output(self):
        final = {
            "status": "completed",
            "metadata": {
                "url": "https://example.test/result.mp4",
                "draft_cache": "cache-result",
            },
        }
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(nodes, "upload_media") as upload,
            patch.object(nodes, "submit_task", return_value=("safe-task", {"id": "safe-task"})) as submit,
            patch.object(nodes, "poll_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_flux3_video_lowprice().generate(
                model="flux-3-video-v2v",
                prompt="restyle the source video",
                seconds="5",
                resolution="hd",
                ratio="16:9",
                draft=True,
                audio_mode="api_default",
                safety_tolerance="api_default",
                video_url="https://example.test/source.mp4",
            )
        upload.assert_not_called()
        self.assertEqual(
            submit.call_args.args[0]["metadata"]["video_url"],
            "https://example.test/source.mp4",
        )
        self.assertEqual(result[2], "cache-result")
        self.assertEqual(len(result), 5)

    def test_skip_error_preserves_five_output_contract(self):
        with patch.object(nodes, "resolve_config", side_effect=RuntimeError("test failure")):
            result = nodes.Comfly_flux3_video_lowprice().generate(
                model="flux-3-video-t2v",
                prompt="valid prompt",
                seconds="5",
                resolution="hd",
                ratio="16:9",
                draft=False,
                audio_mode="api_default",
                safety_tolerance="api_default",
                skip_error=True,
            )
        self.assertEqual(len(result), 5)
        self.assertEqual(result[1:4], ("", "", ""))


class Flux3WorkflowFrontendTests(unittest.TestCase):
    def setUp(self):
        self.paths = sorted(
            (PLUGIN_ROOT / "workflow").glob(
                "zhenzhen-flux-3-video*（贞贞的平价AI小屋）.json"
            )
        )

    def test_all_models_have_safe_workflows(self):
        self.assertEqual(len(self.paths), 8)
        covered = set()
        for path in self.paths:
            raw = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw), path.name)
            workflow = json.loads(raw)
            settings = next(
                node for node in workflow["nodes"] if node["type"] == "T8Zhenzhen_API_Settings"
            )
            self.assertEqual(settings["widgets_values"], ["seedance_low_price", "", "", False])
            model_nodes = [
                node
                for node in workflow["nodes"]
                if node["type"] == "Comfly_flux3_video_lowprice"
            ]
            target = next(
                (
                    node
                    for node in model_nodes
                    if node["widgets_values"][0].endswith("-draft-enhance")
                ),
                model_nodes[0],
            )
            model = target["widgets_values"][0]
            covered.add(model)
            config_input = next(item for item in target["inputs"] if item["name"] == "api_config")
            self.assertIsNotNone(config_input["link"])

            connected = {
                item["name"] for item in target["inputs"] if item["link"] is not None
            }
            if model.endswith("-i2v"):
                self.assertTrue({"image1", "image2"}.issubset(connected))
            elif model.endswith("-v2v"):
                self.assertIn("input_video", connected)
            elif model.endswith("-draft-enhance"):
                self.assertIn("draft_cache", connected)
                source = next(
                    node
                    for node in model_nodes
                    if not node["widgets_values"][0].endswith("-draft-enhance")
                )
                self.assertTrue(source["widgets_values"][5])
                self.assertEqual(
                    "-global-" in source["widgets_values"][0],
                    "-global-" in model,
                )
        self.assertEqual(covered, set(nodes.FLUX3_VIDEO_MODELS))

    def test_registration_frontend_concurrency_and_api_key_button(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        frontend = (PLUGIN_ROOT / "web/js/flux3_video_model_ui.js").read_text(encoding="utf-8")
        api_link = (PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js").read_text(encoding="utf-8")
        self.assertIn('"Comfly_flux3_video_lowprice": Comfly_flux3_video_lowprice', comfly)
        self.assertIn(
            '"Comfly_flux3_video_lowprice": "zhenzhen-flux-3-video-lowprice"',
            comfly,
        )
        self.assertIn('const FLUX3_NODE_NAME = "Comfly_flux3_video_lowprice"', frontend)
        self.assertIn('model.endsWith("-draft-enhance")', frontend)
        self.assertIn("nextVisibleImageSlot", frontend)
        self.assertIn("setZhenzhenInputVisible", frontend)
        self.assertIn('"Comfly_flux3_video_lowprice"', api_link)


if __name__ == "__main__":
    unittest.main()
