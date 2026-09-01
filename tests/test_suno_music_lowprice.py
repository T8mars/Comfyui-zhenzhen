import json
import sys
import unittest
from pathlib import Path
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import seedance_low_price_nodes as nodes


EXPECTED_OPERATIONS = [
    "suno-generation",
    "suno-lyrics",
    "suno-upload",
    "suno-extend",
    "suno-cover-song",
    "suno-inspo",
    "suno-mashup",
    "suno-upsample-tags",
    "suno-sounds",
    "suno-create-voice",
    "suno-stems",
    "suno-stems-all",
    "suno-wav",
    "suno-generate-mp4",
    "suno-concat",
    "suno-crop",
    "suno-fade-in",
    "suno-fade-out",
    "suno-remove-section",
    "suno-replace-music",
    "suno-adjust-speed",
    "suno-remaster",
    "suno-midi",
    "suno-bpm",
    "suno-aligned-lyrics",
    "suno-persona",
    "suno-vox",
    "suno-sample",
    "suno-add-vocals",
    "suno-add-instrumental",
    "suno-add-stem",
]


def base_values():
    return {
        "prompt": "cinematic piano with a clear melodic arc",
        "version": "v5.5",
        "custom": False,
        "instrumental": True,
        "title": "Example",
        "style": "cinematic",
        "vocal_gender": "unspecified",
        "tags": "cinematic, piano",
        "name": "Studio Persona",
        "task_id": "source-task-a",
        "task_id_2": "source-task-b",
        "audio_index": 1,
        "continue_at": 30.0,
        "start_s": 0.0,
        "end_s": 4.0,
        "duration_s": 2.0,
        "speed": 1.1,
    }


class FakeResponse:
    def __init__(self, status_code, data, headers=None):
        self.status_code = status_code
        self._data = data
        self.text = json.dumps(data)
        self.headers = headers or {}

    def json(self):
        return self._data


class SunoContractTests(unittest.TestCase):
    def setUp(self):
        self.node = nodes.Comfly_suno_music_lowprice()

    def test_operation_catalog_matches_documented_registry(self):
        self.assertEqual(nodes.SUNO_OPERATIONS, EXPECTED_OPERATIONS)
        self.assertEqual(len(nodes.SUNO_ACTION_SPECS), 31)
        for operation in EXPECTED_OPERATIONS:
            expected_action = "" if operation == "suno-generation" else operation[5:]
            self.assertEqual(
                nodes.SUNO_ACTION_SPECS[operation]["action"],
                expected_action,
            )

    def test_live_verified_prompt_requirements_are_encoded(self):
        prompt_actions = {
            "suno-cover-song",
            "suno-mashup",
            "suno-sample",
            "suno-add-vocals",
            "suno-add-instrumental",
            "suno-add-stem",
        }
        for operation in prompt_actions:
            self.assertIn(
                "prompt",
                nodes.SUNO_ACTION_SPECS[operation]["required_fields"],
            )

    def test_all_payloads_use_suno_model_and_only_allowlisted_fields(self):
        url_actions = {
            "suno-upload": ["https://media.example/source.wav"],
            "suno-create-voice": ["https://media.example/source.wav"],
            "suno-inspo": [
                "https://media.example/a.wav",
                "https://media.example/b.wav",
            ],
        }
        for operation in EXPECTED_OPERATIONS:
            with self.subTest(operation=operation):
                payload = self.node._build_payload(
                    operation,
                    url_actions.get(operation, []),
                    **base_values(),
                )
                allowed = set(
                    nodes.SUNO_ACTION_SPECS[operation]["allowed_fields"]
                )
                self.assertEqual(payload["model"], "suno")
                self.assertLessEqual(set(payload) - {"model"}, allowed)
                for field in nodes.SUNO_ACTION_SPECS[operation]["required_fields"]:
                    self.assertIn(field, payload)

    def test_version_constraints_are_action_specific(self):
        values = base_values()
        values["version"] = "v4"
        with self.assertRaisesRegex(
            nodes.SeedanceLowPriceError,
            "does not support version",
        ):
            self.node._build_payload("suno-add-stem", [], **values)
        payload = self.node._build_payload("suno-remaster", [], **base_values())
        self.assertEqual(payload["version"], "v5.5")

    def test_missing_required_prompt_is_rejected(self):
        values = base_values()
        values["prompt"] = ""
        for operation in (
            "suno-generation",
            "suno-cover-song",
            "suno-mashup",
            "suno-sample",
            "suno-add-vocals",
            "suno-add-instrumental",
            "suno-add-stem",
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(
                    nodes.SeedanceLowPriceError,
                    "requires: prompt",
                ):
                    self.node._build_payload(operation, [], **values)

    def test_invalid_time_range_is_rejected(self):
        values = base_values()
        values["start_s"] = 5.0
        values["end_s"] = 5.0
        with self.assertRaisesRegex(
            nodes.SeedanceLowPriceError,
            "end_s must be greater",
        ):
            self.node._build_payload("suno-crop", [], **values)

    def test_local_upload_requires_six_seconds(self):
        audio = {
            "waveform": nodes.torch.zeros((1, 1, 5 * 24000)),
            "sample_rate": 24000,
        }
        with self.assertRaisesRegex(
            nodes.SeedanceLowPriceError,
            "at least 6 seconds",
        ):
            self.node._collect_audio_inputs(
                "suno-upload",
                {"audio1": audio},
                {"base_url": "https://api.example", "api_key": "test"},
                lambda _value: None,
            )

    def test_local_create_voice_requires_ten_to_240_seconds(self):
        for seconds in (9, 241):
            audio = {
                "waveform": nodes.torch.zeros((1, 1, seconds * 100)),
                "sample_rate": 100,
            }
            with self.subTest(seconds=seconds):
                with self.assertRaisesRegex(
                    nodes.SeedanceLowPriceError,
                    "10-240 seconds",
                ):
                    self.node._collect_audio_inputs(
                        "suno-create-voice",
                        {"audio1": audio},
                        {
                            "base_url": "https://api.example",
                            "api_key": "test",
                        },
                        lambda _value: None,
                    )

    def test_submit_uses_dedicated_music_route_and_nested_task_id(self):
        session = mock.Mock()
        session.post.return_value = FakeResponse(
            200,
            {"data": [{"task_id": "accepted-task"}]},
        )
        config = {
            "base_url": "https://api.example",
            "api_key": "test",
            "timeout": 5,
        }
        with mock.patch.object(nodes, "_get_session", return_value=session):
            task_id, response = nodes.submit_suno_action(
                "lyrics",
                {"model": "suno", "prompt": "example"},
                config,
            )
        self.assertEqual(task_id, "accepted-task")
        self.assertIn("data", response)
        self.assertEqual(
            session.post.call_args.args[0],
            "https://api.example/v1/music/generations/lyrics",
        )

    def test_poll_uses_music_tasks_route(self):
        session = mock.Mock()
        session.get.return_value = FakeResponse(
            200,
            {
                "data": {
                    "task_id": "task",
                    "status": "completed",
                    "progress": 100,
                }
            },
        )
        config = {
            "base_url": "https://api.example",
            "api_key": "test",
            "poll_interval": 0,
            "max_poll_time": 5,
        }
        with mock.patch.object(nodes, "_get_session", return_value=session):
            result = nodes.poll_suno_task(
                "task",
                config,
                sleep=lambda _seconds: None,
                clock=lambda: 0,
            )
        self.assertEqual(result["data"]["status"], "completed")
        self.assertEqual(
            session.get.call_args.args[0],
            "https://api.example/v1/music/tasks/task",
        )

    def test_result_extraction_preserves_provider_artifact_order(self):
        result = nodes.extract_suno_results(
            {
                "data": {
                    "task_id": "task",
                    "status": "completed",
                    "result": {
                        "music": [
                            {"audio_url": "https://media.example/a.mp3"},
                            {"video_url": "https://media.example/a.mp4"},
                            {"file_url": "https://media.example/a.mid"},
                        ]
                    },
                }
            }
        )
        self.assertEqual(
            [artifact["kind"] for artifact in result["artifacts"]],
            ["audio", "video", "file"],
        )
        self.assertEqual(
            result["all_urls"],
            [
                "https://media.example/a.mp3",
                "https://media.example/a.mp4",
                "https://media.example/a.mid",
            ],
        )

    def test_partial_download_failure_keeps_url_path_indexes_aligned(self):
        final_response = {
            "data": {
                "task_id": "task",
                "status": "completed",
                "result": {
                    "music": [
                        {"audio_url": "https://media.example/a.mp3"},
                        {"audio_url": "https://media.example/b.mp3"},
                    ]
                },
            }
        }
        audio = {
            "waveform": nodes.torch.zeros((1, 1, 100)),
            "sample_rate": 44100,
        }
        with (
            mock.patch.object(
                nodes,
                "resolve_config",
                return_value={
                    "base_url": "https://api.example",
                    "api_key": "test",
                },
            ),
            mock.patch.object(
                nodes,
                "submit_suno_action",
                return_value=("task", {"data": [{"task_id": "task"}]}),
            ),
            mock.patch.object(
                nodes,
                "poll_suno_task",
                return_value=final_response,
            ),
            mock.patch.object(
                nodes,
                "download_suno_audio",
                side_effect=[(audio, "a.mp3"), RuntimeError("download failed")],
            ),
        ):
            output = self.node._execute_inner(
                "suno-generation",
                None,
                base_values(),
            )
        paths = json.loads(output["result"][7])
        urls = json.loads(output["result"][5])
        self.assertEqual(len(paths), len(urls))
        self.assertEqual(paths, ["a.mp3", ""])
        self.assertIs(output["result"][0], audio)

    def test_skip_error_returns_typed_placeholders(self):
        with mock.patch.object(nodes, "make_error_video", return_value="error.mp4"):
            output = self.node.execute(
                operation="suno-generation",
                prompt="",
                version="v5.5",
                custom=False,
                instrumental=True,
                title="",
                style="",
                vocal_gender="unspecified",
                tags="",
                name="",
                task_id="",
                task_id_2="",
                audio_index=1,
                continue_at=30.0,
                start_s=0.0,
                end_s=4.0,
                duration_s=2.0,
                speed=1.0,
                skip_error=True,
            )
        self.assertEqual(output["result"][2], "error.mp4")
        self.assertIn("error", output["result"][9])


class SunoWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = sorted(
            (PLUGIN_ROOT / "workflow").glob(
                "suno-*（贞贞的平价AI小屋）.json"
            )
        )

    def test_all_operations_have_one_workflow(self):
        self.assertEqual(len(self.paths), 31)
        selected = []
        for path in self.paths:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            selected.extend(
                node["widgets_values"][0]
                for node in workflow["nodes"]
                if node["type"] == "Comfly_suno_music_lowprice"
            )
        for operation in EXPECTED_OPERATIONS:
            self.assertIn(operation, selected)

    def test_workflows_have_empty_domestic_api_keys_and_no_runtime_data(self):
        for path in self.paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("sk-", text)
            self.assertNotIn("X-Amz-", text)
            workflow = json.loads(text)
            configs = [
                node
                for node in workflow["nodes"]
                if node["type"] == "T8Zhenzhen_API_Settings"
            ]
            self.assertEqual(len(configs), 1)
            self.assertEqual(
                configs[0]["widgets_values"],
                ["seedance_low_price", "", "", False],
            )

    def test_task_actions_are_wired_to_source_nodes(self):
        direct = DIRECT_ACTIONS = {
            "suno-generation",
            "suno-lyrics",
            "suno-upload",
            "suno-inspo",
            "suno-upsample-tags",
            "suno-sounds",
            "suno-create-voice",
        }
        for path in self.paths:
            operation = next(
                item
                for item in sorted(EXPECTED_OPERATIONS, key=len, reverse=True)
                if path.name.startswith(item)
            )
            if operation in direct:
                continue
            workflow = json.loads(path.read_text(encoding="utf-8"))
            targets = [
                node
                for node in workflow["nodes"]
                if node["type"] == "Comfly_suno_music_lowprice"
                and node["widgets_values"][0] == operation
            ]
            self.assertEqual(len(targets), 1)
            task_inputs = [
                input_slot
                for input_slot in targets[0]["inputs"]
                if input_slot["name"] == "task_id"
            ]
            self.assertEqual(len(task_inputs), 1)
            self.assertIsNotNone(task_inputs[0]["link"])

    def test_generate_mp4_uses_a_short_uploaded_audio_source(self):
        path = next(
            path
            for path in self.paths
            if path.name.startswith("suno-generate-mp4")
        )
        workflow = json.loads(path.read_text(encoding="utf-8"))
        selected = [
            node["widgets_values"][0]
            for node in workflow["nodes"]
            if node["type"] == "Comfly_suno_music_lowprice"
        ]
        node_types = {node["type"] for node in workflow["nodes"]}
        self.assertIn("LoadAudio", node_types)
        self.assertIn("suno-upload", selected)
        self.assertIn("suno-generate-mp4", selected)

    def test_registration_and_frontend_support_are_present(self):
        comfly = (PLUGIN_ROOT / "Comfly.py").read_text(encoding="utf-8")
        api_link = (
            PLUGIN_ROOT / "web" / "js" / "zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        action_ui = (
            PLUGIN_ROOT / "web" / "js" / "suno_action_ui.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"Comfly_suno_music_lowprice"', comfly)
        self.assertIn(
            '"Comfly_suno_music_lowprice": "zhenzhen-suno-music-lowprice"',
            comfly,
        )
        self.assertIn('"Comfly_suno_music_lowprice"', api_link)
        self.assertIn(
            'const SUNO_NODE_NAME = "Comfly_suno_music_lowprice"',
            action_ui,
        )


if __name__ == "__main__":
    unittest.main()
