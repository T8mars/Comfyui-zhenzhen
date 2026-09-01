import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


CONFIG = {
    "base_url": "https://api.seedance.nz",
    "api_key": "test-key",
    "poll_interval": 0,
    "max_poll_time": 30,
}
IMAGE = torch.zeros((1, 8, 8, 3), dtype=torch.float32)


class _Response:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


class MinMaxH3ContextIRContractTests(unittest.TestCase):
    def test_exact_catalog_and_input_limits(self):
        self.assertEqual(
            nodes.MINMAX_H3_CONTEXT_IR_MODELS,
            [
                "minmax-h3-context-ir-text",
                "minmax-h3-context-ir-image",
                "minmax-h3-context-ir-multimodal",
            ],
        )
        inputs = nodes.Comfly_minmax_h3_context_ir_lowprice.INPUT_TYPES()
        self.assertEqual(
            inputs["required"]["seconds"][0],
            [str(value) for value in range(4, 16)],
        )
        self.assertEqual(
            inputs["required"]["ratio"][0],
            [
                "api_default",
                "adaptive",
                "21:9",
                "16:9",
                "4:3",
                "1:1",
                "3:4",
                "9:16",
            ],
        )
        optional = inputs["optional"]
        self.assertEqual(
            [name for name in optional if name.startswith("image")],
            [f"image{index}" for index in range(1, 10)],
        )
        self.assertEqual(
            [name for name in optional if name.startswith("video")],
            ["video1", "video2", "video3"],
        )
        self.assertEqual(
            [name for name in optional if name.startswith("audio")],
            ["audio1", "audio2", "audio3"],
        )
        self.assertEqual(list(optional)[-3:], ["api_config", "skip_error", "seed"])
        self.assertTrue(optional["seed"][1]["control_after_generate"])

    def test_validation_is_model_aware(self):
        node = nodes.Comfly_minmax_h3_context_ir_lowprice
        self.assertIn(
            "prompt is required",
            node.VALIDATE_INPUTS(
                model=nodes.MINMAX_H3_CONTEXT_IR_TEXT_MODEL,
                prompt="",
                seconds="4",
                ratio="16:9",
                strict=True,
            ),
        )
        self.assertIn(
            "fixed documented ratio",
            node.VALIDATE_INPUTS(
                model=nodes.MINMAX_H3_CONTEXT_IR_TEXT_MODEL,
                prompt="camera follows the subject",
                seconds="4",
                ratio="adaptive",
                strict=True,
            ),
        )
        self.assertIn(
            "requires image1",
            node.VALIDATE_INPUTS(
                model=nodes.MINMAX_H3_CONTEXT_IR_IMAGE_MODEL,
                prompt="animate this frame",
                seconds="4",
                ratio="16:9",
                strict=True,
            ),
        )
        self.assertIn(
            "at least one",
            node.VALIDATE_INPUTS(
                model=nodes.MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL,
                prompt="combine the references",
                seconds="4",
                ratio="api_default",
                strict=True,
            ),
        )
        self.assertIs(
            node.VALIDATE_INPUTS(
                model=nodes.MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL,
                prompt="combine the references",
                seconds="15",
                ratio="adaptive",
                image1=IMAGE,
                video1=object(),
                audio1=object(),
                strict=True,
            ),
            True,
        )

    def test_payload_contract_for_all_models(self):
        node = nodes.Comfly_minmax_h3_context_ir_lowprice()
        common = {
            "prompt": "smooth cinematic camera movement",
            "seconds": "4",
            "ratio": "16:9",
        }
        text_payload = node._build_payload(
            nodes.MINMAX_H3_CONTEXT_IR_TEXT_MODEL,
            media={},
            kwargs={},
            **common,
        )
        self.assertEqual(
            text_payload,
            {
                "model": "minmax-h3-context-ir-text",
                "prompt": common["prompt"],
                "seconds": "4",
                "metadata": {"ratio": "16:9"},
            },
        )

        image_payload = node._build_payload(
            nodes.MINMAX_H3_CONTEXT_IR_IMAGE_MODEL,
            media={"images": ["https://media.test/first.png", "https://media.test/last.png"]},
            kwargs={"image1": IMAGE, "image2": IMAGE},
            **common,
        )
        self.assertEqual(
            image_payload["images"],
            ["https://media.test/first.png", "https://media.test/last.png"],
        )
        self.assertNotIn("metadata", image_payload)

        multi_payload = node._build_payload(
            nodes.MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL,
            media={
                "images": ["https://media.test/image.png"],
                "video_urls": ["https://media.test/video.mp4"],
                "audio_urls": ["https://media.test/audio.wav"],
            },
            kwargs={"image1": IMAGE, "video1": object(), "audio1": object()},
            **common,
        )
        self.assertEqual(multi_payload["images"], ["https://media.test/image.png"])
        self.assertEqual(
            multi_payload["metadata"],
            {
                "ratio": "16:9",
                "video_urls": ["https://media.test/video.mp4"],
                "audio_url": ["https://media.test/audio.wav"],
            },
        )

    def test_multimodal_collects_all_media_families(self):
        node = nodes.Comfly_minmax_h3_context_ir_lowprice()
        progress = []
        with (
            patch.object(nodes, "image_to_png_bytes", return_value=b"image"),
            patch.object(nodes, "video_to_mp4_bytes", return_value=b"video"),
            patch.object(nodes, "audio_to_wav_bytes", return_value=b"audio"),
            patch.object(
                nodes,
                "upload_media",
                side_effect=[
                    "https://media.test/image.png",
                    "https://media.test/video.mp4",
                    "https://media.test/audio.wav",
                ],
            ) as upload,
        ):
            media = node._collect_media(
                nodes.MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL,
                CONFIG,
                {"image1": IMAGE, "video1": object(), "audio1": object()},
                progress.append,
            )
        self.assertEqual(upload.call_count, 3)
        self.assertEqual(
            media,
            {
                "images": ["https://media.test/image.png"],
                "video_urls": ["https://media.test/video.mp4"],
                "audio_urls": ["https://media.test/audio.wav"],
            },
        )
        self.assertEqual(progress, [5, 10, 15])

    def test_execute_returns_result_text_and_skip_error_shape(self):
        final = {
            "code": "success",
            "data": {"status": "SUCCESS", "result_text": "Enhanced prompt"},
        }
        node = nodes.Comfly_minmax_h3_context_ir_lowprice()
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(node, "_collect_media", return_value={}),
            patch.object(
                nodes,
                "submit_minmax_h3_context_ir_task",
                return_value=("task-test", {"id": "task-test"}),
            ) as submit,
            patch.object(
                nodes,
                "poll_minmax_h3_context_ir_task",
                return_value=final,
            ),
        ):
            result = node.enhance(
                model=nodes.MINMAX_H3_CONTEXT_IR_TEXT_MODEL,
                prompt="A quiet garden at sunrise",
                seconds="4",
                ratio="16:9",
                seed=123,
            )
        self.assertEqual(submit.call_args.args[0]["metadata"], {"ratio": "16:9"})
        self.assertEqual(result["result"][:2], ("Enhanced prompt", "task-test"))

        with patch.object(nodes, "resolve_config", side_effect=RuntimeError("forced")):
            error_result = node.enhance(
                model=nodes.MINMAX_H3_CONTEXT_IR_TEXT_MODEL,
                prompt="A quiet garden at sunrise",
                seconds="4",
                ratio="16:9",
                skip_error=True,
            )
        self.assertEqual(error_result["result"][:2], ("", ""))
        self.assertIn("forced", json.loads(error_result["result"][2])["message"])


class MinMaxH3ContextIRClientTests(unittest.TestCase):
    def test_submit_and_poll_use_documented_compatibility_endpoints(self):
        session = Mock()
        session.post.return_value = _Response(200, {"data": {"id": "task-test"}})
        session.get.side_effect = [
            _Response(200, {"data": {"status": "IN_PROGRESS", "progress": "50%"}}),
            _Response(
                200,
                {
                    "code": "success",
                    "data": {"status": "SUCCESS", "result_text": "Enhanced prompt"},
                },
            ),
        ]
        with patch.object(nodes, "_get_session", return_value=session):
            task_id, _response = nodes.submit_minmax_h3_context_ir_task(
                {"model": nodes.MINMAX_H3_CONTEXT_IR_TEXT_MODEL},
                CONFIG,
            )
            final = nodes.poll_minmax_h3_context_ir_task(
                task_id,
                CONFIG,
                sleep=lambda _seconds: None,
            )
        self.assertEqual(
            session.post.call_args.args[0],
            "https://api.seedance.nz/v1/video/generations",
        )
        self.assertEqual(
            session.get.call_args.args[0],
            "https://api.seedance.nz/v1/video/generations/task-test",
        )
        self.assertEqual(
            nodes.extract_minmax_h3_context_ir_text(final),
            "Enhanced prompt",
        )


class MinMaxH3ContextIRIntegrationFilesTests(unittest.TestCase):
    def test_registration_frontend_api_link_and_no_concurrent_wrapper(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        api_link = (
            PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        dynamic_ui = (
            PLUGIN_ROOT / "web/js/qwen_minimax_model_ui.js"
        ).read_text(encoding="utf-8")
        node_name = "Comfly_minmax_h3_context_ir_lowprice"
        self.assertIn(f'"{node_name}"', comfly)
        self.assertIn(f'"{node_name}"', api_link)
        self.assertIn(f'const CONTEXT_IR_NODE_NAME = "{node_name}"', dynamic_ui)
        self.assertIn("function refreshContextIRNode(node)", dynamic_ui)
        self.assertTrue(nodes.Comfly_minmax_h3_context_ir_lowprice.COMFLY_CONCURRENT_DISABLED)
        self.assertEqual(
            nodes.Comfly_minmax_h3_context_ir_lowprice.RETURN_TYPES,
            ("STRING", "STRING", "STRING"),
        )

    def test_three_safe_workflows_cover_every_model_and_media_mode(self):
        workflows = {}
        for path in (PLUGIN_ROOT / "workflow").glob(
            "zhenzhen-minmax-h3-context-ir-*（贞贞的平价AI小屋）.json"
        ):
            raw = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw), path.name)
            document = json.loads(raw)
            model_node = next(
                item for item in document["nodes"] if item["type"] == "Comfly_minmax_h3_context_ir_lowprice"
            )
            workflows[model_node["widgets_values"][0]] = document
            settings = next(
                item for item in document["nodes"] if item["type"] == "T8Zhenzhen_API_Settings"
            )
            self.assertEqual(
                settings["widgets_values"],
                ["seedance_low_price", "", "", False],
            )
            config_input = next(
                item for item in model_node["inputs"] if item["name"] == "api_config"
            )
            self.assertIsNotNone(config_input["link"])
        self.assertEqual(set(workflows), set(nodes.MINMAX_H3_CONTEXT_IR_MODELS))

        image_types = {
            item[5]
            for item in workflows[nodes.MINMAX_H3_CONTEXT_IR_IMAGE_MODEL]["links"]
        }
        self.assertIn("IMAGE", image_types)
        multimodal_types = {
            item[5]
            for item in workflows[nodes.MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL]["links"]
        }
        self.assertTrue({"IMAGE", "VIDEO", "AUDIO"}.issubset(multimodal_types))


if __name__ == "__main__":
    unittest.main()
