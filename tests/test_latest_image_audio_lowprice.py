import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import latest_image_audio_low_price_nodes as latest
import seedance_low_price_nodes as lowprice
from generate_latest_image_audio_workflows import SOURCE_FILES, target_filename


CONFIG = {"base_url": "https://example.test", "api_key": "test-key"}
IMAGE = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
AUDIO = {"waveform": torch.zeros((1, 1, 100)), "sample_rate": 24000}


class LatestImageNodeTests(unittest.TestCase):
    def test_gk_v2_contract_and_execution(self):
        node = latest.Comfly_zhenzhen_image_gk_v2_lowprice()
        self.assertEqual(latest.ZHENZHEN_IMAGE_GK_V2_MODEL, "zhenzhen-image-gk-v2")
        self.assertEqual(
            node._build_payload("clean studio portrait", "16:9", 2),
            {
                "model": "zhenzhen-image-gk-v2",
                "prompt": "clean studio portrait",
                "size": "16:9",
                "n": 2,
            },
        )
        final = {
            "data": {
                "status": "SUCCESS",
                "result_url": "https://result.test/a.png",
            }
        }
        with patch.object(latest, "resolve_config", return_value=CONFIG), patch.object(
            latest,
            "submit_image_task",
            return_value=("task-test", {"id": "task-test"}),
        ) as submit, patch.object(
            latest, "poll_image_task", return_value=final
        ), patch.object(
            latest, "extract_image_url", return_value="https://result.test/a.png"
        ), patch.object(
            latest, "download_image", return_value=IMAGE
        ):
            result = node.generate(
                prompt="clean studio portrait", size="1:1", n=1
            )
        self.assertEqual(submit.call_args.args[0]["model"], "zhenzhen-image-gk-v2")
        self.assertTrue(torch.equal(result[0], IMAGE))

    def test_gk_v2_current_size_and_count_contract(self):
        inputs = latest.Comfly_zhenzhen_image_gk_v2_lowprice.INPUT_TYPES()["required"]
        self.assertEqual(
            inputs["size"][0],
            ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"],
        )
        self.assertEqual(inputs["n"][1]["max"], 12)

    def test_gk_v2_edit_contract_and_execution(self):
        node = latest.Comfly_zhenzhen_image_gk_v2_edit_lowprice()
        urls = ["https://media.test/one.png", "https://media.test/two.png"]
        self.assertEqual(
            node._build_payload(
                "turn this into a watercolor poster",
                urls,
                "auto",
                "1k",
                1,
                False,
            ),
            {
                "model": "zhenzhen-image-gk-v2-edit",
                "prompt": "turn this into a watercolor poster",
                "images": urls,
                "n": 1,
                "aspect_ratio": "auto",
                "resolution": "1k",
                "nsfw_check": False,
            },
        )

        final = {
            "data": {
                "status": "SUCCESS",
                "result_url": "https://result.test/a.png",
            }
        }
        with patch.object(latest, "resolve_config", return_value=CONFIG), patch.object(
            latest, "upload_media", side_effect=urls
        ) as upload, patch.object(
            latest,
            "submit_image_task",
            return_value=("task-test", {"id": "task-test"}),
        ) as submit, patch.object(
            latest, "poll_image_task", return_value=final
        ), patch.object(
            latest, "extract_image_url", return_value="https://result.test/a.png"
        ), patch.object(
            latest, "download_image", return_value=IMAGE
        ):
            result = node.generate(
                prompt="turn this into a watercolor poster",
                aspect_ratio="auto",
                resolution="1k",
                n=1,
                nsfw_check=False,
                image1=IMAGE,
                image3=IMAGE,
            )
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(submit.call_args.args[0]["images"], urls)
        self.assertNotIn("quality", submit.call_args.args[0])
        self.assertTrue(torch.equal(result[0], IMAGE))

    def test_gk_v2_edit_requires_one_to_three_images_at_runtime(self):
        result = latest.Comfly_zhenzhen_image_gk_v2_edit_lowprice.VALIDATE_INPUTS(
            prompt="edit this",
            aspect_ratio="auto",
            resolution="1k",
            n=1,
            strict=True,
        )
        self.assertIn("1-3", result)

    def test_wan_contract_separates_t2i_and_i2i(self):
        node = latest.Comfly_wan_2_7_global_image_lowprice()
        self.assertEqual(
            latest.WAN27_GLOBAL_IMAGE_MODELS,
            [
                "wan-2.7-global-t2i",
                "wan-2.7-global-i2i",
                "wan-2.7-global-i2i-pro",
            ],
        )
        t2i = node._build_payload(
            latest.WAN27_GLOBAL_T2I_MODEL,
            "minimal product photo",
            1024,
            1536,
            True,
            [],
        )
        self.assertEqual(
            t2i["metadata"],
            {"width": 1024, "height": 1536, "thinking_mode": True},
        )
        self.assertNotIn("images", t2i)

        urls = [f"https://media.test/{index}.png" for index in range(1, 10)]
        i2i = node._build_payload(
            latest.WAN27_GLOBAL_I2I_PRO_MODEL,
            "edit all references",
            1024,
            1024,
            False,
            urls,
        )
        self.assertEqual(i2i["images"], urls)
        self.assertNotIn("metadata", i2i)

    def test_wan_i2i_uploads_connected_slots_in_order(self):
        final = {
            "data": {
                "status": "SUCCESS",
                "result_url": "https://result.test/a.png",
            }
        }
        with patch.object(latest, "resolve_config", return_value=CONFIG), patch.object(
            latest,
            "upload_media",
            side_effect=["https://media.test/1.png", "https://media.test/3.png"],
        ) as upload, patch.object(
            latest,
            "submit_image_task",
            return_value=("task-test", {"id": "task-test"}),
        ) as submit, patch.object(
            latest, "poll_image_task", return_value=final
        ), patch.object(
            latest, "extract_image_url", return_value="https://result.test/a.png"
        ), patch.object(
            latest, "download_image", return_value=IMAGE
        ):
            latest.Comfly_wan_2_7_global_image_lowprice().generate(
                model=latest.WAN27_GLOBAL_I2I_MODEL,
                prompt="edit these references",
                width=1024,
                height=1024,
                thinking_mode=True,
                image1=IMAGE,
                image3=IMAGE,
            )
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(
            submit.call_args.args[0]["images"],
            ["https://media.test/1.png", "https://media.test/3.png"],
        )


class LatestAudioNodeTests(unittest.TestCase):
    def test_audio_url_list_prefers_and_preserves_documented_array(self):
        response = {
            "data": {
                "result_url": "https://result.test/primary.mp3",
                "data": {
                    "content": {
                        "audio_urls": [
                            "https://result.test/one.mp3",
                            "https://result.test/two.mp3",
                            "https://result.test/two.mp3",
                        ]
                    }
                },
            }
        }
        self.assertEqual(
            lowprice.extract_audio_urls(response),
            [
                "https://result.test/one.mp3",
                "https://result.test/two.mp3",
                "https://result.test/two.mp3",
            ],
        )
        self.assertEqual(
            lowprice.extract_audio_url(response), "https://result.test/one.mp3"
        )

    def test_compressed_audio_uses_ffmpeg_fallback_and_cleans_temp_file(self):
        class BrokenTorchaudio:
            @staticmethod
            def load(*args, **kwargs):
                raise RuntimeError("no audio backend")

        decoded = {
            "waveform": torch.ones((1, 1, 32000), dtype=torch.float32),
            "sample_rate": 32000,
        }
        decoded_path = ""

        def fake_decode(path):
            nonlocal decoded_path
            decoded_path = path
            self.assertTrue(Path(path).is_file())
            return decoded

        with patch.dict(sys.modules, {"torchaudio": BrokenTorchaudio}), patch.object(
            lowprice, "_decode_suno_audio", side_effect=fake_decode
        ) as fallback:
            result = lowprice.audio_bytes_to_comfy(b"ID3-test", "mp3", 32000)

        self.assertIs(result, decoded)
        fallback.assert_called_once()
        self.assertFalse(Path(decoded_path).exists())

    def test_qwen_tts_payload_is_model_aware(self):
        node = latest.Comfly_qwen3_tts_lowprice()
        flash = node._build_payload(
            latest.QWEN3_TTS_FLASH_MODEL,
            "你好，世界。",
            "Cherry",
            "Chinese",
            "快速而自然",
            True,
        )
        self.assertEqual(
            flash["metadata"], {"voice": "Cherry", "language_type": "Chinese"}
        )
        instruct = node._build_payload(
            latest.QWEN3_TTS_INSTRUCT_FLASH_MODEL,
            "你好，世界。",
            "Cherry",
            "Chinese",
            "快速而自然",
            True,
        )
        self.assertEqual(instruct["metadata"]["instructions"], "快速而自然")
        self.assertTrue(instruct["metadata"]["optimize_instructions"])

    def test_minimax_payloads_use_confirmed_gateway_types(self):
        node = latest.Comfly_minimax_audio_lowprice()
        common = {
            "prompt": "soft ambient piano",
            "lyrics": "",
            "is_instrumental": True,
            "lyrics_optimizer": False,
            "voice_id": "Wise_Woman",
            "speed": 1.0,
            "volume": 1.0,
            "pitch": 0,
            "language_boost": "auto",
            "output_format": "mp3",
            "sample_rate": "32000",
            "bitrate": "128000",
            "channel": "1",
            "custom_voice_id": "SeedanceVoice01",
            "clone_target_model": latest.MINIMAX_SPEECH_HD_MODEL,
            "need_noise_reduction": False,
            "need_volume_normalization": False,
        }
        music = node._build_payload({**common, "model": latest.MINIMAX_MUSIC_MODEL})
        self.assertIs(music["metadata"]["is_instrumental"], True)
        self.assertEqual(music["metadata"]["sample_rate"], "32000")
        self.assertEqual(music["metadata"]["bitrate"], "128000")
        self.assertNotIn("lyrics", music["metadata"])

        speech = node._build_payload(
            {**common, "model": latest.MINIMAX_SPEECH_HD_MODEL}
        )
        self.assertEqual(speech["metadata"]["voice_id"], "Wise_Woman")
        self.assertEqual(speech["metadata"]["vol"], 1.0)
        self.assertEqual(speech["metadata"]["channel"], 1)

        clone = node._build_payload(
            {**common, "model": latest.MINIMAX_VOICE_CLONE_MODEL},
            "https://media.test/voice.wav",
        )
        self.assertEqual(
            clone["metadata"]["audio_url"], "https://media.test/voice.wav"
        )
        self.assertEqual(clone["metadata"]["custom_voice_id"], "SeedanceVoice01")

    def test_mureka_downloads_every_ordered_result(self):
        final = {
            "data": {
                "status": "SUCCESS",
                "data": {"content": {"audio_urls": ["u1", "u2"]}},
            }
        }
        with patch.object(latest, "resolve_config", return_value=CONFIG), patch.object(
            latest,
            "submit_audio_task",
            return_value=("task-test", {"id": "task-test"}),
        ) as submit, patch.object(
            latest, "poll_audio_task", return_value=final
        ), patch.object(
            latest, "extract_audio_urls", return_value=["u1", "u2"]
        ), patch.object(
            latest, "download_audio", side_effect=[AUDIO, AUDIO]
        ) as download:
            result = latest.Comfly_mureka_bgm_lowprice().generate(
                model="mureka-v9-bgm",
                prompt="calm acoustic background music",
                instrumental_id="",
                n=2,
            )
        self.assertEqual(
            submit.call_args.args[0],
            {
                "model": "mureka-v9-bgm",
                "prompt": "calm acoustic background music",
                "metadata": {"n": 2, "stream": False},
            },
        )
        self.assertEqual(download.call_count, 2)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(json.loads(result[1]), ["u1", "u2"])


class LatestModelRegistrationTests(unittest.TestCase):
    def test_nodes_and_image_concurrent_wrappers_are_declared(self):
        comfly_source = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        concurrent_source = (PLUGIN_ROOT / "ComflyConcurrent.py").read_text(
            encoding="utf-8"
        )
        for key in (
            "Comfly_zhenzhen_image_gk_v2_lowprice",
            "Comfly_zhenzhen_image_gk_v2_edit_lowprice",
            "Comfly_wan_2_7_global_image_lowprice",
            "Comfly_qwen3_tts_lowprice",
            "Comfly_minimax_audio_lowprice",
            "Comfly_mureka_bgm_lowprice",
        ):
            self.assertIn(f'"{key}": {key}', comfly_source)
        self.assertIn('"latest_image_audio_low_price_nodes"', concurrent_source)
        self.assertTrue(latest.Comfly_mureka_bgm_lowprice.COMFLY_CONCURRENT_DISABLED)

    def test_dynamic_frontend_covers_model_specific_controls(self):
        source = (PLUGIN_ROOT / "web" / "js" / "latest_image_audio_ui.js").read_text(
            encoding="utf-8"
        )
        for fragment in (
            'const WAN_NODE_NAME = "Comfly_wan_2_7_global_image_lowprice"',
            'const QWEN_TTS_NODE_NAME = "Comfly_qwen3_tts_lowprice"',
            'const MINIMAX_AUDIO_NODE_NAME = "Comfly_minimax_audio_lowprice"',
            'model.endsWith("-t2i")',
            'model === "qwen3-tts-instruct-flash"',
            'model === "minimax-voice-clone"',
            'setZhenzhenInputVisible(node, input, model === "minimax-voice-clone")',
            'from "./dynamic_widget_ui.js"',
            "originalNodeName(nodeData.name)",
        ):
            self.assertIn(fragment, source)

    def test_every_new_model_has_a_safe_example_workflow(self):
        expected = {
            latest.ZHENZHEN_IMAGE_GK_V2_MODEL,
            latest.ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL,
            *latest.WAN27_GLOBAL_IMAGE_MODELS,
            *latest.QWEN3_TTS_MODELS,
            *latest.MINIMAX_AUDIO_MODELS,
            *latest.MUREKA_BGM_MODELS,
        }
        node_types = {
            "Comfly_zhenzhen_image_gk_v2_lowprice",
            "Comfly_zhenzhen_image_gk_v2_edit_lowprice",
            "Comfly_wan_2_7_global_image_lowprice",
            "Comfly_qwen3_tts_lowprice",
            "Comfly_minimax_audio_lowprice",
            "Comfly_mureka_bgm_lowprice",
        }
        found = {}
        for source_name in SOURCE_FILES:
            path = PLUGIN_ROOT / "workflow" / target_filename(source_name)
            workflow = json.loads(path.read_text(encoding="utf-8"))
            for node in workflow.get("nodes", []):
                if node.get("type") not in node_types:
                    continue
                model = (
                    latest.ZHENZHEN_IMAGE_GK_V2_MODEL
                    if node["type"] == "Comfly_zhenzhen_image_gk_v2_lowprice"
                    else (
                        latest.ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL
                        if node["type"] == "Comfly_zhenzhen_image_gk_v2_edit_lowprice"
                        else node["widgets_values"][0]
                    )
                )
                found[model] = (path, workflow, node)

        self.assertEqual(set(found), expected)
        for model, (path, workflow, node) in found.items():
            with self.subTest(model=model, workflow=path.name):
                config = next(
                    item
                    for item in workflow["nodes"]
                    if item["type"] == "Comfly_seedance2_low_price_settings"
                )
                self.assertEqual(config["widgets_values"][1], "")
                raw = path.read_text(encoding="utf-8")
                self.assertNotRegex(raw, r"sk-[A-Za-z0-9_-]{12,}")
                self.assertNotRegex(raw, r'"task_[A-Za-z0-9_-]{6,}"')
                if model in latest.WAN27_GLOBAL_I2I_MODELS:
                    incoming = [
                        link
                        for link in workflow["links"]
                        if link[3] == node["id"] and link[5] == "IMAGE"
                    ]
                    self.assertEqual(len(incoming), 1)
                if model == latest.ZHENZHEN_IMAGE_GK_V2_EDIT_MODEL:
                    incoming = [
                        link
                        for link in workflow["links"]
                        if link[3] == node["id"] and link[5] == "IMAGE"
                    ]
                    self.assertEqual(len(incoming), 1)
                if model == latest.MINIMAX_VOICE_CLONE_MODEL:
                    incoming = [
                        link
                        for link in workflow["links"]
                        if link[3] == node["id"] and str(link[5]) == "AUDIO"
                    ]
                    self.assertEqual(len(incoming), 1)


if __name__ == "__main__":
    unittest.main()
