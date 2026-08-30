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


IMAGE = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
AUDIO = {
    "waveform": torch.zeros((1, 1, 1600), dtype=torch.float32),
    "sample_rate": 16000,
}
CONFIG = {"base_url": "https://api.seedance.nz", "api_key": "test-key"}


class QwenImage30ContractTests(unittest.TestCase):
    def test_exact_model_catalog_and_inputs(self):
        self.assertEqual(
            nodes.QWEN_IMAGE_30_MODELS,
            [
                "qwen-image-3.0-t2i",
                "qwen-image-3.0-i2i",
                "qwen-image-3.0-pro-t2i",
                "qwen-image-3.0-pro-i2i",
                "qwen-image-3.0-global-t2i",
                "qwen-image-3.0-global-i2i",
                "qwen-image-3.0-global-pro-t2i",
                "qwen-image-3.0-global-pro-i2i",
            ],
        )
        inputs = nodes.Comfly_qwen_image_3_0_lowprice.INPUT_TYPES()
        self.assertEqual(inputs["required"]["model"][0], nodes.QWEN_IMAGE_30_MODELS)
        self.assertEqual(inputs["required"]["sizing_mode"][0], ["auto", "ratio", "custom_size"])
        self.assertEqual(inputs["required"]["resolution"][0], ["1k", "2k"])
        self.assertEqual(inputs["optional"]["api_config"][0], nodes.CONFIG_TYPE)
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("image")],
            ["image1", "image2", "image3"],
        )

    def test_model_aware_validation(self):
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "prompt is required"):
            nodes.validate_qwen_image_30_inputs(
                nodes.QWEN_IMAGE_30_T2I_MODEL,
                "",
                "auto",
                "1k",
                "1:1",
                "1024*1024",
                1,
                -1,
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "requires 1 to 3 images"):
            nodes.validate_qwen_image_30_inputs(
                nodes.QWEN_IMAGE_30_I2I_MODEL,
                "edit this reference image",
                "auto",
                "1k",
                "1:1",
                "1024*1024",
                1,
                -1,
            )
        self.assertEqual(
            nodes.validate_qwen_image_30_inputs(
                nodes.QWEN_IMAGE_30_I2I_MODEL,
                "edit this reference image",
                "ratio",
                "2k",
                "16:9",
                "1024*1024",
                1,
                7,
                image_count=3,
            ),
            "edit this reference image",
        )

    def test_sizing_modes_are_mutually_exclusive(self):
        common = (
            nodes.QWEN_IMAGE_30_T2I_MODEL,
            "a clear studio product photograph",
            "blur",
            True,
        )
        auto = nodes.build_qwen_image_30_payload(
            *common, "auto", "2k", "16:9", "1024*1536", 2, 9
        )
        self.assertNotIn("size", auto)
        self.assertEqual(auto["metadata"], {"seed": 9})

        ratio = nodes.build_qwen_image_30_payload(
            *common, "ratio", "2k", "16:9", "1024*1536", 2, 9
        )
        self.assertNotIn("size", ratio)
        self.assertEqual(
            ratio["metadata"],
            {"seed": 9, "ratio": "16:9", "resolution": "2k"},
        )

        custom = nodes.build_qwen_image_30_payload(
            *common, "custom_size", "2k", "16:9", "1024x1536", 2, 9
        )
        self.assertEqual(custom["size"], "1024*1536")
        self.assertEqual(custom["metadata"], {"seed": 9})

    def test_i2i_payload_forwards_one_to_three_images(self):
        payload = nodes.build_qwen_image_30_payload(
            nodes.QWEN_IMAGE_30_GLOBAL_PRO_I2I_MODEL,
            "edit these reference images",
            "",
            False,
            "auto",
            "1k",
            "1:1",
            "1024*1024",
            1,
            -1,
            ["https://example.test/1.png", "https://example.test/2.png"],
        )
        self.assertEqual(
            payload["images"],
            ["https://example.test/1.png", "https://example.test/2.png"],
        )
        self.assertNotIn("metadata", payload)
        self.assertNotIn("size", payload)

    def test_execution_uses_image_flow_and_uploads_only_for_i2i(self):
        final = {
            "data": {
                "status": "SUCCESS",
                "result_url": "https://example.test/result.png",
            }
        }
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(
                nodes,
                "_upload_image_slots",
                return_value=["https://example.test/reference.png"],
            ) as upload,
            patch.object(
                nodes,
                "submit_image_task",
                return_value=("safe-task", {"id": "safe-task"}),
            ) as submit,
            patch.object(nodes, "poll_image_task", return_value=final),
            patch.object(nodes, "download_image", return_value=IMAGE),
        ):
            result = nodes.Comfly_qwen_image_3_0_lowprice().generate_image(
                model=nodes.QWEN_IMAGE_30_I2I_MODEL,
                prompt="edit the reference into a clean portrait",
                negative_prompt="",
                prompt_extend=True,
                sizing_mode="ratio",
                resolution="1k",
                ratio="1:1",
                custom_size="1024*1024",
                n=1,
                seed=-1,
                image1=IMAGE,
            )
        upload.assert_called_once()
        self.assertEqual(submit.call_args.args[0]["images"], ["https://example.test/reference.png"])
        self.assertIs(result[0], IMAGE)


class MinimaxH3OWContractTests(unittest.TestCase):
    def test_exact_model_catalog_and_controls(self):
        self.assertEqual(
            nodes.MINIMAX_H3_OW_MODELS,
            [
                "minimax-h3-ow-t2v",
                "minimax-h3-ow-r2v",
                "minimax-h3-ow-i2v",
            ],
        )
        inputs = nodes.Comfly_minimax_h3_ow_video_lowprice.INPUT_TYPES()
        self.assertEqual(inputs["required"]["seconds"][0], ["5", "10", "15"])
        self.assertEqual(inputs["required"]["resolution"][0], ["480p", "720p"])
        self.assertEqual(inputs["required"]["ratio"][0], nodes.MINIMAX_H3_OW_RATIOS)
        self.assertEqual(inputs["optional"]["api_config"][0], nodes.CONFIG_TYPE)

    def test_model_aware_validation_and_payloads(self):
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "require a prompt"):
            nodes.build_minimax_h3_ow_payload(
                nodes.MINIMAX_H3_OW_T2V_MODEL, "", "5", "480p", "16:9"
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "require image1"):
            nodes.build_minimax_h3_ow_payload(
                nodes.MINIMAX_H3_OW_R2V_MODEL,
                "use the reference person",
                "5",
                "480p",
                "16:9",
            )

        t2v = nodes.build_minimax_h3_ow_payload(
            nodes.MINIMAX_H3_OW_T2V_MODEL,
            "slow cinematic camera movement",
            "5",
            "480p",
            "16:9",
        )
        self.assertNotIn("images", t2v)
        self.assertEqual(t2v["metadata"], {"resolution": "480p", "ratio": "16:9"})

        for model in (nodes.MINIMAX_H3_OW_I2V_MODEL, nodes.MINIMAX_H3_OW_R2V_MODEL):
            with self.subTest(model=model):
                payload = nodes.build_minimax_h3_ow_payload(
                    model,
                    "" if model == nodes.MINIMAX_H3_OW_I2V_MODEL else "use the reference",
                    "10",
                    "720p",
                    "21:9",
                    ["https://example.test/reference.png"],
                )
                self.assertEqual(payload["images"], ["https://example.test/reference.png"])

    def test_execution_uses_video_flow(self):
        final = {
            "status": "completed",
            "metadata": {"url": "https://example.test/result.mp4"},
        }
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(nodes, "image_to_png_bytes", return_value=b"png"),
            patch.object(nodes, "upload_media", return_value="https://example.test/reference.png") as upload,
            patch.object(
                nodes,
                "submit_task",
                return_value=("safe-task", {"id": "safe-task"}),
            ) as submit,
            patch.object(nodes, "poll_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_minimax_h3_ow_video_lowprice().generate(
                model=nodes.MINIMAX_H3_OW_R2V_MODEL,
                prompt="use the reference person in a cinematic scene",
                seconds="5",
                resolution="480p",
                ratio="16:9",
                image1=IMAGE,
            )
        upload.assert_called_once()
        self.assertEqual(submit.call_args.args[0]["model"], nodes.MINIMAX_H3_OW_R2V_MODEL)
        self.assertEqual(result[0], "downloaded-video")


class MinimaxH3OWFastContractTests(unittest.TestCase):
    def test_exact_model_catalog_and_controls(self):
        self.assertEqual(
            nodes.MINIMAX_H3_OW_FAST_MODELS,
            [
                "minimax-h3-ow-i2v-fast",
                "minimax-h3-ow-r2v-fast",
                "minimax-h3-ow-fl2va-audio-drive-fast",
                "minimax-h3-ow-ref2va-audio-drive-fast",
                "minimax-h3-ow-t2v-fast",
            ],
        )
        inputs = nodes.Comfly_minimax_h3_ow_fast_video_lowprice.INPUT_TYPES()
        self.assertEqual(inputs["required"]["seconds"][0], ["5", "10", "15"])
        self.assertEqual(inputs["required"]["resolution"][0], ["480p", "720p"])
        self.assertEqual(inputs["required"]["ratio"][0], nodes.MINIMAX_H3_OW_RATIOS)
        self.assertEqual(
            [name for name in inputs["optional"] if name.startswith("image")],
            [f"image{index}" for index in range(1, 10)],
        )
        self.assertEqual(inputs["optional"]["api_config"][0], nodes.CONFIG_TYPE)
        self.assertEqual(inputs["optional"]["audio"][0], nodes.AUDIO_TYPE)

    def test_strict_validation_enforces_model_specific_image_contracts(self):
        missing = nodes.Comfly_minimax_h3_ow_fast_video_lowprice.VALIDATE_INPUTS(
            model=nodes.MINIMAX_H3_OW_FAST_R2V_MODEL,
            prompt="use the reference subject",
            seconds="5",
            resolution="480p",
            ratio="16:9",
            strict=True,
        )
        self.assertIn("at least one image", missing)

        extra = nodes.Comfly_minimax_h3_ow_fast_video_lowprice.VALIDATE_INPUTS(
            model=nodes.MINIMAX_H3_OW_FAST_I2V_MODEL,
            prompt="",
            seconds="5",
            resolution="480p",
            ratio="16:9",
            image1=IMAGE,
            image2=IMAGE,
            strict=True,
        )
        self.assertIn("exactly image1", extra)

        no_prompt = nodes.Comfly_minimax_h3_ow_fast_video_lowprice.VALIDATE_INPUTS(
            model=nodes.MINIMAX_H3_OW_FAST_R2V_MODEL,
            prompt="",
            seconds="5",
            resolution="480p",
            ratio="16:9",
            image1=IMAGE,
            strict=True,
        )
        self.assertIn("requires a prompt", no_prompt)

    def test_t2v_and_audio_drive_validation_contracts(self):
        missing_prompt = nodes.Comfly_minimax_h3_ow_fast_video_lowprice.VALIDATE_INPUTS(
            model=nodes.MINIMAX_H3_OW_FAST_T2V_MODEL,
            prompt="",
            seconds="5",
            resolution="480p",
            ratio="16:9",
            strict=True,
        )
        self.assertIn("requires a prompt", missing_prompt)

        t2v_with_image = nodes.Comfly_minimax_h3_ow_fast_video_lowprice.VALIDATE_INPUTS(
            model=nodes.MINIMAX_H3_OW_FAST_T2V_MODEL,
            prompt="a paper kite in warm sunlight",
            seconds="5",
            resolution="480p",
            ratio="16:9",
            image1=IMAGE,
            strict=True,
        )
        self.assertIn("does not accept images", t2v_with_image)

        for model in nodes.MINIMAX_H3_OW_FAST_AUDIO_MODELS:
            with self.subTest(model=model):
                missing_audio = nodes.Comfly_minimax_h3_ow_fast_video_lowprice.VALIDATE_INPUTS(
                    model=model,
                    prompt="subtle natural performance",
                    seconds="5",
                    resolution="480p",
                    ratio="16:9",
                    image1=IMAGE,
                    strict=True,
                )
                self.assertIn("requires audio", missing_audio)
                valid = nodes.Comfly_minimax_h3_ow_fast_video_lowprice.VALIDATE_INPUTS(
                    model=model,
                    prompt="subtle natural performance",
                    seconds="5",
                    resolution="480p",
                    ratio="16:9",
                    image1=IMAGE,
                    audio=AUDIO,
                    strict=True,
                )
                self.assertIs(valid, True)

    def test_payload_preserves_one_i2v_or_up_to_nine_r2v_images(self):
        i2v = nodes.build_minimax_h3_ow_fast_payload(
            nodes.MINIMAX_H3_OW_FAST_I2V_MODEL,
            "",
            "5",
            "480p",
            "16:9",
            ["https://example.test/first.png"],
        )
        self.assertEqual(i2v["images"], ["https://example.test/first.png"])
        self.assertNotIn("prompt", i2v)

        urls = [f"https://example.test/reference-{index}.png" for index in range(1, 10)]
        r2v = nodes.build_minimax_h3_ow_fast_payload(
            nodes.MINIMAX_H3_OW_FAST_R2V_MODEL,
            "use every reference in order",
            "15",
            "720p",
            "21:9",
            urls,
        )
        self.assertEqual(r2v["images"], urls)
        self.assertEqual(r2v["metadata"], {"resolution": "720p", "ratio": "21:9"})

        t2v = nodes.build_minimax_h3_ow_fast_payload(
            nodes.MINIMAX_H3_OW_FAST_T2V_MODEL,
            "a paper kite in warm sunlight",
            "5",
            "480p",
            "16:9",
        )
        self.assertNotIn("images", t2v)
        self.assertNotIn("audio_urls", t2v["metadata"])

        audio_drive = nodes.build_minimax_h3_ow_fast_payload(
            nodes.MINIMAX_H3_OW_FAST_FL2VA_AUDIO_MODEL,
            "subtle natural performance",
            "5",
            "480p",
            "16:9",
            ["https://example.test/reference.png"],
            ["https://example.test/drive.wav"],
        )
        self.assertEqual(audio_drive["images"], ["https://example.test/reference.png"])
        self.assertEqual(
            audio_drive["metadata"]["audio_urls"],
            ["https://example.test/drive.wav"],
        )

    def test_execution_compacts_image_slot_gaps_in_upload_order(self):
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
                    "https://example.test/reference-1.png",
                    "https://example.test/reference-3.png",
                ],
            ) as upload,
            patch.object(
                nodes,
                "submit_task",
                return_value=("safe-task", {"id": "safe-task"}),
            ) as submit,
            patch.object(nodes, "poll_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_minimax_h3_ow_fast_video_lowprice().generate(
                model=nodes.MINIMAX_H3_OW_FAST_R2V_MODEL,
                prompt="use the references in connected slot order",
                seconds="5",
                resolution="480p",
                ratio="16:9",
                image1=IMAGE,
                image3=IMAGE,
            )
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(
            submit.call_args.args[0]["images"],
            [
                "https://example.test/reference-1.png",
                "https://example.test/reference-3.png",
            ],
        )
        self.assertEqual(result[0], "downloaded-video")

    def test_audio_drive_uploads_image_then_wav(self):
        final = {
            "status": "completed",
            "metadata": {"url": "https://example.test/result.mp4"},
        }
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(nodes, "image_to_png_bytes", return_value=b"png"),
            patch.object(nodes, "audio_to_wav_bytes", return_value=b"wav"),
            patch.object(
                nodes,
                "upload_media",
                side_effect=[
                    "https://example.test/reference.png",
                    "https://example.test/drive.wav",
                ],
            ) as upload,
            patch.object(
                nodes,
                "submit_task",
                return_value=("safe-task", {"id": "safe-task"}),
            ) as submit,
            patch.object(nodes, "poll_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_minimax_h3_ow_fast_video_lowprice().generate(
                model=nodes.MINIMAX_H3_OW_FAST_REF2VA_AUDIO_MODEL,
                prompt="subtle natural performance",
                seconds="5",
                resolution="480p",
                ratio="16:9",
                image1=IMAGE,
                audio=AUDIO,
            )
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(
            submit.call_args.args[0]["metadata"]["audio_urls"],
            ["https://example.test/drive.wav"],
        )
        self.assertEqual(result[0], "downloaded-video")


class RegistrationFrontendAndWorkflowTests(unittest.TestCase):
    def test_registration_frontend_and_api_link_cover_original_and_concurrent_nodes(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        api_link = (PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js").read_text(encoding="utf-8")
        dynamic_ui = (PLUGIN_ROOT / "web/js/qwen_minimax_model_ui.js").read_text(encoding="utf-8")
        helper = (PLUGIN_ROOT / "web/js/dynamic_widget_ui.js").read_text(encoding="utf-8")
        for node_name in (
            "Comfly_qwen_image_3_0_lowprice",
            "Comfly_minimax_h3_ow_video_lowprice",
            "Comfly_minimax_h3_ow_fast_video_lowprice",
        ):
            self.assertIn(f'"{node_name}"', comfly)
            self.assertIn(f'"{node_name}"', api_link)
            self.assertIn(f'"{node_name}"', dynamic_ui)
        self.assertIn('const prefix = "ComflyConcurrent_"', dynamic_ui)
        self.assertIn('DYNAMIC_HIDDEN_WIDGET_TYPE = `${CONVERTED_WIDGET_PREFIX}:zhenzhen-hidden`', helper)

    def test_every_model_has_a_safe_workflow(self):
        paths = sorted(
            path
            for path in (PLUGIN_ROOT / "workflow").glob("zhenzhen-*（贞贞的平价AI小屋）.json")
            if ("qwen-image-3.0" in path.name or "minimax-h3-ow" in path.name)
            and "并发示例" not in path.name
        )
        self.assertEqual(len(paths), 16)
        covered = set()
        for path in paths:
            raw = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw), path.name)
            workflow = json.loads(raw)
            settings = next(node for node in workflow["nodes"] if node["type"] == "T8Zhenzhen_API_Settings")
            self.assertEqual(settings["widgets_values"], ["seedance_low_price", "", "", False])
            model_node = next(
                node
                for node in workflow["nodes"]
                if node["type"] in {
                    "Comfly_qwen_image_3_0_lowprice",
                    "Comfly_minimax_h3_ow_video_lowprice",
                    "Comfly_minimax_h3_ow_fast_video_lowprice",
                }
            )
            model = model_node["widgets_values"][0]
            covered.add(model)
            config_input = next(item for item in model_node["inputs"] if item["name"] == "api_config")
            self.assertIsNotNone(config_input["link"])
            image1 = next(item for item in model_node["inputs"] if item["name"] == "image1")
            needs_image = (
                model.endswith("-i2i")
                or model.endswith("-i2v")
                or model.endswith("-r2v")
                or model in (
                    nodes.MINIMAX_H3_OW_FAST_I2V_MODEL,
                    nodes.MINIMAX_H3_OW_FAST_R2V_MODEL,
                    *nodes.MINIMAX_H3_OW_FAST_AUDIO_MODELS,
                )
            )
            self.assertEqual(image1["link"] is not None, needs_image)
            if model in nodes.MINIMAX_H3_OW_FAST_MODELS:
                expected_inputs = [f"image{index}" for index in range(1, 10)] + [
                    "api_config"
                ]
                if model in (
                    *nodes.MINIMAX_H3_OW_FAST_AUDIO_MODELS,
                    nodes.MINIMAX_H3_OW_FAST_T2V_MODEL,
                ):
                    expected_inputs.append("audio")
                self.assertEqual(
                    [item["name"] for item in model_node["inputs"]],
                    expected_inputs,
                )
                config_input = next(
                    item for item in model_node["inputs"] if item["name"] == "api_config"
                )
                self.assertEqual(
                    next(
                        link[4]
                        for link in workflow["links"]
                        if link[3] == model_node["id"]
                        and link[0] == settings["id"]
                    ),
                    9,
                )
                self.assertIsNotNone(config_input["link"])
                incoming_audio = [
                    link
                    for link in workflow["links"]
                    if link[3] == model_node["id"] and link[5] == "AUDIO"
                ]
                self.assertEqual(
                    len(incoming_audio),
                    1 if model in nodes.MINIMAX_H3_OW_FAST_AUDIO_MODELS else 0,
                )
                if incoming_audio:
                    self.assertEqual(incoming_audio[0][4], 10)
        self.assertEqual(
            covered,
            set(
                nodes.QWEN_IMAGE_30_MODELS
                + nodes.MINIMAX_H3_OW_MODELS
                + nodes.MINIMAX_H3_OW_FAST_MODELS
            ),
        )

    def test_family_concurrent_workflows_use_generated_submit_and_collect_nodes(self):
        expected = {
            "zhenzhen-qwen-image-3.0并发示例（贞贞的平价AI小屋）.json": (
                "ComflyConcurrent_Comfly_qwen_image_3_0_lowprice_Submit",
                "ComflyConcurrent_Image_Await",
            ),
            "zhenzhen-minimax-h3-ow并发示例（贞贞的平价AI小屋）.json": (
                "ComflyConcurrent_Comfly_minimax_h3_ow_video_lowprice_Submit",
                "ComflyConcurrent_Video_Await",
            ),
        }
        for filename, (submit_type, collector_type) in expected.items():
            workflow = json.loads((PLUGIN_ROOT / "workflow" / filename).read_text(encoding="utf-8"))
            types = [node["type"] for node in workflow["nodes"]]
            self.assertEqual(types.count(submit_type), 2)
            self.assertIn(collector_type, types)
            settings = next(node for node in workflow["nodes"] if node["type"] == "T8Zhenzhen_API_Settings")
            self.assertEqual(settings["widgets_values"][1], "")


if __name__ == "__main__":
    unittest.main()
