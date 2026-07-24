import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import torch

import seedance_low_price_nodes as nodes


ROOT = Path(__file__).resolve().parent
WORKFLOW_NODE_TYPES = {
    "zhenzhen-image-g-v2-lowprice文生图（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_image_g_v2_lowprice",
    "zhenzhen-image-g-v2-lowprice图生图（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_image_g_v2_lowprice",
    "zhenzhen-image-gk-v15文生图（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_image_gk_v15_lowprice",
    "zhenzhen-image-gk-v15图像编辑（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_image_gk_v15_lowprice",
    "zhenzhen-video-g-omni-flash文生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_g_omni_flash_lowprice",
    "zhenzhen-video-g-omni-flash图生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_g_omni_flash_lowprice",
    "zhenzhen-video-g-omni-flash视频编辑（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_g_omni_flash_lowprice",
    "zhenzhen-video-g-omni-flash任务续作（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_g_omni_flash_lowprice",
    "zhenzhen-video-gk-v15文生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_gk_v15_lowprice",
    "zhenzhen-video-gk-v15图生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_gk_v15_lowprice",
    "zhenzhen-video-v31-fast文生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_v31_lowprice",
    "zhenzhen-video-v31-fast图生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_v31_lowprice",
    "zhenzhen-video-v31-fast三图参考生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_v31_lowprice",
    "zhenzhen-video-v31-quality文生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_v31_lowprice",
    "zhenzhen-video-v31-quality图生视频（贞贞的平价AI小屋）.json": "Comfly_zhenzhen_video_v31_lowprice",
    "whisper-1语音转写（贞贞的平价AI小屋）.json": "Comfly_whisper_1_lowprice",
}


class APIMartPayloadTests(unittest.TestCase):
    def test_image_g_v2_text_and_image_payloads(self):
        text_payload = nodes.build_zhenzhen_image_g_v2_payload(
            nodes.ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL,
            "watercolor cat",
            "2k",
            "1024x1536",
            2,
        )
        self.assertEqual(
            text_payload,
            {
                "model": "zhenzhen-image-g-v2-lowprice",
                "prompt": "watercolor cat",
                "n": 2,
                "size": "1024x1536",
                "metadata": {"resolution": "2k"},
            },
        )

        image_payload = nodes.build_zhenzhen_image_g_v2_payload(
            nodes.ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL,
            "make this watercolor",
            "1k",
            "1:1",
            1,
            ["https://cdn.test/reference.png"],
        )
        self.assertEqual(image_payload["images"], ["https://cdn.test/reference.png"])
        with self.assertRaises(nodes.SeedanceLowPriceError):
            nodes.build_zhenzhen_image_g_v2_payload(
                nodes.ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL,
                "too many",
                "1k",
                "1:1",
                1,
                [f"https://cdn.test/{index}.png" for index in range(17)],
            )

    def test_image_gk_generation_and_edit_contract(self):
        text_payload = nodes.build_zhenzhen_image_gk_v15_payload(
            nodes.ZHENZHEN_IMAGE_GK_V15_MODEL,
            "cinematic city",
            "16:9",
            1,
        )
        self.assertNotIn("images", text_payload)
        edit_payload = nodes.build_zhenzhen_image_gk_v15_payload(
            nodes.ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL,
            "replace the sky",
            "1:1",
            3,
            ["https://cdn.test/first.png", "https://cdn.test/ignored.png"],
        )
        self.assertEqual(edit_payload["images"], ["https://cdn.test/first.png"])
        with self.assertRaises(nodes.SeedanceLowPriceError):
            nodes.build_zhenzhen_image_gk_v15_payload(
                nodes.ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL,
                "replace the sky",
                "1:1",
                1,
            )

    def test_video_gk_contract(self):
        payload = nodes.build_zhenzhen_video_gk_v15_payload(
            "dog running",
            "30",
            "720p",
            "2:3",
            [f"https://cdn.test/{index}.png" for index in range(7)],
        )
        self.assertEqual(payload["seconds"], "30")
        self.assertEqual(payload["metadata"], {"resolution": "720p", "ratio": "2:3"})
        self.assertEqual(len(payload["images"]), 7)
        with self.assertRaises(nodes.SeedanceLowPriceError):
            nodes.build_zhenzhen_video_gk_v15_payload(
                "dog running", "5", "720p", "16:9"
            )

    def test_video_v31_fixed_duration_and_quality_reference_restriction(self):
        payload = nodes.build_zhenzhen_video_v31_payload(
            nodes.ZHENZHEN_VIDEO_V31_FAST_MODEL,
            "dolphins",
            "4k",
            "9:16",
            ["one", "two", "three"],
        )
        self.assertEqual(payload["seconds"], "8")
        self.assertEqual(payload["images"], ["one", "two", "three"])
        with self.assertRaises(nodes.SeedanceLowPriceError):
            nodes.build_zhenzhen_video_v31_payload(
                nodes.ZHENZHEN_VIDEO_V31_QUALITY_MODEL,
                "dolphins",
                "720p",
                "16:9",
                ["one", "two", "three"],
            )

    def test_omni_contract_omits_duration_and_enforces_video_exclusivity(self):
        payload = nodes.build_zhenzhen_video_g_omni_flash_payload(
            "change the sky",
            "16:9",
            image_urls=["https://cdn.test/reference.png"],
            video_url="https://cdn.test/input.mp4",
        )
        self.assertNotIn("seconds", payload)
        self.assertEqual(
            payload["metadata"],
            {
                "resolution": "720p",
                "ratio": "16:9",
                "video_url": "https://cdn.test/input.mp4",
            },
        )
        with self.assertRaises(nodes.SeedanceLowPriceError):
            nodes.build_zhenzhen_video_g_omni_flash_payload(
                "continue",
                "16:9",
                video_url="https://cdn.test/input.mp4",
                extend_from_task_id="task-id",
            )


class APIMartExecutionTests(unittest.TestCase):
    def test_image_g_v2_upload_submit_poll_and_download(self):
        node = nodes.Comfly_zhenzhen_image_g_v2_lowprice()
        reference = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
        result_tensor = torch.ones((1, 4, 4, 3), dtype=torch.float32)
        with patch.object(
            nodes,
            "resolve_config",
            return_value={"base_url": nodes.DEFAULT_BASE_URL, "api_key": "test"},
        ), patch.object(
            nodes,
            "upload_media",
            return_value="https://cdn.test/reference.png",
        ), patch.object(
            nodes,
            "submit_image_task",
            return_value=("image-task", {"id": "image-task"}),
        ) as submit, patch.object(
            nodes,
            "poll_image_task",
            return_value={
                "data": {
                    "status": "SUCCESS",
                    "result_url": "https://cdn.test/result.png",
                }
            },
        ), patch.object(
            nodes,
            "download_image",
            return_value=result_tensor,
        ):
            output = node.generate_image(
                model=nodes.ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL,
                prompt="make this watercolor",
                resolution="1k",
                size="1:1",
                n=1,
                image1=reference,
            )

        self.assertEqual(
            submit.call_args.args[0]["images"], ["https://cdn.test/reference.png"]
        )
        self.assertIs(output[0], result_tensor)
        self.assertEqual(output[1:3], ("https://cdn.test/result.png", "image-task"))

    def test_omni_video_edit_uploads_mp4_and_submits_metadata_video_url(self):
        node = nodes.Comfly_zhenzhen_video_g_omni_flash_lowprice()
        with patch.object(
            nodes,
            "resolve_config",
            return_value={"base_url": nodes.DEFAULT_BASE_URL, "api_key": "test"},
        ), patch.object(
            nodes,
            "video_to_mp4_bytes",
            return_value=b"mp4",
        ), patch.object(
            nodes,
            "upload_media",
            return_value="https://cdn.test/input.mp4",
        ), patch.object(
            nodes,
            "submit_task",
            return_value=("video-task", {"id": "video-task"}),
        ) as submit, patch.object(
            nodes,
            "poll_task",
            return_value={
                "status": "completed",
                "metadata": {"url": "https://cdn.test/result.mp4"},
            },
        ), patch.object(
            nodes,
            "download_video",
            return_value="downloaded-video",
        ):
            output = node.generate(
                prompt="change the sky",
                resolution="720p",
                ratio="16:9",
                input_video="video-input",
            )

        payload = submit.call_args.args[0]
        self.assertEqual(
            payload["metadata"]["video_url"], "https://cdn.test/input.mp4"
        )
        self.assertNotIn("seconds", payload)
        self.assertEqual(output[0], "downloaded-video")
        self.assertEqual(output[2], "video-task")

    def test_whisper_node_converts_audio_and_uses_synchronous_helper(self):
        node = nodes.Comfly_whisper_1_lowprice()
        audio = {
            "waveform": torch.zeros((1, 1, 1600), dtype=torch.float32),
            "sample_rate": 16000,
        }
        with patch.object(
            nodes,
            "resolve_config",
            return_value={"base_url": nodes.DEFAULT_BASE_URL, "api_key": "test"},
        ), patch.object(
            nodes,
            "transcribe_audio",
            return_value=("hello", '{"text":"hello"}'),
        ) as transcribe:
            output = node.transcribe(audio, "whisper-1", "json")

        wav_bytes = transcribe.call_args.args[0]
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertEqual(output, ("hello", '{"text":"hello"}'))

    def test_transcription_request_is_multipart_without_json_content_type(self):
        response = MagicMock()
        response.status_code = 200
        response.text = '{"text":"hello"}'
        response.json.return_value = {"text": "hello"}
        session = MagicMock()
        session.post.return_value = response
        config = {
            "base_url": nodes.DEFAULT_BASE_URL,
            "api_key": "test",
            "timeout": 60,
        }

        with patch.object(nodes, "_get_session", return_value=session):
            result = nodes.transcribe_audio(
                b"RIFFdata",
                "input.wav",
                "audio/wav",
                "whisper-1",
                "json",
                config,
            )

        self.assertEqual(result[0], "hello")
        kwargs = session.post.call_args.kwargs
        self.assertNotIn("Content-Type", kwargs["headers"])
        self.assertEqual(kwargs["data"], {"model": "whisper-1", "response_format": "json"})
        self.assertEqual(kwargs["files"]["file"], ("input.wav", b"RIFFdata", "audio/wav"))

    def test_transcription_rejects_invalid_json_for_json_format(self):
        response = MagicMock()
        response.status_code = 200
        response.text = "not-json"
        response.json.side_effect = ValueError("invalid")
        session = MagicMock()
        session.post.return_value = response
        config = {
            "base_url": nodes.DEFAULT_BASE_URL,
            "api_key": "test",
            "timeout": 60,
        }

        with patch.object(nodes, "_get_session", return_value=session):
            with self.assertRaises(nodes.SeedanceLowPriceError):
                nodes.transcribe_audio(
                    b"RIFFdata",
                    "input.wav",
                    "audio/wav",
                    "whisper-1",
                    "json",
                    config,
                )


class APIMartRegistrationAndWorkflowTests(unittest.TestCase):
    def test_registration_and_domestic_api_key_button(self):
        source = (ROOT / "Comfly.py").read_text(encoding="utf-8")
        frontend = (
            ROOT / "web" / "js" / "zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        for node_type in sorted(set(WORKFLOW_NODE_TYPES.values())):
            self.assertIn(f'"{node_type}": {node_type}', source)
            self.assertIn(node_type, frontend)
        self.assertIn("贞贞的平价AI小屋（国内版）ApiKey获取", frontend)
        self.assertIn("https://api.seedance.nz/sign-up?aff=5f4w", frontend)

    def test_all_workflows_have_empty_keys_and_valid_links(self):
        for filename, node_type in WORKFLOW_NODE_TYPES.items():
            with self.subTest(filename=filename):
                path = ROOT / "workflow" / filename
                self.assertTrue(path.is_file())
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("sk-", text)
                data = json.loads(text)
                settings = next(
                    node for node in data["nodes"] if node["type"] == "Comfly_api_set"
                )
                generator = next(
                    node for node in data["nodes"] if node["type"] == node_type
                )
                self.assertEqual(
                    settings["widgets_values"],
                    ["seedance_low_price", "", "", False],
                )
                self.assertEqual(generator["widgets_values"][-1], False)

                link_by_id = {link[0]: link for link in data["links"]}
                for node in data["nodes"]:
                    for item in node.get("inputs", []):
                        link_id = item.get("link")
                        if link_id is not None:
                            self.assertIn(link_id, link_by_id)
                            self.assertEqual(link_by_id[link_id][3], node["id"])
                    for output_index, output in enumerate(node.get("outputs", [])):
                        for link_id in output.get("links") or []:
                            self.assertIn(link_id, link_by_id)
                            self.assertEqual(
                                link_by_id[link_id][1:3],
                                [node["id"], output_index],
                            )

                config_link = next(
                    link
                    for link in data["links"]
                    if link[1] == settings["id"] and link[3] == generator["id"]
                )
                self.assertEqual(config_link[2], 1)
                self.assertEqual(config_link[5], nodes.CONFIG_TYPE)

    def test_mode_specific_workflows_use_expected_media_links(self):
        cases = {
            "zhenzhen-image-g-v2-lowprice图生图（贞贞的平价AI小屋）.json": 1,
            "zhenzhen-image-gk-v15图像编辑（贞贞的平价AI小屋）.json": 1,
            "zhenzhen-video-g-omni-flash视频编辑（贞贞的平价AI小屋）.json": 1,
            "zhenzhen-video-gk-v15图生视频（贞贞的平价AI小屋）.json": 1,
            "zhenzhen-video-v31-fast三图参考生视频（贞贞的平价AI小屋）.json": 3,
            "whisper-1语音转写（贞贞的平价AI小屋）.json": 1,
        }
        for filename, expected_media_links in cases.items():
            with self.subTest(filename=filename):
                data = json.loads((ROOT / "workflow" / filename).read_text("utf-8"))
                node_type = WORKFLOW_NODE_TYPES[filename]
                generator = next(
                    node for node in data["nodes"] if node["type"] == node_type
                )
                media_links = [
                    link
                    for link in data["links"]
                    if link[3] == generator["id"]
                    and link[5] in ("IMAGE", "VIDEO", "AUDIO")
                ]
                self.assertEqual(len(media_links), expected_media_links)


if __name__ == "__main__":
    unittest.main()
