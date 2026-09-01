import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


CONFIG = {
    "base_url": "https://api.seedance.nz",
    "api_key": "test",
    "timeout": 30,
    "poll_interval": 0,
    "max_poll_time": 30,
}


class _Response:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


class FlashVSRLowPriceContractTests(unittest.TestCase):
    def test_inputs_and_model_match_documented_contract(self):
        inputs = nodes.Comfly_fashvsr_video_upscale_lowprice.INPUT_TYPES()
        self.assertEqual(
            nodes.FLASHVSR_VIDEO_UPSCALE_MODEL,
            "FlashVSR_video_upscale",
        )
        self.assertEqual(list(inputs["required"]), ["video_url"])
        self.assertEqual(
            list(inputs["optional"]),
            ["input_video", "api_config", "skip_error", "seed"],
        )
        self.assertEqual(inputs["optional"]["seed"][1]["default"], 0)
        self.assertTrue(
            inputs["optional"]["seed"][1]["control_after_generate"]
        )

    def test_payload_contains_only_model_and_metadata_video_url(self):
        payload = nodes.build_flashvsr_payload(
            "https://cdn.test/source.mp4"
        )
        self.assertEqual(payload, {
            "model": "FlashVSR_video_upscale",
            "metadata": {"video_url": "https://cdn.test/source.mp4"},
        })

    def test_exactly_one_source_is_required(self):
        node = nodes.Comfly_fashvsr_video_upscale_lowprice()
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "exactly one"):
            node.generate(
                video_url="https://cdn.test/source.mp4",
                input_video=object(),
                api_config=CONFIG,
            )
        with self.assertRaisesRegex(nodes.SeedanceLowPriceError, "Connect input_video"):
            node.generate(video_url="", api_config=CONFIG)

    def test_local_video_is_uploaded_once(self):
        final = {
            "code": "success",
            "data": {
                "status": "SUCCESS",
                "result_url": "https://cdn.test/result.mp4",
            },
        }
        with (
            patch.object(nodes, "resolve_config", return_value=CONFIG),
            patch.object(nodes, "video_to_mp4_bytes", return_value=b"video"),
            patch.object(
                nodes,
                "upload_media",
                return_value="https://cdn.test/uploaded.mp4",
            ) as upload,
            patch.object(
                nodes,
                "submit_legacy_video_task",
                return_value=("task-test", {"data": {"id": "task-test"}}),
            ) as submit,
            patch.object(nodes, "poll_legacy_video_task", return_value=final),
            patch.object(nodes, "download_video", return_value="downloaded-video"),
        ):
            result = nodes.Comfly_fashvsr_video_upscale_lowprice().generate(
                video_url="",
                input_video={"file_path": "source.mp4"},
                api_config=CONFIG,
            )

        upload.assert_called_once_with(
            b"video",
            "flashvsr_input.mp4",
            "video/mp4",
            CONFIG,
        )
        self.assertEqual(submit.call_args.args[0], {
            "model": "FlashVSR_video_upscale",
            "metadata": {"video_url": "https://cdn.test/uploaded.mp4"},
        })
        self.assertEqual(result[:3], (
            "downloaded-video",
            "https://cdn.test/result.mp4",
            "task-test",
        ))

    def test_legacy_submit_poll_and_url_extraction(self):
        session = Mock()
        session.post.return_value = _Response(
            200, {"data": {"id": "task-test"}}
        )
        session.get.side_effect = [
            _Response(
                200,
                {"data": {"status": "IN_PROGRESS", "progress": "40%"}},
            ),
            _Response(
                200,
                {
                    "data": {
                        "status": "SUCCESS",
                        "data": {
                            "content": {
                                "video_url": "https://cdn.test/result.mp4"
                            }
                        },
                    }
                },
            ),
        ]
        with patch.object(nodes, "_get_session", return_value=session):
            task_id, _submit = nodes.submit_legacy_video_task(
                nodes.build_flashvsr_payload("https://cdn.test/source.mp4"),
                CONFIG,
            )
            final = nodes.poll_legacy_video_task(task_id, CONFIG)

        self.assertEqual(task_id, "task-test")
        self.assertEqual(
            session.post.call_args.args[0],
            "https://api.seedance.nz/v1/video/generations",
        )
        self.assertEqual(
            session.get.call_args.args[0],
            "https://api.seedance.nz/v1/video/generations/task-test",
        )
        self.assertEqual(
            nodes.extract_legacy_video_url(final),
            "https://cdn.test/result.mp4",
        )


class FlashVSRLowPriceRegistrationTests(unittest.TestCase):
    def test_registration_api_link_and_safe_workflow(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        api_link = (
            PLUGIN_ROOT / "web/js/zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"Comfly_fashvsr_video_upscale_lowprice": '
            'Comfly_fashvsr_video_upscale_lowprice',
            comfly,
        )
        self.assertIn(
            '"Comfly_fashvsr_video_upscale_lowprice": '
            '"zhenzhen-FlashVSR-video-upscale-lowprice"',
            comfly,
        )
        self.assertIn('"Comfly_fashvsr_video_upscale_lowprice"', api_link)

        path = (
            PLUGIN_ROOT
            / "workflow"
            / "zhenzhen-FlashVSR-480P视频超分（贞贞的平价AI小屋）.json"
        )
        raw = path.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{12,}", raw))
        workflow = json.loads(raw)
        settings = next(
            item for item in workflow["nodes"]
            if item.get("type") == "T8Zhenzhen_API_Settings"
        )
        node = next(
            item for item in workflow["nodes"]
            if item.get("type") == "Comfly_fashvsr_video_upscale_lowprice"
        )
        self.assertEqual(
            settings["widgets_values"],
            ["seedance_low_price", "", "", False],
        )
        self.assertEqual(node["widgets_values"], ["", False, 0, "fixed"])
        connected = {
            value["name"]
            for value in node["inputs"]
            if value.get("link") is not None
        }
        self.assertEqual(connected, {"input_video", "api_config"})


if __name__ == "__main__":
    unittest.main()
