import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

import seedance_low_price_nodes as nodes


ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"base_url": "https://example.test", "api_key": "sk-test"}


class Wan30LowPriceTests(unittest.TestCase):
    def test_eight_models_and_documented_controls(self):
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
        self.assertEqual(nodes.WAN30_SECONDS, ["auto", *map(str, range(2, 31))])
        self.assertEqual(nodes.WAN30_RESOLUTIONS, ["480P", "720P", "1080P"])
        self.assertEqual(
            nodes.WAN30_RATIOS,
            ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"],
        )
        inputs = nodes.Comfly_wan_3_0_video_lowprice.INPUT_TYPES()
        self.assertTrue(inputs["required"]["seed"][1]["control_after_generate"])
        expected_optional = (
            ["api_config"]
            + [f"image{index}" for index in range(1, 11)]
            + [f"video{index}" for index in range(1, 6)]
            + [f"audio{index}" for index in range(1, 6)]
            + ["skip_error"]
        )
        self.assertEqual(list(inputs["optional"]), expected_optional)

    def test_i2v_payload_uses_only_first_and_last_frame(self):
        payload = nodes.build_wan30_payload(
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
                    "generate_audio": False,
                    "seed": 7,
                },
            },
        )

    def test_global_i2v_sends_enable_thinking(self):
        payload = nodes.build_wan30_payload(
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
        )
        self.assertTrue(payload["metadata"]["enable_thinking"])
        self.assertNotIn("prompt", payload)

    def test_r2v_payload_uses_documented_media_fields_and_caps(self):
        payload = nodes.build_wan30_payload(
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
        self.assertEqual(
            payload["metadata"]["link_url"],
            "https://example.test/reference",
        )

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

    @patch.object(nodes, "download_video", return_value="downloaded-video")
    @patch.object(
        nodes,
        "poll_task",
        return_value={
            "status": "completed",
            "metadata": {"url": "https://cdn.test/result.mp4"},
        },
    )
    @patch.object(nodes, "submit_task")
    @patch.object(nodes, "audio_to_wav_bytes", return_value=b"wav")
    @patch.object(nodes, "video_to_mp4_bytes", return_value=b"mp4")
    @patch.object(nodes, "image_to_png_bytes", return_value=b"png")
    @patch.object(nodes, "upload_media")
    def test_r2v_node_uploads_image_video_audio_and_executes(
        self,
        upload_media,
        _image_to_png_bytes,
        _video_to_mp4_bytes,
        _audio_to_wav_bytes,
        submit_task,
        _poll_task,
        _download_video,
    ):
        upload_media.side_effect = [
            "https://cdn.test/image.png",
            "https://cdn.test/video.mp4",
            "https://cdn.test/audio.wav",
        ]
        submit_task.return_value = ("task-test", {"id": "task-test"})
        result = nodes.Comfly_wan_3_0_video_lowprice().generate(
            model="wan-3.0-r2v",
            prompt="Use Image 1, Video 1, and Audio 1",
            seconds="2",
            resolution="480P",
            ratio="adaptive",
            generate_audio=True,
            enable_thinking=False,
            file_url="",
            link_url="",
            seed=3,
            api_config=CONFIG,
            image1=np.zeros((1, 32, 32, 3), dtype=np.float32),
            video1=object(),
            audio1={"waveform": np.zeros((1, 1, 16)), "sample_rate": 16000},
        )
        self.assertEqual(result[:3], ("downloaded-video", "https://cdn.test/result.mp4", "task-test"))
        payload = submit_task.call_args.args[0]
        self.assertEqual(payload["images"], ["https://cdn.test/image.png"])
        self.assertEqual(payload["metadata"]["video_url"], ["https://cdn.test/video.mp4"])
        self.assertEqual(payload["metadata"]["audio_url"], ["https://cdn.test/audio.wav"])

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
                )
        session.post.assert_called_once()

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
            node = next(
                item
                for item in workflow["nodes"]
                if item["type"] == "Comfly_wan_3_0_video_lowprice"
            )
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
        self.assertEqual(covered, set(nodes.WAN30_MODELS))


if __name__ == "__main__":
    unittest.main()
