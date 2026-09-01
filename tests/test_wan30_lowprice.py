from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


CONFIG = {"base_url": "https://example.test", "api_key": "test"}
IMAGE = torch.zeros((1, 8, 8, 3), dtype=torch.float32)


<<<<<<< HEAD
class Wan30LowPriceTests(unittest.TestCase):
    def test_eight_models_and_documented_controls(self):
=======
def base_values(model: str) -> dict:
    return {
        "model": model,
        "prompt": "Use Image 1, Video 1, and Audio 1 as ordered references",
        "seconds": "2",
        "resolution": "480P",
        "ratio": "adaptive",
        "generate_audio": True,
        "enable_thinking": False,
        "file_url": "",
        "link_url": "",
        "seed": 7,
    }


class Wan30LowPriceContractTests(unittest.TestCase):
    def test_documented_models_and_controls(self):
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
        self.assertEqual(
            nodes.WAN30_MODELS,
            [
                "wan-3.0-i2v",
                "wan-3.0-r2v",
                "wan-3.0-global-i2v",
                "wan-3.0-global-r2v",
                "wan-3.0-prime-i2v",
                "wan-3.0-prime-r2v",
                "wan-3.0-global-prime-i2v",
                "wan-3.0-global-prime-r2v",
            ],
        )
        self.assertEqual(
            nodes.WAN30_SECONDS,
            ["auto", *[str(value) for value in range(2, 31)]],
        )
        self.assertEqual(nodes.WAN30_RESOLUTIONS, ["480P", "720P", "1080P"])
        self.assertEqual(
            nodes.WAN30_RATIOS,
            ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"],
        )
        inputs = nodes.Comfly_wan_3_0_video_lowprice.INPUT_TYPES()
<<<<<<< HEAD
        self.assertTrue(inputs["required"]["seed"][1]["control_after_generate"])
        expected_optional = (
            ["api_config"]
            + [f"image{index}" for index in range(1, 11)]
            + [f"video{index}" for index in range(1, 6)]
            + [f"audio{index}" for index in range(1, 6)]
            + ["skip_error"]
=======
        self.assertEqual(inputs["required"]["model"][0], nodes.WAN30_MODELS)
        self.assertTrue(
            inputs["required"]["seed"][1]["control_after_generate"]
        )
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("image")],
            [f"image{index}" for index in range(1, 11)],
        )
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("video")],
            [f"video{index}" for index in range(1, 6)],
        )
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("audio")],
            [f"audio{index}" for index in range(1, 6)],
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
        )

    def test_i2v_payload_uses_first_and_optional_last_frame(self):
        values = base_values(nodes.WAN30_I2V_MODEL)
        values["prompt"] = "slow cinematic push in"
        payload = nodes.build_wan30_payload(
<<<<<<< HEAD
            {
                "model": "wan-3.0-i2v",
                "prompt": "slow cinematic push in",
                "seconds": "2",
                "resolution": "480P",
                "ratio": "adaptive",
                "generate_audio": False,
                "enable_thinking": True,
                "file_url": "",
                "link_url": "",
                "seed": 7,
            },
            {"images": ["https://cdn.test/first.png", "https://cdn.test/last.png"]},
=======
            values,
            {
                "images": [
                    "https://cdn.test/first.png",
                    "https://cdn.test/last.png",
                ]
            },
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
        )
        self.assertEqual(
            payload,
            {
                "model": "wan-3.0-i2v",
                "prompt": "slow cinematic push in",
                "seconds": "2",
                "images": [
                    "https://cdn.test/first.png",
                    "https://cdn.test/last.png",
                ],
                "metadata": {
                    "resolution": "480P",
                    "ratio": "adaptive",
                    "generate_audio": True,
                    "seed": 7,
                },
            },
        )

    def test_global_i2v_forwards_enable_thinking(self):
        values = base_values(nodes.WAN30_GLOBAL_I2V_MODEL)
        values.update(
            {
                "prompt": "",
                "seconds": "auto",
                "resolution": "720P",
                "ratio": "16:9",
                "enable_thinking": True,
            }
        )
        payload = nodes.build_wan30_payload(
<<<<<<< HEAD
            {
                "model": "wan-3.0-global-i2v",
                "prompt": "",
                "seconds": "auto",
                "resolution": "720P",
                "ratio": "16:9",
                "generate_audio": True,
                "enable_thinking": True,
                "file_url": "",
                "link_url": "",
                "seed": 0,
            },
            {"images": ["https://cdn.test/first.png"]},
=======
            values, {"images": ["https://cdn.test/first.png"]}
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
        )
        self.assertTrue(payload["metadata"]["enable_thinking"])
        self.assertNotIn("prompt", payload)

    def test_global_prime_i2v_omits_unsupported_enable_thinking(self):
        values = base_values(nodes.WAN30_GLOBAL_PRIME_I2V_MODEL)
        values["enable_thinking"] = True
        payload = nodes.build_wan30_payload(
<<<<<<< HEAD
            {
                "model": "wan-3.0-r2v",
                "prompt": "Image 1 enters Video 1 while Audio 1 guides the rhythm",
                "seconds": "30",
                "resolution": "1080P",
                "ratio": "9:16",
                "generate_audio": True,
                "enable_thinking": True,
                "file_url": "https://files.test/reference.pdf",
                "link_url": "",
                "seed": 2147483647,
            },
            {
                "images": [f"https://cdn.test/image-{index}.png" for index in range(1, 12)],
                "video_urls": [f"https://cdn.test/video-{index}.mp4" for index in range(1, 7)],
                "audio_urls": [f"https://cdn.test/audio-{index}.wav" for index in range(1, 7)],
=======
            values, {"images": ["https://cdn.test/first.png"]}
        )
        self.assertNotIn("enable_thinking", payload["metadata"])

    def test_r2v_payload_forwards_all_documented_material_groups(self):
        values = base_values(nodes.WAN30_R2V_MODEL)
        values.update(
            {
                "seconds": "30",
                "resolution": "1080P",
                "ratio": "9:16",
                "file_url": "https://files.test/reference.pdf",
                "seed": 2147483647,
            }
        )
        payload = nodes.build_wan30_payload(
            values,
            {
                "images": [
                    f"https://cdn.test/image-{index}.png"
                    for index in range(1, 12)
                ],
                "video_urls": [
                    f"https://cdn.test/video-{index}.mp4"
                    for index in range(1, 7)
                ],
                "audio_urls": [
                    f"https://cdn.test/audio-{index}.wav"
                    for index in range(1, 7)
                ],
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
            },
        )
        self.assertEqual(len(payload["images"]), 10)
        self.assertEqual(len(payload["metadata"]["video_url"]), 5)
        self.assertEqual(len(payload["metadata"]["audio_url"]), 5)
        self.assertEqual(
            payload["metadata"]["file_url"],
            "https://files.test/reference.pdf",
        )
        self.assertNotIn("enable_thinking", payload["metadata"])

<<<<<<< HEAD
    def test_global_r2v_forces_thinking_for_file_or_link(self):
        payload = nodes.build_wan30_payload(
            {
                "model": "wan-3.0-global-r2v",
                "prompt": "Use the referenced webpage as context",
                "seconds": "2",
                "resolution": "480P",
                "ratio": "adaptive",
                "generate_audio": False,
                "enable_thinking": False,
                "file_url": "",
                "link_url": "https://example.test/reference",
                "seed": 1,
            },
            {},
        )
        self.assertTrue(payload["metadata"]["enable_thinking"])
=======
    def test_global_r2v_reference_url_forces_thinking(self):
        values = base_values(nodes.WAN30_GLOBAL_R2V_MODEL)
        values["link_url"] = "https://example.test/reference"
        payload = nodes.build_wan30_payload(values, {})
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
        self.assertEqual(
            payload["metadata"]["link_url"],
            "https://example.test/reference",
        )
        self.assertTrue(payload["metadata"]["enable_thinking"])

<<<<<<< HEAD
    def test_validation_rejects_invalid_model_contracts(self):
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "requires image1"):
            nodes.validate_wan30_inputs(
                "wan-3.0-i2v",
                "",
                "2",
                "480P",
                "adaptive",
                "",
                "",
                0,
                strict=True,
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "prompt is required"):
            nodes.validate_wan30_inputs(
                "wan-3.0-r2v",
                "",
                "2",
                "480P",
                "adaptive",
                "",
                "",
                0,
                strict=True,
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "mutually exclusive"):
            nodes.validate_wan30_inputs(
                "wan-3.0-r2v",
                "reference",
                "2",
                "480P",
                "adaptive",
                "https://files.test/reference.pdf",
                "https://example.test/reference",
                0,
                strict=True,
            )
=======
    def test_global_prime_r2v_forwards_link_without_thinking(self):
        values = base_values(nodes.WAN30_GLOBAL_PRIME_R2V_MODEL)
        values.update(
            {
                "enable_thinking": True,
                "link_url": "https://example.test/reference",
            }
        )
        payload = nodes.build_wan30_payload(values, {})
        self.assertEqual(
            payload["metadata"]["link_url"],
            "https://example.test/reference",
        )
        self.assertNotIn("enable_thinking", payload["metadata"])

    def test_validation_matches_model_specific_contracts(self):
        common = {
            "seconds": "2",
            "resolution": "480P",
            "ratio": "adaptive",
            "file_url": "",
            "link_url": "",
            "seed": 0,
            "strict": True,
        }
        self.assertIs(
            nodes.Comfly_wan_3_0_video_lowprice.VALIDATE_INPUTS(
                model=nodes.WAN30_I2V_MODEL,
                prompt="",
                image1=IMAGE,
                **common,
            ),
            True,
        )
        self.assertIn(
            "requires image1",
            nodes.Comfly_wan_3_0_video_lowprice.VALIDATE_INPUTS(
                model=nodes.WAN30_I2V_MODEL,
                prompt="",
                **common,
            ),
        )
        self.assertIn(
            "prompt is required",
            nodes.Comfly_wan_3_0_video_lowprice.VALIDATE_INPUTS(
                model=nodes.WAN30_R2V_MODEL,
                prompt="",
                **common,
            ),
        )
        self.assertIn(
            "mutually exclusive",
            nodes.Comfly_wan_3_0_video_lowprice.VALIDATE_INPUTS(
                model=nodes.WAN30_R2V_MODEL,
                prompt="reference",
                seconds="2",
                resolution="480P",
                ratio="adaptive",
                file_url="https://files.test/reference.pdf",
                link_url="https://example.test/reference",
                seed=0,
                strict=True,
            ),
        )
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a

    @patch.object(nodes, "audio_to_wav_bytes", return_value=b"wav")
    @patch.object(nodes, "video_to_mp4_bytes", return_value=b"mp4")
    @patch.object(nodes, "image_to_png_bytes", return_value=b"png")
    @patch.object(nodes, "upload_media")
    def test_r2v_collects_images_videos_and_audios(
        self,
        upload_media,
        image_to_png_bytes,
        video_to_mp4_bytes,
        audio_to_wav_bytes,
    ):
        upload_media.side_effect = [
            "https://cdn.test/image.png",
            "https://cdn.test/video.mp4",
            "https://cdn.test/audio.wav",
        ]
        progress = []
        values = base_values(nodes.WAN30_R2V_MODEL)
        values.update(
            {"image1": IMAGE, "video1": object(), "audio1": object()}
        )
        media = nodes.Comfly_wan_3_0_video_lowprice().collect_media(
            values, CONFIG, progress.append
        )
        self.assertEqual(
            media,
            {
                "images": ["https://cdn.test/image.png"],
                "video_urls": ["https://cdn.test/video.mp4"],
                "audio_urls": ["https://cdn.test/audio.wav"],
            },
        )
        self.assertEqual(progress, [1 / 3, 2 / 3, 1.0])
        image_to_png_bytes.assert_called_once()
        video_to_mp4_bytes.assert_called_once()
        audio_to_wav_bytes.assert_called_once()

<<<<<<< HEAD
    def test_api_key_validation_does_not_echo_secret(self):
        for bad_key in ("bad", "sk-has space", " sk-test", "sk-test\n", "sk-中文"):
            with self.subTest(bad_key=bad_key):
                with self.assertRaises(nodes.SeedanceLowPriceError) as caught:
                    nodes.resolve_config(
                        {"base_url": "https://example.test", "api_key": bad_key}
                    )
                self.assertNotIn(bad_key, str(caught.exception))

    def test_video_submit_does_not_replay_http_500(self):
        response = Mock(status_code=500, text="upstream error")
        response.json.return_value = {"message": "upstream error"}
        session = Mock()
        session.post.return_value = response
        with patch.object(nodes, "_get_session", return_value=session):
            with self.assertRaisesRegex(RuntimeError, "not retried"):
                nodes.submit_task(
                    {"model": "wan-3.0-i2v"},
                    CONFIG,
                    sleep=lambda _seconds: None,
=======
    def test_invalid_r2v_is_rejected_before_upload(self):
        values = base_values(nodes.WAN30_R2V_MODEL)
        values["prompt"] = ""
        values["image1"] = IMAGE
        with patch.object(nodes, "upload_media") as upload:
            with self.assertRaisesRegex(
                nodes.SeedanceLowPriceError, "prompt is required"
            ):
                nodes.Comfly_wan_3_0_video_lowprice().collect_media(
                    values, CONFIG
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
                )
        upload.assert_not_called()

<<<<<<< HEAD
    def test_workflows_are_safe_and_cover_all_models(self):
        paths = sorted((ROOT / "workflow").glob("zhenzhen-wan-3.0-*.json"))
        self.assertGreaterEqual(len(paths), 8)
        covered = set()
        media_first_inputs = (
            [f"image{index}" for index in range(1, 11)]
            + [f"video{index}" for index in range(1, 6)]
            + [f"audio{index}" for index in range(1, 6)]
            + ["api_config"]
        )
        config_first_inputs = ["api_config", *media_first_inputs[:-1]]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("sk-", text)
            workflow = json.loads(text)
=======
    def test_generate_runs_shared_submit_poll_and_download_path(self):
        final = {
            "status": "completed",
            "metadata": {"url": "https://cdn.test/result.mp4"},
        }
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(nodes, "image_to_png_bytes", return_value=b"png"),
            patch.object(
                nodes,
                "upload_media",
                return_value="https://cdn.test/first.png",
            ),
            patch.object(
                nodes,
                "submit_task",
                return_value=("safe-task", {"id": "safe-task"}),
            ) as submit,
            patch.object(nodes, "poll_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_wan_3_0_video_lowprice().generate(
                model=nodes.WAN30_I2V_MODEL,
                prompt="keep the subject consistent",
                seconds="2",
                resolution="480P",
                ratio="adaptive",
                generate_audio=True,
                enable_thinking=False,
                file_url="",
                link_url="",
                seed=1,
                image1=IMAGE,
            )
        self.assertEqual(result[0], "downloaded-video")
        self.assertEqual(
            submit.call_args.args[0]["images"],
            ["https://cdn.test/first.png"],
        )


class Wan30LowPriceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.paths = sorted(
            (PLUGIN_ROOT / "workflow").glob(
                "zhenzhen-wan-3.0-*（贞贞的平价AI小屋）.json"
            )
        )

    def test_safe_workflows_cover_all_models(self):
        self.assertGreaterEqual(len(self.paths), len(nodes.WAN30_MODELS))
        covered = set()
        for path in self.paths:
            raw = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw))
            workflow = json.loads(raw)
            settings = next(
                item for item in workflow["nodes"] if item["type"] == "T8Zhenzhen_API_Settings"
            )
            self.assertEqual(
                settings["widgets_values"],
                ["seedance_low_price", "", "", False],
            )
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
            node = next(
                item
                for item in workflow["nodes"]
                if item["type"] == "Comfly_wan_3_0_video_lowprice"
            )
<<<<<<< HEAD
            covered.add(node["widgets_values"][0])
            input_names = [item["name"] for item in node["inputs"]]
            self.assertIn(input_names, (media_first_inputs, config_first_inputs))
            settings = next(
                item
                for item in workflow["nodes"]
                if item["type"] in {"Comfly_api_set", "T8Zhenzhen_API_Settings"}
            )
            self.assertEqual(settings["widgets_values"], ["seedance_low_price", "", "", False])
            incoming = [link for link in workflow["links"] if link[3] == node["id"]]
            media_names = {
                input_names[link[4]]
                for link in incoming
                if link[5] in {"IMAGE", "VIDEO", "AUDIO"}
            }
            if node["widgets_values"][0].endswith("-i2v"):
                self.assertEqual(media_names, {"image1", "image2"})
            elif "prime" in node["widgets_values"][0]:
                self.assertEqual(media_names, {"image1"})
            else:
                self.assertEqual(media_names, {"image1", "video1", "audio1"})
=======
            model = node["widgets_values"][0]
            covered.add(model)
            self.assertEqual(node["widgets_values"][2:5], ["2", "480P", "adaptive"])
            self.assertEqual(len(node["inputs"]), 21)
            config = next(value for value in node["inputs"] if value["name"] == "api_config")
            self.assertIsNotNone(config["link"])
            connected = [
                value["name"] for value in node["inputs"] if value["link"] is not None
            ]
            if model.endswith("-i2v"):
                self.assertEqual(set(connected), {"api_config", "image1", "image2"})
            elif "-prime-r2v" in model:
                self.assertEqual(set(connected), {"api_config", "image1"})
            else:
                self.assertEqual(
                    set(connected),
                    {"api_config", "image1", "video1", "audio1"},
                )
>>>>>>> 9f93c1ae1c99828234d996f12d3e86e1ff1db15a
        self.assertEqual(covered, set(nodes.WAN30_MODELS))

    def test_registration_frontend_and_api_key_button(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        frontend = (PLUGIN_ROOT / "web/js/wan30_model_ui.js").read_text(
            encoding="utf-8"
        )
        api_link = (
            PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"Comfly_wan_3_0_video_lowprice"', comfly)
        self.assertIn(
            '"Comfly_wan_3_0_video_lowprice": "zhenzhen-wan-3.0-video-lowprice（8合1）"',
            comfly,
        )
        self.assertIn(
            'const NODE_NAME = "Comfly_wan_3_0_video_lowprice"', frontend
        )
        self.assertIn('widgetByName(node, "enable_thinking")', frontend)
        self.assertIn("THINKING_MODELS.has(model)", frontend)
        self.assertIn('model.endsWith("-r2v")', frontend)
        self.assertIn("setZhenzhenInputVisible", frontend)
        self.assertIn('"Comfly_wan_3_0_video_lowprice"', api_link)


if __name__ == "__main__":
    unittest.main()
