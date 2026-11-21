"""Documented Low Price contracts and regression coverage; no paid calls."""

import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from nov08_fixture import ROOT, module

nodes = module("nov21_low_price_nodes")
api, spec, h3 = nodes.api, nodes.spec, nodes.h3
llm = module("llm_low_price_presets")


class November21Tests(TestCase):
    def test_long_image_roles_limits_and_connected_prompt(self):
        self.assertTrue(nodes.T8ZhenzhenKlingLongImage.VALIDATE_INPUTS(prompt=None, image1=None))
        payload, used = spec.long_image({"skill": "webpage", "subject_image": "subject",
                                        "style_image": "style", "prompt": "Use @Image1 and @Image2"}, True)
        self.assertEqual(used, [("style", "style"), ("subject", "subject")])
        self.assertNotIn("length", payload)
        with self.assertRaisesRegex(nodes.Error, "product images"):
            spec.long_image({"skill": "webpage", "prompt": "Webpage", "image1": object()}, True)
        with self.assertRaisesRegex(nodes.Error, "at least one"):
            spec.long_image({"prompt": "Page"}, True)
        with self.assertRaisesRegex(nodes.Error, "@Image"):
            spec.long_image({"prompt": "Product @Image2", "image1": object()}, True)
        with self.assertRaisesRegex(nodes.Error, "aspect ratio"):
            spec.long_image_bytes(api.torch.zeros(1, 300, 800, 3), "image1")

    def test_long_image_submits_roles_and_downloads_one(self):
        node = nodes.T8ZhenzhenKlingLongImage()
        config = {"api_key": "test", "base_url": api.DEFAULT_BASE_URL}
        body, refs = node.prepare({"prompt": "Use @Image1", "skill": "webpage",
                                   "style_image": api.torch.zeros(1, 300, 300, 3)})
        asset = {"data": {"status": "SUCCESS", "result_url": "https://example.test/page.png"}}
        with (patch.object(api, "upload_media", return_value="https://example.test/style.png"),
              patch.object(api, "submit_image_task", return_value=("task_example", {})) as submit,
              patch.object(api, "poll_image_task", return_value=asset),
              patch.object(api, "download_image", return_value="image")):
            result = node.run((body, refs), config, lambda _: None)["result"]
        self.assertEqual(submit.call_args.args[0]["image_with_roles"], [{"role": "style", "url": "https://example.test/style.png"}])
        self.assertFalse(submit.call_args.kwargs["retry_server_errors"])
        self.assertEqual(result[:3], ("image", "https://example.test/page.png", "task_example"))

    def test_gemini_contract(self):
        self.assertEqual(len(set(spec.GEMINI_VOICES)), 30)
        default = spec.gemini_tts({"prompt": "Hi", "voice": "kore", "instructions": "Read calmly."}, True)
        self.assertEqual(default, {"model": spec.GEMINI_TTS[1], "prompt": "Hi",
                                   "metadata": {"format": "wav", "voice": "Kore", "instructions": "Read calmly."}})
        for change in ({"prompt": "p" * 5001}, {"voice": "unlisted"}, {"instructions": "p" * 1001}):
            with self.subTest(change=list(change)), self.assertRaises(nodes.Error):
                spec.gemini_tts({"prompt": "Hi", **change}, True)

    def test_h3_token_profiles_duration_constraints(self):
        for kind, cls in ((kind, nodes.CLASSES[kind]) for kind in h3.PROFILES):
            _, images, audio, video, _ = h3.PROFILES[kind]
            self.assertEqual(len([key for key in cls.INPUT_TYPES()["optional"] if key.startswith("image")]), images)
            self.assertTrue(cls.VALIDATE_INPUTS(prompt=None, image1=None))
            kwargs = {"prompt": "<Picture 1> smiles", "image1": object(), "seed": 12345}
            if kind == "digital":
                kwargs["audio1"] = object()
            if kind == "charswap":
                kwargs.update(video_urls="https://example.test/source.mp4", frames=22, duration_mode="frames")
            body, refs = cls.plan(kwargs, True)
            self.assertEqual(body["model"], h3.PROFILES[kind][0])
            self.assertNotIn("seed", body)
            self.assertNotIn("resolution", body["metadata"])
            self.assertEqual(len(refs["audio_urls"]), int(kind == "digital"))
            if kind == "charswap":
                self.assertEqual(body["metadata"], {"ratio": "auto", "frames": 22, "video_url": ["https://example.test/source.mp4"]})
                self.assertNotIn("seconds", body)
            else:
                self.assertEqual(body["seconds"], "5")
            self.assertEqual(sum(key.startswith("audio") for key in cls.INPUT_TYPES()["optional"]), audio)
            self.assertEqual(sum(key.startswith("video") and key != "video_urls" for key in cls.INPUT_TYPES()["optional"]), video)
        with self.assertRaisesRegex(nodes.Error, "exactly one source"):
            h3.plan("charswap", {"prompt": "Change", "image1": object()}, True)
        with self.assertRaisesRegex(nodes.Error, "cover"):
            spec.audio_bytes({"waveform": api.torch.zeros(1, 1, 32001), "sample_rate": 16000}, max_seconds=2)

    def test_heygen_text_and_audio_are_mutually_exclusive(self):
        text = spec.heygen({"prompt": "Welcome"}, True)
        self.assertEqual(text["prompt"], "Welcome")
        self.assertEqual(text["metadata"]["voice"], "Warm Pro Narrator")
        url = "https://example.test/speech.wav"
        driven = spec.heygen({"prompt": "Ignored", "voice": "Ignored", "audio_url": url}, True)
        self.assertNotIn("prompt", driven)
        self.assertNotIn("voice", driven["metadata"])
        self.assertEqual(driven["metadata"]["audio_urls"], [url])
        with self.assertRaisesRegex(nodes.Error, "not both"):
            spec.heygen({"audio_url": url, "audio": object()}, True)
        with self.assertRaisesRegex(nodes.Error, "HTTPS"):
            spec.heygen({"audio_url": url.replace("https", "http")}, True)

    def test_miora_outputs_all_artifacts_before_selecting_preview(self):
        urls = [f"https://example.test/model.{extension}" for extension in ("glb", "zip", "mtl", "png")]
        payload, refs = spec.miora({"image1": object(), "image2": object(),
                                    "prompt": "Ignored", "enable_pbr": True, "generate_type": "geometry"}, True)
        self.assertEqual(list(payload), ["model", "generate_type", "face_count"])
        self.assertEqual([index for index, _ in refs], [1, 2])
        with self.assertRaisesRegex(nodes.Error, "without leaving holes"):
            spec.miora({"image2": object()}, True)
        with tempfile.TemporaryDirectory() as folder:
            paths = [str(Path(folder) / url.rsplit("/", 1)[1]) for url in urls]
            final = {"data": {"data": {"content": {"file_urls": urls}}, "result_url": urls[0]}}
            with (patch.object(nodes, "submit_3d", return_value=("task_example", {})),
                  patch.object(nodes, "poll_3d", return_value=final),
                  patch.object(nodes, "download_file", side_effect=[(path, {}, None) for path in paths]) as download,
                  patch.object(nodes, "prepare_model", return_value=(paths[0], "glb")) as inspect,
                  patch.object(nodes, "File3D", return_value="preview")):
                output = nodes.T8ZhenzhenMiora3D().run((payload, []), {}, lambda _: None)["result"]
            self.assertEqual([call.args[0] for call in download.call_args_list], urls)
            inspect.assert_called_once_with(paths[0])
            self.assertEqual(output[:4], ("preview", urls[0], paths[0], "task_example"))
            self.assertEqual([entry["local_path"] for entry in json.loads(output[4])], paths)

    def test_llm_preserves_requested_preset_but_uses_documented_hy4_id(self):
        import openai

        client = MagicMock()
        client.chat.completions.create.return_value.choices[0].message.content = "OK"
        with patch.object(openai, "OpenAI", return_value=client):
            self.assertEqual(llm.call_g62("zhenzhen/hy-4-flash", "Say OK", "", api_key="test"), "OK")
        self.assertEqual(client.chat.completions.create.call_args.kwargs["model"], "tencent/hy4-flash")
        self.assertEqual(llm.PRESETS[-4:], ["zhenzhen/gm-4-hydrogen", "zhenzhen/gm-4-carbon", "zhenzhen/gm-4-neon", "zhenzhen/hy-4-flash"])

    def test_examples_have_blank_keys_and_registered_types(self):
        mapping = module("Comfly").NODE_CLASS_MAPPINGS
        parallel = module("ComflyConcurrent").CONCURRENT_NODE_CLASS_MAPPINGS
        self.assertEqual(len(nodes.CLASSES), 8)
        for kind, cls in nodes.CLASSES.items():
            self.assertIs(mapping[nodes.KEYS[kind]], cls)
            self.assertEqual("ComflyConcurrent_" + nodes.KEYS[kind] + "_Submit" in parallel, kind not in ("tts", "miora"))
        candidates = [path for path in (ROOT / "workflow").glob("*-lowprice.json")
                      if path.name.startswith(("kling-v4-long-image-", "heygen-avatar-6-", "miora-3d-",
                                               "zhenzhen-gm-2.5-", "zhenzhen-gm-4-", "zhenzhen-hy-4-"))
                      or "-token-" in path.name and path.name.startswith("minimax-h3-comfyui-")]
        self.assertEqual(len(candidates), 26)
        for path in candidates:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            graph_nodes = {node["id"]: node for node in workflow["nodes"]}
            self.assertEqual(graph_nodes[1]["widgets_values"], ["seedance_low_price", "", "", False], path.name)
            for identifier, source, output, target, index, typ in workflow["links"]:
                self.assertIn(identifier, graph_nodes[source]["outputs"][output]["links"], path.name)
                self.assertEqual(graph_nodes[target]["inputs"][index]["link"], identifier, path.name)
                self.assertEqual(graph_nodes[target]["inputs"][index]["type"], typ)
