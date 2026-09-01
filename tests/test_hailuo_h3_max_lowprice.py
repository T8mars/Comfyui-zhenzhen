import json
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import seedance_low_price_nodes as nodes


ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"base_url": "https://example.test", "api_key": "sk-test"}


class HailuoH3MaxLowPriceTests(unittest.TestCase):
    def test_documented_models_and_controls(self):
        self.assertEqual(
            nodes.HAILUO_H3_MAX_MODELS,
            ["hailuo-h3-max-t2v", "hailuo-h3-max-i2v"],
        )
        self.assertEqual(
            nodes.HAILUO_H3_MAX_SECONDS,
            [str(value) for value in range(5, 16)],
        )
        self.assertEqual(nodes.HAILUO_H3_MAX_RESOLUTIONS, ["480P", "768P"])
        self.assertEqual(
            nodes.HAILUO_H3_MAX_RATIOS,
            ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
        )
        inputs = nodes.Comfly_hailuo_h3_max_video_lowprice.INPUT_TYPES()
        self.assertEqual(
            list(inputs["optional"]),
            ["image1", "image2", "api_config", "skip_error"],
        )
        self.assertFalse(inputs["optional"]["skip_error"][1]["default"])

    def test_t2v_payload_matches_documented_contract(self):
        payload = nodes.build_hailuo_h3_max_payload(
            {
                "model": "hailuo-h3-max-t2v",
                "prompt": "A paper airplane glides through a sunlit studio",
                "seconds": "5",
                "resolution": "480P",
                "ratio": "16:9",
            }
        )
        self.assertEqual(
            payload,
            {
                "model": "hailuo-h3-max-t2v",
                "prompt": "A paper airplane glides through a sunlit studio",
                "seconds": "5",
                "metadata": {"resolution": "480P", "ratio": "16:9"},
            },
        )

    def test_i2v_payload_uses_frames_and_omits_ratio(self):
        payload = nodes.build_hailuo_h3_max_payload(
            {
                "model": "hailuo-h3-max-i2v",
                "prompt": "The subject turns naturally as the camera moves forward",
                "seconds": "15",
                "resolution": "768P",
                "ratio": "9:16",
            },
            ["https://cdn.test/first.png", "https://cdn.test/last.png"],
        )
        self.assertEqual(
            payload["images"],
            ["https://cdn.test/first.png", "https://cdn.test/last.png"],
        )
        self.assertEqual(payload["metadata"], {"resolution": "768P"})
        self.assertNotIn("ratio", payload["metadata"])

    def test_strict_validation_enforces_model_specific_contract(self):
        common = {
            "prompt": "valid prompt",
            "seconds": "5",
            "resolution": "480P",
            "ratio": "16:9",
        }
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "prompt is required"):
            nodes.validate_hailuo_h3_max_inputs(
                "hailuo-h3-max-t2v",
                "",
                "5",
                "480P",
                "16:9",
                strict=True,
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "does not accept"):
            nodes.validate_hailuo_h3_max_inputs(
                "hailuo-h3-max-t2v",
                strict=True,
                image1=object(),
                **common,
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "requires image1"):
            nodes.validate_hailuo_h3_max_inputs(
                "hailuo-h3-max-i2v",
                strict=True,
                **common,
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "480P or 768P"):
            nodes.validate_hailuo_h3_max_inputs(
                "hailuo-h3-max-t2v",
                "valid",
                "5",
                "2K",
                "16:9",
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "Unsupported.*ratio"):
            nodes.validate_hailuo_h3_max_inputs(
                "hailuo-h3-max-t2v",
                "valid",
                "5",
                "480P",
                "adaptive",
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
    @patch.object(nodes, "image_to_png_bytes", return_value=b"png")
    @patch.object(nodes, "upload_media")
    def test_i2v_node_uploads_first_and_last_frame(
        self,
        upload_media,
        _image_to_png_bytes,
        submit_task,
        _poll_task,
        _download_video,
    ):
        upload_media.side_effect = [
            "https://cdn.test/first.png",
            "https://cdn.test/last.png",
        ]
        submit_task.return_value = ("task-test", {"id": "task-test"})
        result = nodes.Comfly_hailuo_h3_max_video_lowprice().generate(
            model="hailuo-h3-max-i2v",
            prompt="Smooth motion between the first and last frame",
            seconds="5",
            resolution="480P",
            ratio="16:9",
            api_config=CONFIG,
            image1=np.zeros((1, 32, 32, 3), dtype=np.float32),
            image2=np.zeros((1, 32, 32, 3), dtype=np.float32),
        )
        self.assertEqual(
            result[:3],
            ("downloaded-video", "https://cdn.test/result.mp4", "task-test"),
        )
        payload = submit_task.call_args.args[0]
        self.assertEqual(
            payload["images"],
            ["https://cdn.test/first.png", "https://cdn.test/last.png"],
        )
        self.assertNotIn("ratio", payload["metadata"])

    def test_registration_and_frontend_sources_cover_base_and_concurrent_nodes(self):
        comfly_source = (ROOT / "Comfly.py").read_text(encoding="utf-8")
        self.assertIn(
            '"Comfly_hailuo_h3_max_video_lowprice": Comfly_hailuo_h3_max_video_lowprice',
            comfly_source,
        )
        frontend = (ROOT / "web" / "js" / "hailuo_h3_max_model_ui.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('"Comfly_hailuo_h3_max_video_lowprice"', frontend)
        self.assertIn(
            '"ComflyConcurrent_Comfly_hailuo_h3_max_video_lowprice_Submit"',
            frontend,
        )
        self.assertIn('model === "hailuo-h3-max-i2v"', frontend)

    def test_workflows_cover_both_models_without_secrets(self):
        paths = sorted((ROOT / "workflow").glob("zhenzhen-hailuo-h3-max-*.json"))
        self.assertEqual(len(paths), 2)
        covered = set()
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("sk-", text)
            workflow = json.loads(text)
            node = next(
                item
                for item in workflow["nodes"]
                if item["type"] == "Comfly_hailuo_h3_max_video_lowprice"
            )
            covered.add(node["widgets_values"][0])
            self.assertEqual(
                [item["name"] for item in node["inputs"]],
                ["image1", "image2", "api_config"],
            )
            settings = next(
                item
                for item in workflow["nodes"]
                if item["type"] == "T8Zhenzhen_API_Settings"
            )
            self.assertEqual(
                settings["widgets_values"],
                ["seedance_low_price", "", "", False],
            )
            incoming = [link for link in workflow["links"] if link[3] == node["id"]]
            image_links = [link for link in incoming if link[5] == "IMAGE"]
            if node["widgets_values"][0].endswith("-t2v"):
                self.assertEqual(image_links, [])
            else:
                self.assertEqual(
                    {(link[4], link[5]) for link in image_links},
                    {(0, "IMAGE"), (1, "IMAGE")},
                )
        self.assertEqual(covered, set(nodes.HAILUO_H3_MAX_MODELS))


if __name__ == "__main__":
    unittest.main()
