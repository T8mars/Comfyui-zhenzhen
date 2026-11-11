import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import torch
from PIL import Image

from nov08_fixture import module, ROOT
nodes = module("tripo_low_price_nodes")
api = module("tripo_contracts")
artifacts = module("tripo_artifacts")
geometry = module("aug22_low_price_nodes")
preview_models = module("preview_muse_flux_low_price_nodes")
concurrent_nodes = module("ComflyConcurrent")
SeedanceAPIError = api.SeedanceAPIError
MAPPINGS = {nodes.TRIPO_KEYS[family]: cls for family, cls in nodes.TRIPO_CLASSES.items()}

URL = "https://example.com/model.glb"
CONFIG = {"base_url": "https://api.seedance.nz", "api_key": "sk-test"}
KEYS = nodes.TRIPO_KEYS


def minimal(family, model):
    kwargs = {"model": model}
    if family == "generate":
        if "text-to-3d" in model:
            kwargs["prompt"] = "A simple blue toy robot"
        else:
            kwargs["image1"] = object()
            if "multiview" in model:
                kwargs["image2"] = object()
    elif family in ("texture", "retopology", "convert", "mesh"):
        kwargs["model_url"] = URL
        if family == "texture":
            kwargs["texture_prompt_text"] = "Glossy blue ceramic"
        if model.endswith("retopology-v1"):
            kwargs["face_limit"] = 10000
        if model.endswith("smartsegment"):
            kwargs.pop("model_url")
            kwargs["image1"] = object()
        if model.endswith("mesh-complete"):
            kwargs.pop("model_url")
            kwargs["tripo_segment_task_id"] = "upstream-example"
    else:
        kwargs["image1"] = object()
    return kwargs


def final(files=None, upstream="upstream-example"):
    files = files or [{"name": "modelUrl", "type": "glb", "url": URL}]
    content = {"files": files, "file_url": next(item["url"] for item in files if item["name"] == "modelUrl"),
               "file_urls": [item["url"] for item in files]}
    if upstream is not None:
        content["tripo_task_id"] = upstream
    return {"data": {"task_id": "platform-example", "status": "SUCCESS", "result_url": content["file_url"],
                     "data": {"content": content}}}


class TripoContractTests(unittest.TestCase):
    def test_unique_registrations_use_our_classes(self):
        plugin = module("Comfly")
        for family, key in KEYS.items():
            self.assertIs(plugin.NODE_CLASS_MAPPINGS[key], nodes.TRIPO_CLASSES[family])
            self.assertIn("平价小屋", plugin.NODE_DISPLAY_NAME_MAPPINGS[key])
        self.assertFalse(any(key in plugin.NODE_CLASS_MAPPINGS for key in ("Tripo_Generate", "Tripo_Texture", "Tripo_Mesh")))

    def test_blank_or_missing_workflow_key_cannot_use_environment(self):
        for config in (None, {}, {"base_url": URL, "api_key": ""}):
            with patch.dict(os.environ, {"SEEDANCE_API_KEY": "environment-fixture"}), patch.object(nodes, "submit_3d") as submit:
                with self.assertRaises(SeedanceAPIError):
                    nodes.T8ZhenzhenTripoGenerate().execute(prompt="A toy robot", api_config=config)
                submit.assert_not_called()

    def test_connected_widget_placeholders_defer_until_runtime(self):
        for cls in nodes.TRIPO_CLASSES.values():
            self.assertTrue(cls.VALIDATE_INPUTS(model=None, face_limit=None, model_url=None))
        self.assertTrue(nodes.T8ZhenzhenTripoGenerate.VALIDATE_INPUTS(prompt=None, face_limit=None))
        self.assertIsNot(nodes.T8ZhenzhenTripoGenerate.VALIDATE_INPUTS(strict=True, prompt=None), True)

    def test_all_25_models_have_one_function_group_and_minimal_payload(self):
        models = [model for group in api.MODELS.values() for model in group]
        self.assertEqual(len(models), 25)
        self.assertEqual(len(set(models)), 25)
        for family, group in api.MODELS.items():
            for model in group:
                with self.subTest(model=model):
                    kwargs = minimal(family, model)
                    uploaded = {name: f"https://example.com/{name}.png" for name in api.image_roles(family, kwargs) if name in kwargs}
                    result = api.payload(family, kwargs, uploaded)
                    self.assertEqual(result["model"], model)
                    self.assertNotIn("seed", result)
                    self.assertNotIn("api_key", json.dumps(result))
                    self.assertTrue(api.validate(family, kwargs, strict=True))

    def test_node_registration_seed_skip_and_no_image_video_collector(self):
        for family, key in KEYS.items():
            cls = MAPPINGS[key]
            schema = cls.INPUT_TYPES()
            self.assertEqual(schema["required"]["model"][0], api.MODELS[family])
            self.assertEqual(len(cls.RETURN_TYPES), 8)
            self.assertEqual(cls.RETURN_TYPES[0], "STRING" if family == "splat" else "FILE_3D")
            self.assertFalse(schema["optional"]["skip_error"][1]["default"])
            self.assertTrue(schema["optional"]["seed"][1]["control_after_generate"])
            self.assertTrue(cls.SEEDANCE_EXPLICIT_CACHE_ONLY_SEED)
            self.assertFalse(hasattr(cls, "IS_CHANGED"))
            self.assertNotIn("ComflyConcurrent_" + key + "_Submit", concurrent_nodes.CONCURRENT_NODE_CLASS_MAPPINGS)

    def test_defaults_omit_sentinels_and_native_seeds_are_not_cache_seed(self):
        result = api.payload("generate", {"prompt": "robot", "seed": 99}, {})
        self.assertEqual(result, {"model": api.GENERATE_MODELS[0], "prompt": "robot"})
        result = api.payload("generate", {"prompt": "robot", "model_seed": 0, "image_seed": 42,
                                         "texture_seed": api.MAX_SEED, "texture": "false", "pbr": "true"}, {})
        self.assertEqual(result["metadata"], {"model_seed": 0, "image_seed": 42, "texture_seed": api.MAX_SEED,
                                             "texture": False, "pbr": True})

    def test_model_specific_options_are_omitted_after_switch(self):
        stale = {"geometry_quality": "detailed", "smart_low_poly": "true", "generate_parts": "true", "compress": "geometry",
                 "auto_size": "true", "texture_quality": "extreme", "quad": "true", "negative_prompt": "unused", "image_seed": 4}
        for family, model in (("generate", "tripo-h-v2.5-image-to-3d"), ("texture", "tripo-texture-v2.5")):
            kwargs = {**stale, **minimal(family, model)}
            payload = api.payload(family, kwargs, {"image1": URL})
            for field in ("geometry_quality", "smart_low_poly", "generate_parts", "compress", "quad", "image_seed", "negative_prompt"):
                self.assertNotIn(field, payload.get("metadata", {}))
        p1 = api.payload("generate", {**minimal("generate", "tripo-p-p1-text-to-3d"), "quad": "true", "compress": "geometry"}, {})
        self.assertNotIn("quad", p1["metadata"])
        self.assertEqual(p1["metadata"]["compress"], "geometry")

    def test_face_limits_all_families_and_quad_detailed_combinations(self):
        cases = [("h-v2.5", {}, 1, 500000), ("h-v3.0", {}, 1, 1000000), ("h-v3.1", {}, 1, 1500000),
                 ("h-v3.0", {"geometry_quality": "detailed"}, 1, 2000000),
                 ("h-v3.1", {"quad": "true", "geometry_quality": "detailed"}, 1, 150000),
                 ("p-p1", {}, 50, 20000), ("p-p2", {}, 48, 50000), ("p-p2", {"quad": "true"}, 48, 25000)]
        for variant, options, low, high in cases:
            kwargs = {"model": f"tripo-{variant}-text-to-3d", "prompt": "robot", **options}
            for count in (0, low, high):
                self.assertTrue(api.validate("generate", {**kwargs, "face_limit": count}, strict=True))
            for count in (low - 1 if low > 1 else -1, high + 1, True, 1.5):
                with self.subTest(variant=variant, count=count), self.assertRaises(SeedanceAPIError):
                    api.validate("generate", {**kwargs, "face_limit": count}, strict=True)

    def test_generate_parts_conflict_requires_all_three_disabled(self):
        base = {"prompt": "robot", "generate_parts": "true"}
        for extra in ({}, {"texture": "false"}, {"texture": "false", "pbr": "false", "quad": "true"}):
            with self.assertRaises(SeedanceAPIError):
                api.validate("generate", {**base, **extra}, strict=True)
        result = api.payload("generate", {**base, "texture": "false", "pbr": "false", "quad": "false"}, {})
        self.assertTrue(result["metadata"]["generate_parts"])
        self.assertNotIn("texture_quality", api.active_fields("generate", {**base, "texture": "false", "pbr": "false"}))

    def test_single_and_multiview_references_are_contiguous_in_documented_order(self):
        self.assertEqual(api.VIEWS, ["front", "left", "back", "right"])
        for model in ("tripo-p-p1-image-to-3d", "tripo-h-v3.1-multiview-to-3d"):
            for images in ({}, {"image2": object()}, {"image1": object(), "image3": object()}, {"image5": object()}):
                with self.assertRaises(SeedanceAPIError):
                    api.validate("generate", {"model": model, **images}, strict=True)
        for count in (2, 3, 4):
            kwargs = {"model": "tripo-h-v3.1-multiview-to-3d", **{f"image{i}": object() for i in range(1, count + 1)}}
            uploaded = {f"image{i}": f"https://example.com/view{i}.png" for i in range(1, count + 1)}
            self.assertEqual(api.payload("generate", kwargs, uploaded)["images"], list(uploaded.values()))

    def test_reused_multiview_id_never_sends_images(self):
        kwargs = {"model": "tripo-p-p2-multiview-to-3d", "input_mode": "multiviewTaskId", "multiview_task_id": "upstream-example"}
        self.assertNotIn("images", api.payload("generate", kwargs, {}))
        with self.assertRaises(SeedanceAPIError):
            api.payload("generate", {**kwargs, "image1": object()}, {})
        with self.assertRaises(SeedanceAPIError):
            api.payload("generate", {**kwargs, "multiview_task_id": ""}, {})

    def test_prompt_seed_enum_and_text_type_boundaries(self):
        for kwargs in ({"prompt": ""}, {"prompt": "x"*1025}, {"prompt": 123}, {"prompt": "ok", "negative_prompt": "x"*256},
                       {"prompt": "ok", "model_seed": -2}, {"prompt": "ok", "texture_seed": api.MAX_SEED+1},
                       {"prompt": "ok", "image_seed": True}, {"prompt": "ok", "texture": "yes"}, {"model": "unknown"}):
            with self.assertRaises(SeedanceAPIError):
                api.validate("generate", kwargs, strict=True)
        self.assertTrue(api.validate("generate", {"prompt": None, "negative_prompt": None}, strict=False))

    def test_part_names_csv_array_omit_and_invalid_names(self):
        for value in (None, "", " ", "null", [], "[]"):
            self.assertEqual(api.part_names(value), [])
        for value in ('[" tripo_part_0 ","Part_B"]', " tripo_part_0 , Part_B", ["tripo_part_0", "Part_B"]):
            self.assertEqual(api.part_names(value), ["tripo_part_0", "Part_B"])
        self.assertEqual(api.part_names("x"*1024), ["x"*1024])
        for value in ("x"*1025, '["x","x"]', '["x,y"]', '[""]', '[1]', '["x"', "x,,y", {}, 123):
            with self.subTest(value=str(value)[:40]), self.assertRaises(SeedanceAPIError):
                api.part_names(value)

    def test_texture_three_modes_and_style_mapping(self):
        base = {"model_url": URL}
        result = api.payload("texture", {**base, "texture_prompt_text": "blue ceramic", "style_image": object()}, {"style_image": URL})
        self.assertEqual(result["metadata"]["style_image_url"], URL)
        for mode in ("image", "images"):
            kwargs = {**base, "texture_prompt_mode": mode}
            roles = api.image_roles("texture", kwargs)
            for field in roles:
                kwargs[field] = object()
            uploaded = {field: f"https://example.com/{field}.png" for field in roles}
            result = api.payload("texture", kwargs, uploaded)
            for local, remote in roles.items():
                self.assertEqual(result["metadata"][remote], uploaded[local])
            self.assertNotIn("images", result)
            with self.assertRaises(SeedanceAPIError):
                api.payload("texture", {**kwargs, next(iter(roles)): None}, uploaded)
        with self.assertRaises(SeedanceAPIError):
            api.payload("texture", {**base, "texture_prompt_text": "blue", "style_image": object(), "style_image_url": URL}, {})

    def test_url_texture_sources_and_source_conflict(self):
        kwargs = {"model_url": URL, "texture_prompt_mode": "images", **{f"texture_{view}_image_url": URL for view in api.VIEWS}}
        self.assertTrue(api.validate("texture", kwargs, strict=True))
        with self.assertRaises(SeedanceAPIError):
            api.validate("texture", {**kwargs, "image1": object()}, strict=True)

    def test_segmentation_ref_overrides_options_and_upstream_id_is_distinct(self):
        kwargs = {"model": "tripo-mesh-segment-v2", "model_url": URL, "ref_image_url": URL,
                  "segmentation_granularity": "detailed", "split_by_connectivity": "false"}
        metadata = api.payload("mesh", kwargs, {})["metadata"]
        self.assertEqual(metadata, {"model_url": URL, "ref_image_url": URL})
        self.assertTrue(api.validate("mesh", {"model": kwargs["model"], "model_url": None, "ref_image_url": None}))
        for model in api.MODELS["mesh"]:
            if model.endswith("complete"):
                with self.assertRaises(SeedanceAPIError):
                    api.validate("mesh", {"model": model, "task_id": "platform-example"}, strict=True)

    def test_smart_segmentation_image_model_and_matrix(self):
        base = {"model": "tripo-mesh-smartsegment"}
        local = api.payload("mesh", {**base, "image1": object()}, {"image1": URL})
        self.assertEqual(local["images"], [URL])
        self.assertNotIn("image_url", local["metadata"])
        self.assertTrue(api.validate("mesh", {**base, "image_url": URL}, strict=True))
        self.assertTrue(api.validate("mesh", {**base, "seg_type": "model", "transform": None}, strict=False))
        model = api.payload("mesh", {**base, "seg_type": "model", "model_url": URL}, {})
        self.assertEqual(len(model["metadata"]["transform"].split(",")), 16)
        for matrix in ("1,2,3", ",".join(["nan"]*16), ",".join(["inf"]*16), "bad"):
            with self.assertRaises(SeedanceAPIError):
                api.validate("mesh", {**base, "seg_type": "model", "model_url": URL, "transform": matrix}, strict=True)

    def test_convert_options_dependencies_and_bounds(self):
        kwargs = {"model_url": URL, "format": "FBX", "fbx_preset": "mixamo", "quad": "true", "force_symmetry": "true",
                  "flatten_bottom": "true", "flatten_bottom_threshold": .5, "export_vertex_colors": "true", "bake": "false"}
        metadata = api.payload("convert", kwargs, {})["metadata"]
        self.assertTrue(metadata["force_symmetry"])
        self.assertFalse(metadata["bake"])
        self.assertNotIn("export_vertex_colors", metadata)
        for field, value in (("face_limit", 499), ("face_limit", 2000001), ("texture_size", 255),
                             ("texture_size", 8193), ("scale_factor", 0), ("scale_factor", 1001),
                             ("scale_factor", float("nan")), ("flatten_bottom_threshold", 1.01)):
            with self.assertRaises(SeedanceAPIError):
                api.validate("convert", {**kwargs, field: value}, strict=True)
        plain = api.payload("convert", {"model_url": URL, "force_symmetry": "true", "fbx_preset": "mixamo"}, {})["metadata"]
        self.assertNotIn("force_symmetry", plain)
        self.assertNotIn("fbx_preset", plain)

    def test_retopology_v1_requires_face_count_and_ignores_v2_options(self):
        base = {"model": "tripo-retopology-v1", "model_url": URL, "part_names": "invalid,,parts", "bake": "false"}
        with self.assertRaises(SeedanceAPIError):
            api.payload("retopology", base, {})
        self.assertEqual(api.payload("retopology", {**base, "face_limit": 1}, {})["metadata"], {"model_url": URL, "face_limit": 1})

    def test_http_urls_and_required_tools(self):
        for url in ("file:///model.glb", "ftp://host/model.glb", "https://user:pass@example.com/m.glb", "https://", "https://ex ample.com/x"):
            self.assertFalse(api.http_url(url))
            with self.assertRaises(SeedanceAPIError):
                api.payload("convert", {"model_url": url}, {})
        for family in ("convert", "texture", "retopology"):
            with self.assertRaises(SeedanceAPIError):
                api.payload(family, {}, {})

    def test_splat_requires_one_local_reference(self):
        for kwargs in ({}, {"image2": object()}, {"image1": object(), "image2": object()}):
            with self.assertRaises(SeedanceAPIError):
                api.payload("splat", kwargs, {})
        self.assertEqual(api.payload("splat", {"image1": object(), "model_seed": 0}, {"image1": URL}),
                         {"model": "tripo-image-to-splat", "images": [URL], "metadata": {"model_seed": 0}})

    def test_all_images_validate_encode_and_size_check_before_upload(self):
        image = torch.zeros(1, 4, 4, 3)
        bad = torch.zeros(2, 4, 4, 3)
        kwargs = {"model": "tripo-h-v3.1-multiview-to-3d", "image1": image, "image2": bad}
        with patch.object(nodes.api, "upload_media") as upload:
            with self.assertRaises(SeedanceAPIError):
                nodes.T8ZhenzhenTripoGenerate().execute(api_config=CONFIG, **kwargs)
            upload.assert_not_called()
        with patch.object(preview_models, "image_bytes", return_value=b"large"), patch.object(api, "IMAGE_LIMIT", 4), \
                patch.object(nodes.api, "upload_media") as upload:
            with self.assertRaises(SeedanceAPIError):
                nodes.T8ZhenzhenTripoSplat().execute(image1=image, api_config=CONFIG)
            upload.assert_not_called()

    def test_execute_all_groups_typed_outputs_and_cache_seed_removal(self):
        image = torch.zeros(1, 4, 4, 3)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "result.glb"
            source.write_bytes(geometry.minimal_glb_bytes())
            for family, key in KEYS.items():
                kwargs = minimal(family, api.MODELS[family][0])
                kwargs = {name: image if name.startswith("image") else value for name, value in kwargs.items()}
                with patch.object(nodes.api, "upload_media", return_value=URL), \
                        patch.object(nodes, "submit_3d", return_value=("platform-example", {})) as submit, \
                        patch.object(nodes, "poll_3d", return_value=final()), \
                        patch.object(nodes, "download_file", return_value=str(source)):
                    result = MAPPINGS[key]().execute(api_config=CONFIG, seed=123, **kwargs)["result"]
                self.assertEqual(len(result), 8)
                self.assertEqual(result[1:5], (URL, str(source), "platform-example", "upstream-example"))
                self.assertNotIn("seed", submit.call_args.args[0])
                if family != "splat":
                    self.assertEqual(result[0].format, "glb")
                else:
                    self.assertEqual(result[0], str(source))

    def test_skip_error_all_groups_keeps_output_arity(self):
        for key in KEYS.values():
            cls = MAPPINGS[key]
            with patch.object(cls, "_execute_inner", side_effect=RuntimeError("offline")):
                with self.assertRaises(RuntimeError):
                    cls().execute()
                result = cls().execute(skip_error=True)["result"]
            self.assertEqual(len(result), 8)
            self.assertEqual(result[1:5], ("", "", "", ""))


class TripoArtifactTests(unittest.TestCase):
    def test_manifest_role_not_order_suffix_or_result_mirror(self):
        files = [{"name": "renderedImageUrl", "type": "PNG", "url": "https://example.com/preview.bin"},
                 {"name": "modelUrl", "type": "glb", "url": "https://example.com/download"}]
        response = final(files)
        response["data"]["result_url"] = "https://example.com/mirror.glb"
        result, upstream = artifacts.result_manifest(response)
        self.assertEqual(result[1]["type"], "glb")
        self.assertEqual(upstream, "upstream-example")

    def test_no_upstream_id_fallback_to_platform_task(self):
        self.assertEqual(artifacts.result_manifest(final(upstream=None))[1], "")

    def test_malformed_or_ambiguous_manifest_fails(self):
        responses = [None, {}, {"data": None}, {"data": {"data": []}}, final()]
        responses[-1]["data"]["data"]["content"]["files"].append({"name": "modelUrl", "type": "obj", "url": "https://example.com/other"})
        for response in responses:
            with self.assertRaises(SeedanceAPIError):
                artifacts.result_manifest(response)
        for field, value in (("type", "exe"), ("url", "file:///x"), ("name", None)):
            response = final()
            response["data"]["data"]["content"]["files"][0][field] = value
            with self.assertRaises(SeedanceAPIError):
                artifacts.result_manifest(response)

    def test_manifest_file_lists_must_agree(self):
        for field, value in (("file_url", "https://example.com/different"), ("file_urls", [])):
            response = final()
            response["data"]["data"]["content"][field] = value
            with self.assertRaises(SeedanceAPIError):
                artifacts.result_manifest(response)

    def test_download_main_first_preserves_order_names_and_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            document = {"asset": {"version": "2.0"}, "nodes": [{"name": "tripo_part_0"}, {"name": "Part_B"}, {"name": "Part_B"}]}
            chunk = json.dumps(document).encode()
            chunk += b" " * (-len(chunk) % 4)
            glb = struct.pack("<4sIIII", b"glTF", 2, 20+len(chunk), len(chunk), 0x4E4F534A)+chunk
            calls = []
            def download(url, **kwargs):
                calls.append(url)
                path = Path(directory) / (kwargs["filename_prefix"] + ".bin")
                if url == URL:
                    path.write_bytes(glb)
                else:
                    Image.new("RGB", (2, 2)).save(path, format="PNG")
                return str(path)
            files = [{"name": "renderedImageUrl", "type": "png", "url": "https://example.com/render"},
                     {"name": "modelUrl", "type": "glb", "url": URL}]
            main, saved, upstream, parts = artifacts.download_results(final(files), download)
            self.assertEqual(calls, [URL, "https://example.com/render"])
            self.assertEqual([item["name"] for item in saved], ["renderedImageUrl", "modelUrl"])
            self.assertEqual(parts, ["tripo_part_0", "Part_B"])
            self.assertEqual(Path(main["local_path"]).suffix, ".glb")

    def test_optional_preview_failure_does_not_lose_model(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "model.glb"
            source.write_bytes(geometry.minimal_glb_bytes())
            def download(url, **kwargs):
                if url != URL:
                    raise ConnectionError("offline")
                return str(source)
            files = [{"name": "modelUrl", "type": "glb", "url": URL},
                     {"name": "renderedImageUrl", "type": "png", "url": "https://example.com/render"}]
            main, saved, _, _ = artifacts.download_results(final(files), download)
            self.assertTrue(Path(main["local_path"]).is_file())
            self.assertEqual(saved[1]["download_error"], "ConnectionError")

    def test_main_download_failure_is_not_treated_as_preview_failure(self):
        with self.assertRaises(ConnectionError):
            artifacts.download_results(final(), lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("offline")))

    def test_archive_preserved_instead_of_relabelled_or_extracting_one_part(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.glb"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("part1.glb", geometry.minimal_glb_bytes())
                archive.writestr("part2.glb", geometry.minimal_glb_bytes())
            path, actual = artifacts.validate_file(str(path), "glb")
            self.assertEqual(actual, "zip")
            self.assertEqual(Path(path).suffix, ".zip")
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(len(archive.namelist()), 2)

    def test_known_formats_and_bad_content_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = {"glb": geometry.minimal_glb_bytes(), "gltf": b'{"asset":{"version":"2.0"}}',
                     "fbx": b"Kaydara FBX Binary  \x00", "obj": b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
                     "stl": b"solid sample\nendsolid sample\n", "splat": b"native splat bytes"}
            for format_, data in valid.items():
                path = Path(directory) / ("test." + format_)
                path.write_bytes(data)
                self.assertEqual(artifacts.validate_file(str(path), format_)[1], format_)
            for format_ in ("glb", "gltf", "fbx", "obj", "stl", "zip", "usdz", "3mf"):
                path = Path(directory) / ("bad." + format_)
                path.write_bytes(b"not a valid model")
                with self.assertRaises((SeedanceAPIError, ValueError)):
                    artifacts.validate_file(str(path), format_)

    def test_29_workflows_cover_all_models_and_have_no_keys(self):
        paths = [path for path in (ROOT / "workflow").glob("zhenzhen-tripo-*-lowprice.json")]
        self.assertEqual(len(paths), 29)
        models = set()
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            for node in data["nodes"]:
                if node["type"] in KEYS.values():
                    models.add(node["widgets_values"][0])
                if node["type"] == "T8Zhenzhen_API_Settings":
                    self.assertEqual(node["widgets_values"][1], "")
            for link in data["links"]:
                source = next(node for node in data["nodes"] if node["id"] == link[1])
                target = next(node for node in data["nodes"] if node["id"] == link[3])
                self.assertIn(link[0], source["outputs"][link[2]]["links"])
                self.assertEqual(target["inputs"][link[4]]["link"], link[0])
        self.assertEqual(models, {model for group in api.MODELS.values() for model in group})


if __name__ == "__main__":
    unittest.main()
