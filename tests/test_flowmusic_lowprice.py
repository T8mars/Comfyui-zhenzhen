import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import latest_image_audio_low_price_nodes as latest
from generate_flowmusic_workflows import SOURCE_FILES, target_filename


EXPECTED_OPERATIONS = [
    "flowmusic-generation",
    "flowmusic-lyrics",
    "flowmusic-upload-audio",
    "flowmusic-extend",
    "flowmusic-replace",
    "flowmusic-cover",
    "flowmusic-stems",
    "flowmusic-download-audio",
    "flowmusic-video-clip",
]
CONFIG = {"base_url": "https://example.test", "api_key": "test-key"}
AUDIO = {"waveform": object(), "sample_rate": 44100}


def values():
    return {
        "version": "default",
        "sound_prompt": "warm cinematic piano",
        "lyrics": "",
        "prompt": "a hopeful song after rain",
        "title": "",
        "bpm": 120,
        "length": 30,
        "clip_id": "clip-source",
        "extend_from_s": 0.0,
        "extend_s": 15,
        "instruction": "continue naturally with soft strings",
        "start_s": 0.0,
        "end_s": 5.0,
        "strength": 0.5,
        "format": "mp3",
        "preset": "modern",
        "seed": 7,
    }


class FlowMusicContractTests(unittest.TestCase):
    def setUp(self):
        self.node = latest.Comfly_flowmusic_lowprice()

    def test_operation_catalog_and_paths_are_exact(self):
        self.assertEqual(latest.FLOWMUSIC_OPERATIONS, EXPECTED_OPERATIONS)
        for operation in EXPECTED_OPERATIONS:
            expected_action = "" if operation == "flowmusic-generation" else operation[10:]
            with self.subTest(operation=operation):
                self.assertEqual(
                    latest.FLOWMUSIC_ACTION_SPECS[operation]["action"],
                    expected_action,
                )

    def test_every_payload_uses_fixed_model_and_action_whitelist(self):
        for operation in EXPECTED_OPERATIONS:
            uploaded = (
                "https://media.test/source.wav"
                if operation == "flowmusic-upload-audio"
                else ""
            )
            with self.subTest(operation=operation):
                payload = self.node._build_payload(operation, uploaded, **values())
                allowed = set(
                    latest.FLOWMUSIC_ACTION_SPECS[operation]["allowed_fields"]
                )
                self.assertEqual(payload["model"], "flowmusic")
                self.assertTrue(set(payload).issubset({"model", *allowed}))

    def test_generation_payload_preserves_documented_types(self):
        payload = self.node._build_payload(
            "flowmusic-generation", **values()
        )
        self.assertEqual(
            payload,
            {
                "model": "flowmusic",
                "sound_prompt": "warm cinematic piano",
                "bpm": "120",
                "length": 30,
                "seed": 7,
            },
        )

    def test_lyria_version_is_sent_only_by_supported_actions(self):
        supported = {
            "flowmusic-generation",
            "flowmusic-extend",
            "flowmusic-replace",
            "flowmusic-cover",
        }
        for operation in EXPECTED_OPERATIONS:
            kwargs = values()
            kwargs["version"] = "lyria-3.5"
            uploaded = (
                "https://media.test/source.wav"
                if operation == "flowmusic-upload-audio"
                else ""
            )
            payload = self.node._build_payload(operation, uploaded, **kwargs)
            with self.subTest(operation=operation):
                self.assertEqual(
                    payload.get("version"),
                    "lyria-3.5" if operation in supported else None,
                )

    def test_documented_validation_ranges(self):
        kwargs = values()
        kwargs.update({"sound_prompt": "", "lyrics": ""})
        with self.assertRaisesRegex(latest.SeedanceLowPriceError, "both be empty"):
            self.node._build_payload("flowmusic-generation", **kwargs)

        kwargs = values()
        kwargs["prompt"] = "x" * 3001
        with self.assertRaisesRegex(latest.SeedanceLowPriceError, "3000"):
            self.node._build_payload("flowmusic-lyrics", **kwargs)

        kwargs = values()
        kwargs.update({"start_s": 5.0, "end_s": 5.0})
        with self.assertRaisesRegex(latest.SeedanceLowPriceError, "greater"):
            self.node._build_payload("flowmusic-replace", **kwargs)

        kwargs = values()
        kwargs["strength"] = 1.1
        with self.assertRaisesRegex(latest.SeedanceLowPriceError, "between 0 and 1"):
            self.node._build_payload("flowmusic-cover", **kwargs)

        kwargs = values()
        kwargs["extend_s"] = 165
        with self.assertRaisesRegex(latest.SeedanceLowPriceError, "164"):
            self.node._build_payload("flowmusic-extend", **kwargs)

    def test_upload_accepts_one_local_or_public_audio_source(self):
        with self.assertRaisesRegex(latest.SeedanceLowPriceError, "cannot both"):
            self.node._resolve_audio_url(
                "flowmusic-upload-audio",
                object(),
                "https://media.test/a.wav",
                CONFIG,
            )
        with patch.object(latest, "audio_to_wav_bytes", return_value=b"wav"), patch.object(
            latest, "upload_media", return_value="https://media.test/upload.wav"
        ) as upload:
            url = self.node._resolve_audio_url(
                "flowmusic-upload-audio", object(), "", CONFIG
            )
        self.assertEqual(url, "https://media.test/upload.wav")
        upload.assert_called_once()


class FlowMusicResultTests(unittest.TestCase):
    def test_result_extracts_nested_lyrics_and_clip_ids(self):
        response = {
            "data": {
                "id": "task-test",
                "status": "completed",
                "result": {
                    "lyrics": [{"title": "Rain", "lyrics": "Light after rain"}],
                    "music": [
                        {
                            "clip_id": "clip-one",
                            "audio_url": "https://media.test/a.wav",
                        },
                        {
                            "clip_id": "clip-two",
                            "video_url": "https://media.test/a.mp4",
                        },
                    ],
                },
            }
        }
        extracted = latest.extract_flowmusic_results(response)
        self.assertEqual(extracted["clip_ids"], ["clip-one", "clip-two"])
        self.assertEqual(extracted["text"], "Light after rain")
        self.assertEqual(
            [item["url"] for item in extracted["artifacts"]],
            ["https://media.test/a.wav", "https://media.test/a.mp4"],
        )

    def test_execute_returns_clip_and_downloaded_audio(self):
        final = {
            "data": {
                "id": "task-test",
                "status": "completed",
                "result": {
                    "music": [
                        {
                            "clip_id": "clip-result",
                            "audio_url": "https://media.test/result.wav",
                        }
                    ]
                },
            }
        }
        with patch.object(latest, "resolve_config", return_value=CONFIG), patch.object(
            latest, "submit_suno_action", return_value=("task-test", {})
        ) as submit, patch.object(
            latest, "poll_suno_task", return_value=final
        ), patch.object(
            latest, "download_suno_audio", return_value=(AUDIO, "result.wav")
        ):
            result = latest.Comfly_flowmusic_lowprice().execute(
                operation="flowmusic-generation", **values()
            )
        self.assertEqual(submit.call_args.args[0], "")
        self.assertEqual(result["result"][0], AUDIO)
        self.assertEqual(result["result"][4], "clip-result")

    def test_skip_error_returns_all_typed_outputs(self):
        with patch.object(latest, "make_error_video", return_value="error.mp4"):
            result = latest.Comfly_flowmusic_lowprice().execute(
                operation="flowmusic-lyrics",
                skip_error=True,
                **{**values(), "prompt": ""},
            )
        self.assertEqual(len(result["result"]), 11)
        self.assertIn("error", result["result"][-1])


class FlowMusicRegistrationAndWorkflowTests(unittest.TestCase):
    def test_node_and_frontend_are_registered(self):
        comfly_source = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        self.assertIn(
            '"Comfly_flowmusic_lowprice": Comfly_flowmusic_lowprice',
            comfly_source,
        )
        source = (PLUGIN_ROOT / "web" / "js" / "flowmusic_action_ui.js").read_text(
            encoding="utf-8"
        )
        for fragment in (
            'const FLOWMUSIC_NODE_NAME = "Comfly_flowmusic_lowprice"',
            '"flowmusic-video-clip": ["clip_id", "preset"]',
            'from "./dynamic_widget_ui.js"',
            "setZhenzhenInputVisible(node, input, visible.has(input.name))",
            "refreshFlowMusicNode(node)",
        ):
            self.assertIn(fragment, source)

    def test_all_nine_safe_workflows_exist_and_clip_actions_are_chained(self):
        self.assertEqual(len(SOURCE_FILES), 9)
        covered = set()
        clip_actions = set(EXPECTED_OPERATIONS) - {
            "flowmusic-generation",
            "flowmusic-lyrics",
            "flowmusic-upload-audio",
        }
        for source_name in SOURCE_FILES:
            path = PLUGIN_ROOT / "workflow" / target_filename(source_name)
            workflow = json.loads(path.read_text(encoding="utf-8"))
            flow_nodes = [
                item
                for item in workflow["nodes"]
                if item["type"] == "Comfly_flowmusic_lowprice"
            ]
            selected = {item["widgets_values"][0] for item in flow_nodes}
            operation = next(
                item
                for item in EXPECTED_OPERATIONS
                if source_name.startswith(item)
            )
            covered.add(operation)
            self.assertIn(operation, selected)
            target = next(
                item for item in flow_nodes if item["widgets_values"][0] == operation
            )
            if operation == "flowmusic-replace":
                self.assertEqual(target["widgets_values"][1], "lyria-3.5")
            config = next(
                item
                for item in workflow["nodes"]
                if item["type"] == "Comfly_seedance2_low_price_settings"
            )
            self.assertEqual(config["widgets_values"][1], "")
            raw = path.read_text(encoding="utf-8")
            self.assertNotRegex(raw, r"sk-[A-Za-z0-9_-]{12,}")
            self.assertNotRegex(raw, r'"task_[A-Za-z0-9_-]{6,}"')
            if operation in clip_actions:
                clip_links = [
                    link
                    for link in workflow["links"]
                    if link[3] == target["id"] and link[5] == "STRING"
                ]
                self.assertEqual(len(clip_links), 1)
                self.assertIn("flowmusic-upload-audio", selected)
        self.assertEqual(covered, set(EXPECTED_OPERATIONS))


if __name__ == "__main__":
    unittest.main()
