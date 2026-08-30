import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


CONFIG = {"base_url": "https://example.test", "api_key": "test"}
IMAGE = torch.zeros((1, 8, 8, 3), dtype=torch.float32)


class Seedance25LowPriceContractTests(unittest.TestCase):
    def test_exact_model_catalog_and_material_capacity(self):
        self.assertEqual(nodes.SEEDANCE25_MODELS, [
            "seedance-2.5-standard-t2v",
            "seedance-2.5-standard-i2v",
            "seedance-2.5-standard-multi",
            "seedance-2.5-global-standard-t2v",
            "seedance-2.5-global-standard-i2v",
            "seedance-2.5-global-standard-multi",
        ])
        inputs = nodes.Comfly_seedance25_standard_low_price.INPUT_TYPES()
        self.assertEqual(inputs["required"]["seconds"][0], [
            "-1", *[str(value) for value in range(4, 31)],
        ])
        self.assertEqual(
            inputs["required"]["resolution"][0],
            ["480p", "720p", "1080p", "2k", "4k", "native1080p"],
        )
        optional = list(inputs["optional"])
        self.assertEqual(
            [name for name in optional if name.startswith("image")],
            [f"image{index}" for index in range(1, 31)],
        )
        self.assertEqual(
            [name for name in optional if name.startswith("video")],
            [f"video{index}" for index in range(1, 11)],
        )
        self.assertEqual(
            [name for name in optional if name.startswith("audio")],
            [f"audio{index}" for index in range(1, 11)],
        )

    def test_validation_matches_model_specific_contract(self):
        common = {"seconds": "4", "resolution": "480p", "ratio": "adaptive"}
        self.assertIs(
            nodes.Comfly_seedance25_standard_low_price.VALIDATE_INPUTS(
                model=nodes.SEEDANCE25_T2V_MODELS[0], prompt="valid prompt", **common
            ),
            True,
        )
        self.assertIn(
            "prompt is required",
            nodes.Comfly_seedance25_standard_low_price.VALIDATE_INPUTS(
                model=nodes.SEEDANCE25_MULTI_MODELS[0], prompt="", **common
            ),
        )
        self.assertIs(
            nodes.Comfly_seedance25_standard_low_price.VALIDATE_INPUTS(
                model=nodes.SEEDANCE25_I2V_MODELS[0], prompt="", **common
            ),
            True,
        )
        self.assertIn(
            "seconds must",
            nodes.Comfly_seedance25_standard_low_price.VALIDATE_INPUTS(
                model=nodes.SEEDANCE25_T2V_MODELS[0],
                prompt="valid",
                seconds="31",
                resolution="480p",
                ratio="adaptive",
            ),
        )
        self.assertIs(
            nodes.Comfly_seedance25_standard_low_price.VALIDATE_INPUTS(
                model=nodes.SEEDANCE25_T2V_MODELS[0],
                prompt="valid",
                seconds="4",
                resolution="native1080p",
                ratio="adaptive",
            ),
            True,
        )

    def test_native1080p_is_forwarded_for_all_six_models(self):
        for model in nodes.SEEDANCE25_MODELS:
            with self.subTest(model=model):
                media = {}
                prompt = "valid prompt"
                if model in nodes.SEEDANCE25_I2V_MODELS:
                    media = {"images": ["https://cdn.test/frame.png"]}
                    prompt = ""
                elif model in nodes.SEEDANCE25_MULTI_MODELS:
                    media = {
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "https://cdn.test/ref.png"},
                            }
                        ]
                    }
                payload = nodes.Comfly_seedance25_standard_low_price.build_payload({
                    "model": model,
                    "prompt": prompt,
                    "seconds": "4",
                    "resolution": "native1080p",
                    "ratio": "adaptive",
                    "seed": -1,
                }, media)
                self.assertEqual(
                    payload["metadata"]["resolution"], "native1080p"
                )

    def test_t2v_and_smart_duration_payloads(self):
        fixed = nodes.Comfly_seedance25_standard_low_price.build_payload({
            "model": nodes.SEEDANCE25_T2V_MODELS[0],
            "prompt": "a paper boat crossing a quiet pond",
            "seconds": "4",
            "resolution": "480p",
            "ratio": "16:9",
            "generate_audio": True,
            "return_last_frame": False,
            "seed": 7,
        }, {})
        self.assertEqual(fixed, {
            "model": nodes.SEEDANCE25_T2V_MODELS[0],
            "prompt": "a paper boat crossing a quiet pond",
            "seconds": "4",
            "metadata": {
                "resolution": "480p",
                "ratio": "16:9",
                "generate_audio": True,
                "seed": 7,
            },
        })
        smart = nodes.Comfly_seedance25_standard_low_price.build_payload({
            "model": nodes.SEEDANCE25_T2V_MODELS[1],
            "prompt": "a quiet studio product reveal",
            "seconds": "-1",
            "resolution": "720p",
            "ratio": "16:9",
            "generate_audio": False,
            "return_last_frame": True,
            "seed": -1,
        }, {})
        self.assertNotIn("seconds", smart)
        self.assertEqual(smart["metadata"]["duration"], -1)
        self.assertNotIn("seed", smart["metadata"])

    def test_i2v_payload_uses_top_level_first_and_last_frames(self):
        payload = nodes.Comfly_seedance25_standard_low_price.build_payload({
            "model": nodes.SEEDANCE25_I2V_MODELS[0],
            "prompt": "",
            "seconds": "4",
            "resolution": "480p",
            "ratio": "adaptive",
            "seed": -1,
        }, {"images": ["https://cdn.test/first.png", "https://cdn.test/last.png"]})
        self.assertEqual(payload["images"], [
            "https://cdn.test/first.png", "https://cdn.test/last.png",
        ])
        self.assertEqual(payload["metadata"]["ratio"], "adaptive")
        self.assertNotIn("prompt", payload)
        self.assertNotIn("content", payload["metadata"])

    def test_multi_collect_and_payload_use_only_metadata_content(self):
        with (
            patch.object(nodes, "image_to_png_bytes", return_value=b"image"),
            patch.object(nodes, "video_to_mp4_bytes", return_value=b"video"),
            patch.object(nodes, "audio_to_wav_bytes", return_value=b"audio"),
            patch.object(nodes, "_seedance25_video_duration_seconds", return_value=3.0),
            patch.object(nodes, "_seedance25_audio_duration_seconds", return_value=3.0),
            patch.object(nodes, "upload_media", side_effect=[
                "https://cdn.test/image.png",
                "https://cdn.test/video.mp4",
                "https://cdn.test/audio.wav",
            ]),
        ):
            media = nodes.Comfly_seedance25_standard_low_price().collect_media({
                "model": nodes.SEEDANCE25_MULTI_MODELS[1],
                "image1": IMAGE,
                "video1": object(),
                "audio1": {
                    "waveform": torch.zeros((1, 1, 144000)),
                    "sample_rate": 48000,
                },
            }, CONFIG)
        payload = nodes.Comfly_seedance25_standard_low_price.build_payload({
            "model": nodes.SEEDANCE25_MULTI_MODELS[1],
            "prompt": "match @Image 1, @Video 1 and @Audio 1",
            "seconds": "4",
            "resolution": "480p",
            "ratio": "16:9",
            "seed": -1,
        }, media)
        self.assertEqual(payload["metadata"]["content"], [
            {"type": "image_url", "image_url": {"url": "https://cdn.test/image.png"}},
            {"type": "video_url", "video_url": {"url": "https://cdn.test/video.mp4"}},
            {"type": "audio_url", "audio_url": {"url": "https://cdn.test/audio.wav"}},
        ])
        self.assertNotIn("images", payload)

    def test_multi_collect_supports_all_fifty_documented_reference_slots(self):
        kwargs = {
            "model": nodes.SEEDANCE25_MULTI_MODELS[0],
            **{f"image{index}": IMAGE for index in range(1, 31)},
            **{f"video{index}": object() for index in range(1, 11)},
            **{
                f"audio{index}": {
                    "waveform": torch.zeros((1, 1, 9600)),
                    "sample_rate": 48000,
                }
                for index in range(1, 11)
            },
        }
        uploaded_urls = [f"https://cdn.test/reference-{index}" for index in range(50)]
        with (
            patch.object(nodes, "image_to_png_bytes", return_value=b"image"),
            patch.object(nodes, "video_to_mp4_bytes", return_value=b"video"),
            patch.object(nodes, "audio_to_wav_bytes", return_value=b"audio"),
            patch.object(nodes, "_validate_seedance25_media_durations"),
            patch.object(nodes, "upload_media", side_effect=uploaded_urls) as upload,
        ):
            media = nodes.Comfly_seedance25_standard_low_price().collect_media(kwargs, CONFIG)
        self.assertEqual(upload.call_count, 50)
        self.assertEqual(len(media["content"]), 50)
        self.assertEqual(
            [item["type"] for item in media["content"]],
            ["image_url"] * 30 + ["video_url"] * 10 + ["audio_url"] * 10,
        )

    def test_multi_rejects_invalid_or_excessive_reference_duration_before_upload(self):
        node = nodes.Comfly_seedance25_standard_low_price()
        valid_audio = {
            "waveform": torch.zeros((1, 1, 144000)),
            "sample_rate": 48000,
        }
        with (
            patch.object(nodes, "_seedance25_video_duration_seconds", return_value=1.5),
            patch.object(nodes, "upload_media") as upload,
        ):
            with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "between 2 and 30"):
                node.collect_media({
                    "model": nodes.SEEDANCE25_MULTI_MODELS[0],
                    "video1": object(),
                }, CONFIG)
            upload.assert_not_called()

        with (
            patch.object(nodes, "_seedance25_video_duration_seconds", return_value=20.0),
            patch.object(nodes, "_seedance25_audio_duration_seconds", return_value=11.0),
            patch.object(nodes, "upload_media") as upload,
        ):
            with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "must not exceed 30"):
                node.collect_media({
                    "model": nodes.SEEDANCE25_MULTI_MODELS[0],
                    "video1": object(),
                    "audio1": valid_audio,
                }, CONFIG)
            upload.assert_not_called()

    def test_runtime_requires_i2v_and_multi_materials(self):
        node = nodes.Comfly_seedance25_standard_low_price()
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "image1 is required"):
            node.collect_media({"model": nodes.SEEDANCE25_I2V_MODELS[0]}, CONFIG)
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "at least one"):
            node.collect_media({"model": nodes.SEEDANCE25_MULTI_MODELS[0]}, CONFIG)

    def test_generate_executes_upload_submit_poll_and_download(self):
        final = {"status": "completed", "metadata": {"url": "https://cdn.test/result.mp4"}}
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(nodes, "image_to_png_bytes", return_value=b"png"),
            patch.object(nodes, "upload_media", return_value="https://cdn.test/first.png"),
            patch.object(nodes, "submit_task", return_value=("safe-task", {"id": "safe-task"})) as submit,
            patch.object(nodes, "poll_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_seedance25_standard_low_price().generate(
                model=nodes.SEEDANCE25_I2V_MODELS[0],
                prompt="keep the subject consistent",
                seconds="4",
                resolution="480p",
                ratio="16:9",
                image1=IMAGE,
            )
        self.assertEqual(result[0], "downloaded-video")
        self.assertEqual(submit.call_args.args[0]["images"], ["https://cdn.test/first.png"])

    def test_video_download_uses_part_file_and_atomic_completion(self):
        class FakeResponse:
            def __init__(self):
                self.closed = False

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                self.asserted_chunk_size = chunk_size
                yield b"valid-mp4"

            def close(self):
                self.closed = True

        response = FakeResponse()
        get_calls = []

        class FakeSession:
            def get(self, *args, **kwargs):
                get_calls.append((args, kwargs))
                return response

        session = FakeSession()
        with tempfile.TemporaryDirectory() as output_dir:
            with (
                patch.dict(os.environ, {"SEEDANCE_OUTPUT_DIR": output_dir}),
                patch.object(nodes, "_get_session", return_value=session),
                patch.object(nodes, "_video_from_path", side_effect=lambda path: path),
            ):
                path = nodes.download_video("https://cdn.test/result.mp4")
                self.assertTrue(Path(path).is_file())
                self.assertEqual(Path(path).read_bytes(), b"valid-mp4")
                self.assertFalse(Path(f"{path}.part").exists())
        self.assertTrue(response.closed)
        self.assertEqual(get_calls[0][1]["timeout"], (120.0, 120.0))

    def test_video_download_bypasses_broken_environment_proxy(self):
        class FakeResponse:
            def __init__(self):
                self.closed = False

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield b"valid-mp4"

            def close(self):
                self.closed = True

        class BrokenProxySession:
            def get(self, *_args, **_kwargs):
                raise nodes.requests.exceptions.ConnectionError("broken proxy")

        response = FakeResponse()
        with tempfile.TemporaryDirectory() as output_dir:
            with (
                patch.dict(os.environ, {"SEEDANCE_OUTPUT_DIR": output_dir}),
                patch.object(
                    nodes, "_get_session", return_value=BrokenProxySession()
                ),
                patch.object(
                    nodes, "direct_media_get", return_value=response
                ) as direct_get,
                patch.object(nodes, "_video_from_path", side_effect=lambda path: path),
            ):
                path = nodes.download_video("https://cdn.test/result.mp4")
                downloaded = Path(path).read_bytes()

        self.assertEqual(downloaded, b"valid-mp4")
        self.assertTrue(response.closed)
        direct_get.assert_called_once()
        self.assertEqual(
            direct_get.call_args.kwargs["timeout"], (120.0, 120.0)
        )

    def test_video_stream_ssl_failure_switches_to_direct_route(self):
        class BrokenStreamResponse:
            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                raise nodes.requests.exceptions.SSLError("stream TLS EOF")
                yield b""

            def close(self):
                return None

        class ValidResponse:
            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield b"valid-mp4"

            def close(self):
                return None

        class NormalSession:
            def get(self, *_args, **_kwargs):
                return BrokenStreamResponse()

        with tempfile.TemporaryDirectory() as output_dir:
            with (
                patch.dict(os.environ, {"SEEDANCE_OUTPUT_DIR": output_dir}),
                patch.object(nodes, "_get_session", return_value=NormalSession()),
                patch.object(
                    nodes, "direct_media_get", return_value=ValidResponse()
                ) as direct_get,
                patch.object(nodes.time, "sleep"),
                patch.object(nodes, "_video_from_path", side_effect=lambda path: path),
            ):
                path = nodes.download_video(
                    "https://cdn.test/result.mp4", max_retries=2
                )
                downloaded = Path(path).read_bytes()

        self.assertEqual(downloaded, b"valid-mp4")
        direct_get.assert_called_once()

    def test_video_download_error_does_not_expose_result_url(self):
        private_marker = "opaque-private-result-marker"

        class BrokenSession:
            def get(self, *_args, **_kwargs):
                raise nodes.requests.exceptions.SSLError(private_marker)

        with tempfile.TemporaryDirectory() as output_dir:
            with (
                patch.dict(os.environ, {"SEEDANCE_OUTPUT_DIR": output_dir}),
                patch.object(nodes, "_get_session", return_value=BrokenSession()),
                patch.object(nodes, "direct_media_get", side_effect=BrokenSession().get),
                patch.object(nodes.time, "sleep"),
            ):
                with self.assertRaises(RuntimeError) as context:
                    nodes.download_video(
                        f"https://cdn.test/{private_marker}.mp4", max_retries=2
                    )

        self.assertNotIn(private_marker, str(context.exception))
        self.assertIn("SSLError", str(context.exception))


class Seedance25LowPriceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.paths = sorted((PLUGIN_ROOT / "workflow").glob(
            "zhenzhen-seedance-2.5-*（贞贞的平价AI小屋）.json"
        ))

    def test_workflows_cover_six_models_without_runtime_secrets(self):
        self.assertEqual(len(self.paths), 6)
        covered = set()
        for path in self.paths:
            raw = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw))
            workflow = json.loads(raw)
            settings = next(node for node in workflow["nodes"] if node["type"] == "T8Zhenzhen_API_Settings")
            self.assertEqual(settings["widgets_values"], ["seedance_low_price", "", "", False])
            node = next(node for node in workflow["nodes"] if node["type"] == nodes.Comfly_seedance25_standard_low_price.__name__)
            covered.add(node["widgets_values"][0])
            expected_ratio = "adaptive" if node["widgets_values"][0].endswith("-i2v") else "16:9"
            self.assertEqual(node["widgets_values"][2:5], ["4", "480p", expected_ratio])
            self.assertEqual(len(node["inputs"]), 51)
            self.assertIsNotNone(next(value for value in node["inputs"] if value["name"] == "api_config")["link"])
        self.assertEqual(covered, set(nodes.SEEDANCE25_MODELS))

    def test_examples_connect_mode_specific_materials(self):
        for path in self.paths:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            node = next(node for node in workflow["nodes"] if node["type"] == nodes.Comfly_seedance25_standard_low_price.__name__)
            model = node["widgets_values"][0]
            connected = [value["name"] for value in node["inputs"] if value["link"] is not None]
            if model.endswith("-i2v"):
                self.assertEqual(connected, ["api_config", "image1", "image2"])
            elif model.endswith("-multi"):
                self.assertEqual(connected, ["api_config", "image1", "video1", "audio1"])
            else:
                self.assertEqual(connected, ["api_config"])

    def test_registration_dynamic_ui_and_api_key_link(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        dynamic_ui = (PLUGIN_ROOT / "web/js/seedance25_lowprice_ui.js").read_text(encoding="utf-8")
        api_link = (PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js").read_text(encoding="utf-8")
        self.assertIn('"Comfly_seedance25_standard_low_price"', comfly)
        self.assertIn(
            '"Comfly_seedance25_standard_low_price": "zhenzhen-seedance2.5-standard-low-price"',
            comfly,
        )
        self.assertIn('const NODE_NAME = "Comfly_seedance25_standard_low_price"', dynamic_ui)
        self.assertIn("const MEDIA_LIMITS = { image: 30, video: 10, audio: 10 }", dynamic_ui)
        self.assertIn('widgetByName(node, "ratio")', dynamic_ui)
        self.assertIn("function nextVisibleSlots(node)", dynamic_ui)
        self.assertIn("media.index <= nextVisible[media.family]", dynamic_ui)
        self.assertIn('"Comfly_seedance25_standard_low_price"', api_link)


if __name__ == "__main__":
    unittest.main()
