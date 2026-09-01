import importlib
import json
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import torch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "zhenzhen_aug22_test_package"
if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[PACKAGE_NAME] = package

advanced = importlib.import_module(f"{PACKAGE_NAME}.aug22_low_price_nodes")
legacy = importlib.import_module(f"{PACKAGE_NAME}.seedance_low_price_nodes")
from generate_aug22_workflows import SOURCE_FILES

CONFIG = {"base_url": "https://example.test", "api_key": "test-key"}
IMAGE = torch.zeros((1, 8, 8, 3), dtype=torch.float32)


class OmniFlashLowpriceTests(unittest.TestCase):
    def test_payloads_match_all_four_modes(self):
        node = advanced.Comfly_zhenzhen_video_g_omni_flash_lowprice_v2()
        common = {
            "mode": "text",
            "prompt": "a paper airplane crosses a quiet studio",
            "seconds": "4",
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "nsfw_check": False,
        }
        self.assertEqual(
            node.build_payload(common, {}),
            {
                "model": "zhenzhen-video-g-omni-flash-lowprice",
                "prompt": common["prompt"],
                "seconds": "4",
                "resolution": "720p",
                "aspect_ratio": "16:9",
                "nsfw_check": False,
            },
        )
        frame = node.build_payload(
            {**common, "mode": "frame"}, {"images": ["front"]}
        )
        self.assertEqual(frame["generation_type"], "frame")
        self.assertEqual(frame["images"], ["front"])
        reference = node.build_payload(
            {**common, "mode": "reference_images"},
            {"images": ["one", "two", "three"]},
        )
        self.assertEqual(reference["generation_type"], "reference")
        self.assertEqual(reference["images"], ["one", "two", "three"])
        video = node.build_payload(
            {**common, "mode": "reference_video"},
            {"video_url": "https://example.test/reference.mp4"},
        )
        self.assertNotIn("seconds", video)
        self.assertNotIn("generation_type", video)
        self.assertEqual(
            video["metadata"],
            {"video_url": "https://example.test/reference.mp4"},
        )

    def test_strict_media_validation_and_legacy_schema_are_preserved(self):
        base = {
            "prompt": "a valid prompt",
            "seconds": "6",
            "resolution": "720p",
            "aspect_ratio": "16:9",
        }
        self.assertIs(
            advanced.Comfly_zhenzhen_video_g_omni_flash_lowprice_v2.VALIDATE_INPUTS(
                **base, mode="frame", image1=object(), strict=True
            ),
            True,
        )
        self.assertIn(
            "exactly image1",
            advanced.Comfly_zhenzhen_video_g_omni_flash_lowprice_v2.VALIDATE_INPUTS(
                **base, mode="frame", image2=object(), strict=True
            ),
        )
        self.assertIn(
            "exactly one",
            advanced.Comfly_zhenzhen_video_g_omni_flash_lowprice_v2.VALIDATE_INPUTS(
                **base,
                mode="reference_video",
                input_video=object(),
                video_url="https://example.test/reference.mp4",
                strict=True,
            ),
        )
        old_required = legacy.Comfly_zhenzhen_video_g_omni_flash_lowprice.INPUT_TYPES()[
            "required"
        ]
        self.assertEqual(list(old_required), ["prompt", "resolution", "ratio"])
        self.assertEqual(
            legacy.ZHENZHEN_VIDEO_G_OMNI_FLASH_MODEL,
            "zhenzhen-video-g-omni-flash",
        )

    def test_omni_11_reuses_the_contract_with_its_own_model_id(self):
        common = {
            "mode": "text",
            "prompt": "a paper airplane crosses a quiet studio",
            "seconds": "4",
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "nsfw_check": False,
        }
        original = (
            advanced.Comfly_zhenzhen_video_g_omni_flash_lowprice_v2.build_payload(
                common, {}
            )
        )
        omni_11 = (
            advanced.Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice.build_payload(
                common, {}
            )
        )
        self.assertEqual(
            omni_11["model"],
            "zhenzhen-video-g-omni-1.1-flash-lowprice",
        )
        self.assertEqual(
            {key: value for key, value in omni_11.items() if key != "model"},
            {key: value for key, value in original.items() if key != "model"},
        )
        self.assertEqual(
            original["model"],
            "zhenzhen-video-g-omni-flash-lowprice",
        )


class Hunyuan3DTests(unittest.TestCase):
    def test_models_limits_and_contiguous_views(self):
        node = advanced.Comfly_hunyuan3d_v3_1_lowprice
        self.assertEqual(len(advanced.HUNYUAN3D_MODELS), 2)
        self.assertIn(
            "face_count",
            node.VALIDATE_INPUTS(
                model=advanced.HUNYUAN3D_TEXT_MODEL,
                prompt="teapot",
                face_count=9999,
                generate_type="Normal",
                strict=True,
            ),
        )
        self.assertIn(
            "prompt is required",
            node.VALIDATE_INPUTS(
                model=advanced.HUNYUAN3D_IMAGE_MODEL,
                prompt="",
                face_count=10000,
                generate_type="Geometry",
                image1=object(),
                strict=True,
            ),
        )
        self.assertIn(
            "contiguously",
            node.VALIDATE_INPUTS(
                model=advanced.HUNYUAN3D_IMAGE_MODEL,
                prompt="a black cat bust",
                face_count=10000,
                generate_type="Geometry",
                image2=object(),
                strict=True,
            ),
        )

    def test_text_execution_returns_file3d_contract(self):
        node = advanced.Comfly_hunyuan3d_v3_1_lowprice()
        final = {
            "data": {
                "status": "SUCCESS",
                "result_url": "https://example.test/model.glb",
            }
        }
        marker = object()
        with patch.object(advanced, "resolve_config", return_value=CONFIG), patch.object(
            advanced,
            "submit_3d_task",
            return_value=("task-test", {"id": "task-test"}),
        ) as submit, patch.object(
            advanced, "poll_3d_task", return_value=final
        ), patch.object(
            advanced, "download_glb", return_value="C:/temp/model.glb"
        ), patch.object(
            advanced, "file3d_from_path", return_value=marker
        ):
            output = node.generate(
                model=advanced.HUNYUAN3D_TEXT_MODEL,
                prompt="a ceramic teapot",
                face_count=10000,
                enable_pbr=False,
                generate_type="Normal",
            )
        payload = submit.call_args.args[0]
        self.assertEqual(payload["face_count"], 10000)
        self.assertNotIn("images", payload)
        self.assertIs(output["result"][0], marker)
        self.assertEqual(output["result"][2], "C:/temp/model.glb")

    def test_glb_integrity_and_url_preference(self):
        data = advanced.minimal_glb_bytes("test")
        self.assertEqual(data[:4], b"glTF")
        self.assertEqual(struct.unpack("<I", data[8:12])[0], len(data))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.glb"
            path.write_bytes(data)
            advanced._validate_glb(str(path))
            model = advanced.file3d_from_path(str(path))
            self.assertEqual(model.format, "glb")
            self.assertEqual(model.get_bytes()[:4], b"glTF")
        response = {
            "data": {
                "result_url": "https://example.test/package.zip",
                "data": {
                    "content": {
                        "file_urls": [
                            "https://example.test/package.zip",
                            "https://example.test/model.glb",
                        ]
                    }
                },
            }
        }
        self.assertEqual(
            advanced.extract_3d_url(response),
            "https://example.test/model.glb",
        )


class GKV2ToolTests(unittest.TestCase):
    def test_segment_extracts_image_id_and_objects(self):
        node = advanced.Comfly_zhenzhen_image_gk_v2_segment_lowprice()
        final = {
            "data": {
                "status": "SUCCESS",
                "content": {
                    "result": {
                        "image_id": "image-test",
                        "objects": [{"label": "bag"}],
                    }
                },
            }
        }
        with patch.object(advanced, "resolve_config", return_value=CONFIG), patch.object(
            advanced,
            "submit_image_task",
            return_value=("task-test", {"id": "task-test"}),
        ) as submit, patch.object(
            advanced, "poll_image_task", return_value=final
        ):
            output = node.segment("source-test", True)
        self.assertEqual(
            submit.call_args.args[0],
            {
                "model": "zhenzhen-image-gk-v2-segment",
                "operation": "segment",
                "source_task_id": "source-test",
                "include_mask_rle": True,
            },
        )
        self.assertEqual(output["result"][0], "image-test")
        self.assertEqual(json.loads(output["result"][1]), [{"label": "bag"}])

    def test_region_edit_sends_exactly_one_selection_structure(self):
        node = advanced.Comfly_zhenzhen_image_gk_v2_region_edit_lowprice()
        self.assertEqual(node.parse_selection("object_indices", "[0, 2]"), [0, 2])
        self.assertEqual(
            node.parse_selection("boxes", "[[1, 2, 3, 4]]"),
            [[1, 2, 3, 4]],
        )
        self.assertEqual(
            node.parse_selection("selection_regions", '[{"x": 1}]'),
            [{"x": 1}],
        )
        with self.assertRaisesRegex(legacy.SeedanceLowPriceError, "non-negative"):
            node.parse_selection("object_indices", '["0"]')

        final = {
            "data": {
                "status": "SUCCESS",
                "result_url": "https://example.test/edit.png",
            }
        }
        with patch.object(advanced, "resolve_config", return_value=CONFIG), patch.object(
            advanced,
            "submit_image_task",
            return_value=("task-test", {"id": "task-test"}),
        ) as submit, patch.object(
            advanced, "poll_image_task", return_value=final
        ), patch.object(
            advanced, "download_image", return_value=IMAGE
        ):
            output = node.edit(
                image_id="image-test",
                prompt="replace the selected object",
                selection_mode="object_indices",
                selection_json="[0]",
            )
        payload = submit.call_args.args[0]
        self.assertEqual(payload["object_indices"], [0])
        self.assertNotIn("boxes", payload)
        self.assertNotIn("selection_regions", payload)
        self.assertTrue(torch.equal(output[0], IMAGE))


class FrontendTests(unittest.TestCase):
    def test_dynamic_ui_keeps_user_json_and_handles_concurrent_nodes(self):
        source = (PLUGIN_ROOT / "web" / "js" / "aug22_low_price_ui.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("MODE_DEFAULTS", source)
        self.assertIn("knownDefault", source)
        self.assertIn("ComflyConcurrent_", source)
        self.assertIn("setZhenzhenInputVisible", source)
        self.assertIn("setZhenzhenWidgetVisible", source)
        self.assertIn(
            "Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice",
            source,
        )

        api_link = (
            PLUGIN_ROOT / "web" / "js" / "zhenzhen_image_g2_api_key_link.js"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice",
            api_link,
        )


class WorkflowTests(unittest.TestCase):
    def test_all_examples_are_connected_and_secret_free(self):
        for filename in SOURCE_FILES:
            with self.subTest(workflow=filename):
                source = (PLUGIN_ROOT / "workflow" / filename).read_text(
                    encoding="utf-8"
                )
                self.assertNotIn("sk-", source)
                workflow = json.loads(source)
                config = next(
                    node
                    for node in workflow["nodes"]
                    if node["type"] == "T8Zhenzhen_API_Settings"
                )
                self.assertEqual(
                    config["widgets_values"],
                    ["seedance_low_price", "", "", False],
                )
                node_by_id = {node["id"]: node for node in workflow["nodes"]}
                link_ids = {link[0] for link in workflow["links"]}
                for node in workflow["nodes"]:
                    for output in node.get("outputs") or []:
                        for link_id in output.get("links") or []:
                            self.assertIn(link_id, link_ids)
                for link_id, origin_id, origin_slot, target_id, target_slot, _ in workflow[
                    "links"
                ]:
                    self.assertIn(
                        link_id,
                        node_by_id[origin_id]["outputs"][origin_slot].get("links")
                        or [],
                    )
                    self.assertEqual(
                        node_by_id[target_id]["inputs"][target_slot].get("link"),
                        link_id,
                    )

    def test_3d_and_region_examples_show_complete_native_chains(self):
        for filename in (
            "hunyuan3d-v3.1-text-to-3d文生3D.json",
            "hunyuan3d-v3.1-image-to-3d图生3D.json",
        ):
            workflow = json.loads(
                (PLUGIN_ROOT / "workflow" / filename).read_text(encoding="utf-8")
            )
            node_types = {node["type"] for node in workflow["nodes"]}
            self.assertIn("Preview3D", node_types)
            self.assertIn("SaveGLB", node_types)
        region = json.loads(
            (
                PLUGIN_ROOT
                / "workflow"
                / "zhenzhen-image-gk-v2-region-edit分割区域编辑.json"
            ).read_text(encoding="utf-8")
        )
        node_types = {node["type"] for node in region["nodes"]}
        self.assertTrue(
            {
                "Comfly_zhenzhen_image_gk_v2_lowprice",
                "Comfly_zhenzhen_image_gk_v2_segment_lowprice",
                "Comfly_zhenzhen_image_gk_v2_region_edit_lowprice",
                "SaveImage",
            }.issubset(node_types)
        )


if __name__ == "__main__":
    unittest.main()
