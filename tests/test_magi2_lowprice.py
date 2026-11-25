"""Magi 2 contract, registration and blank-key example tests."""

import json
from unittest import TestCase
from unittest.mock import patch

from nov08_fixture import ROOT, module

magi = module("magi2_low_price_nodes")
transport = module("nov21_low_price_nodes")
node = magi.T8ZhenzhenMagi2Video
IMAGE = magi.api.torch.zeros(1, 32, 32, 3)
PROMPT = "A small blue cube on a white desk."


def audio(seconds):
    return {"waveform": magi.api.torch.zeros(1, 1, seconds * 8000), "sample_rate": 8000}


class Magi2Tests(TestCase):
    def test_text_and_frame_request_fields_for_both_models(self):
        for model in magi.MODELS:
            body, media = magi.prepare({"model": model, "prompt": PROMPT, "seconds": 4, "seed": 0, "generate_audio": False})
            self.assertEqual(body, {"model": model, "prompt": PROMPT, "seconds": "4",
                                   "metadata": {"resolution": "1080p", "generate_audio": False, "seed": 0}})
            self.assertEqual(media, [])
            body, media = magi.prepare({"model": model, "prompt": PROMPT, "generation_type": "frame",
                                       "image2": IMAGE, "image1": IMAGE, "seconds": 30})
            self.assertEqual([(field, name) for field, name, *_ in media],
                             [("images", "magi_image1.png"), ("images", "magi_image2.png")])
            self.assertEqual(body["metadata"]["generation_type"], "frame")
            self.assertNotIn("ratio", body["metadata"])

    def test_auto_and_explicit_reference_mode(self):
        body, _ = magi.prepare({"prompt": PROMPT, "image1": IMAGE})
        self.assertNotIn("generation_type", body["metadata"])
        self.assertNotIn("ratio", body["metadata"])
        body, media = magi.prepare({"prompt": PROMPT, "generation_type": "reference", "image1": IMAGE, "ratio": "21:9"})
        self.assertEqual(body["metadata"]["generation_type"], "reference")
        self.assertEqual(body["metadata"]["ratio"], "21:9")
        self.assertEqual(len(media), 1)
        _, media = magi.prepare({"prompt": PROMPT, "image1": IMAGE, "image2": IMAGE, "image3": IMAGE})
        self.assertEqual(len(media), 3)

    def test_prevalidation_and_invalid_inputs_fail_before_upload(self):
        self.assertIs(node.VALIDATE_INPUTS(prompt=None, generation_type="frame", image1=None), True)
        invalid = [
            {"prompt": " "}, {"prompt": "x" * 15001}, {"seconds": 3}, {"seconds": 31}, {"seconds": "4"},
            {"seed": -1}, {"seed": magi.SEED_MAX + 1}, {"seed": True}, {"ratio": "2:3"},
            {"image11": IMAGE}, {"video6": object()}, {"audio6": audio(2)}, {"generate_audio": "no"},
            {"generation_type": "text", "image1": IMAGE}, {"generation_type": "frame"},
            {"generation_type": "frame", "image2": IMAGE}, {"generation_type": "reference"},
            {"generation_type": "frame", "image1": IMAGE, "audio1": audio(2)},
            {"image1": magi.api.torch.zeros(2, 32, 32, 3)},
        ]
        with patch.object(magi.api, "upload_media") as upload, patch.object(transport, "submit_kling_task") as submit:
            for values in invalid:
                with self.subTest(fields=tuple(values)), self.assertRaises(magi.Error):
                    node().execute(**{"prompt": PROMPT, **values})
            upload.assert_not_called()
            submit.assert_not_called()

    def test_maximum_refs_and_independent_duration_limits(self):
        values = {"prompt": PROMPT, **{f"image{i}": IMAGE for i in range(1, 11)},
                  **{f"video{i}": object() for i in range(1, 6)}, **{f"audio{i}": audio(6) for i in range(1, 6)}}
        with (patch.object(magi.api, "video_to_upload_bytes", return_value=(b"fake", "mp4")),
              patch.object(magi, "probe_video", return_value={"duration": 6.0}) as probe):
            _, media = magi.prepare(values)
            self.assertEqual([field for field, *_ in media], ["images"] * 10 + ["video_url"] * 5 + ["audio_urls"] * 5)
            probe.return_value = {"duration": 6.1}
            with self.assertRaisesRegex(magi.Error, "Total Magi 2 reference video"):
                magi.prepare(values)
        for durations in ([1.99], [30.01], [float("nan")]):
            with self.assertRaisesRegex(magi.Error, "Each"):
                magi.check_durations("audio", durations)
        with self.assertRaisesRegex(magi.Error, "Total Magi 2 reference audio"):
            magi.prepare({"prompt": PROMPT, "audio1": audio(15), "audio2": audio(16)})

    def test_legacy_transport_uses_ordered_media_and_sends_native_seed(self):
        config = {"base_url": magi.api.DEFAULT_BASE_URL, "api_key": "test-key"}
        image_url, video_url, audio_url, output_url = ("https://example.test/" + name
                                                      for name in ("image.png", "clip.mp4", "audio.wav", "output.mp4"))
        final = {"data": {"status": "SUCCESS", "result_url": output_url}}
        with (patch.object(magi.api, "video_to_upload_bytes", return_value=(b"video", "mp4")),
              patch.object(magi, "probe_video", return_value={"duration": 2}),
              patch.object(magi.api, "upload_media", side_effect=[image_url, video_url, audio_url]),
              patch.object(transport, "submit_kling_task", return_value=("fake-task", {})) as submit,
              patch.object(transport, "poll_kling_task", return_value=final) as poll,
              patch.object(magi.api, "download_video", return_value="decoded") as download):
            result = node().execute(api_config=config, model="magi-2-global", prompt=PROMPT, seed=345,
                                    generation_type="reference", image1=IMAGE, video1=object(), audio1=audio(2))["result"]
        body = submit.call_args.args[0]
        self.assertEqual(body["images"], [image_url])
        self.assertEqual(body["metadata"]["video_url"], [video_url])
        self.assertEqual(body["metadata"]["audio_urls"], [audio_url])
        self.assertEqual(body["metadata"]["seed"], 345)
        self.assertEqual(poll.call_args.args[0], "fake-task")
        download.assert_called_once_with(output_url)
        self.assertEqual(result[:3], ("decoded", output_url, "fake-task"))

    def test_registration_and_examples(self):
        plugin, parallel = module("Comfly"), module("ComflyConcurrent")
        parallel_key = f"ComflyConcurrent_{magi.KEY}_Submit"
        self.assertIs(plugin.NODE_CLASS_MAPPINGS[magi.KEY], node)
        wrapper = parallel.CONCURRENT_NODE_CLASS_MAPPINGS[parallel_key]
        self.assertFalse(hasattr(wrapper, "VALIDATE_INPUTS"))
        self.assertEqual(wrapper.INPUT_TYPES(), node.INPUT_TYPES())
        workflows = list((ROOT / "workflow").glob("zhenzhen-magi-2-*-lowprice.json"))
        self.assertEqual(len(workflows), 8)
        for path in workflows:
            graph = json.loads(path.read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in graph["nodes"]}
            self.assertEqual(by_id[1]["widgets_values"], ["seedance_low_price", "", "", False], path.name)
            self.assertIn(by_id[2]["type"], (magi.KEY, parallel_key))
            self.assertEqual(by_id[2]["widgets_values"][:2], [
                "magi-2-global" if "global" in path.name else "magi-2",
                "text" if "t2v" in path.name else "frame" if "i2v" in path.name else "reference",
            ])
            self.assertEqual(by_id[2]["widgets_values"][-2:], ["fixed", False])
            self.assertEqual(graph["nodes"][-1]["type"], "SaveVideo")
            for link, source, output, target, slot, type_ in graph["links"]:
                self.assertIn(link, by_id[source]["outputs"][output]["links"])
                self.assertEqual(by_id[target]["inputs"][slot]["link"], link)
                self.assertEqual(by_id[target]["inputs"][slot]["type"], type_)
