"""Tripo public request contracts and model-dependent controls."""

import json
import math
from urllib.parse import urlparse

try:
    from .seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError
    from .preview_muse_flux_low_price_nodes import references
except ImportError:
    from seedance_low_price_nodes import SeedanceLowPriceError as SeedanceAPIError
    from preview_muse_flux_low_price_nodes import references


GENERATE_MODELS = [f"tripo-{family}-{mode}-to-3d" for family in ("h-v3.1", "h-v3.0", "h-v2.5", "p-p2", "p-p1")
                   for mode in ("text", "image", "multiview")]
MODELS = {
    "generate": GENERATE_MODELS,
    "texture": ["tripo-texture-v3.0", "tripo-texture-v2.5"],
    "retopology": ["tripo-retopology-v2", "tripo-retopology-v1"],
    "mesh": ["tripo-mesh-segment-v1", "tripo-mesh-segment-v2", "tripo-mesh-smartsegment", "tripo-mesh-complete"],
    "convert": ["tripo-convert"],
    "splat": ["tripo-image-to-splat"],
}
VIEWS = ["front", "left", "back", "right"]
BOOLEAN = ["api_default", "true", "false"]
MAX_SEED = 2147483647
IMAGE_LIMIT = 20 * 1024 * 1024


def text(default="", multiline=False, tooltip=""):
    return ("STRING", {"default": default, "multiline": multiline, "tooltip": tooltip})


def choice(values, default="api_default"):
    return (values, {"default": default})


def number(default=0, minimum=0, maximum=2147483647):
    return ("INT", {"default": default, "min": minimum, "max": maximum,
                    "tooltip": "-1 omits native seed; 0 omits face/texture-size limits | 原生种子-1不传；面数/纹理尺寸0不传"})


FIELDS = {
    "prompt": text(multiline=True, tooltip="Text-to-3D: up to 1024 characters | 文生3D提示词，最多1024字符"),
    "negative_prompt": text(multiline=True),
    "model_url": text(tooltip="Public source model URL; connect the previous model_url, not task_id | 公网模型文件直链，连接前一节点model_url，不是task_id"),
    "part_names": text(multiline=True, tooltip='JSON string array or comma-separated names; blank selects all | JSON字符串数组或逗号分隔部件名，留空处理全部'),
    "face_limit": number(),
    "model_seed": number(-1, -1, MAX_SEED),
    "texture_seed": number(-1, -1, MAX_SEED),
    "image_seed": number(-1, -1, MAX_SEED),
    "texture_quality": choice(["api_default", "standard", "detailed", "extreme"]),
    "geometry_quality": choice(["api_default", "standard", "detailed"]),
    "texture_alignment": choice(["api_default", "original_image", "geometry"]),
    "orientation": choice(["api_default", "default", "align_image"]),
    "export_orientation": choice(["api_default", "+x", "-x", "+y", "-y"]),
    "compress": choice(["api_default", "geometry"]),
    "input_mode": choice(["views", "multiviewTaskId"], "views"),
    "multiview_task_id": text(tooltip="Tripo multiview task ID, not the platform task ID | Tripo多视图任务ID，不是本站任务ID"),
    "seg_type": choice(["image", "model"], "image"),
    "image_url": text(),
    "ref_image_url": text(),
    "transform": text("1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1", tooltip="Column-major 4x4 matrix, 16 comma-separated numbers | 列主序4x4矩阵，16个逗号分隔数字"),
    "granularity": choice(["api_default", "coarse", "medium", "fine"]),
    "hint": text(),
    "segmentation_granularity": choice(["api_default", "simple", "balanced", "detailed"]),
    "tripo_segment_task_id": text(tooltip="Connect segmentation tripo_task_id, never task_id | 连接分割节点的tripo_task_id，不能连接task_id"),
    "completion_mode": choice(["ai_completion", "quick_cap"], "quick_cap"),
    "texture_prompt_mode": choice(["text", "image", "images"], "text"),
    "texture_prompt_text": text(multiline=True),
    "style_image_url": text(),
    "texture_image_url": text(),
    **{f"texture_{view}_image_url": text() for view in VIEWS},
    "format": choice(["GLTF", "FBX", "USDZ", "OBJ", "STL", "3MF"], "GLTF"),
    "texture_format": choice(["api_default", "JPEG", "PNG", "WEBP"]),
    "texture_size": number(0, 0, 8192),
    "fbx_preset": choice(["api_default", "blender", "3dsmax", "mixamo", "bake_scale"]),
    "flatten_bottom_threshold": ("FLOAT", {"default": 0.01, "min": 0, "max": 1, "step": 0.01}),
    "scale_factor": ("FLOAT", {"default": 1.0, "min": 0.001, "max": 1000, "step": 0.01}),
}
FIELDS["face_limit"][1]["tooltip"] = "0 omits; retopology v1 requires a positive value | 0使用接口默认；重拓扑v1必须填写大于0的面数"
FIELDS["texture_size"][1]["tooltip"] = "0 omits; explicit values 256-8192 | 0使用接口默认；手动值256-8192"
FIELDS["compress"][1]["tooltip"] = "Compressed GLB requires a Meshopt-capable viewer | 压缩GLB需要支持Meshopt的查看器"
BOOL_FIELDS = ("texture", "pbr", "export_uv", "enable_image_autofix", "auto_size", "quad", "smart_low_poly",
               "generate_parts", "bake", "split_by_connectivity", "force_symmetry", "flatten_bottom",
               "pivot_to_center_bottom", "export_vertex_colors", "pack_uv", "with_animation", "animate_in_place")
FIELDS.update({field: choice(BOOLEAN) for field in BOOL_FIELDS})
FAMILY_FIELDS = {
    "generate": ["prompt", "face_limit", "texture", "pbr", "export_uv", "texture_quality", "geometry_quality", "quad",
                 "auto_size", "smart_low_poly", "generate_parts", "compress", "texture_alignment", "orientation", "export_orientation",
                 "input_mode", "multiview_task_id", "enable_image_autofix", "negative_prompt", "image_seed", "model_seed", "texture_seed"],
    "texture": ["model_url", "texture_prompt_mode", "texture_prompt_text", "texture_image_url", *[f"texture_{v}_image_url" for v in VIEWS],
                "style_image_url", "part_names", "pbr", "texture_quality", "texture_alignment", "bake", "texture_seed", "compress"],
    "retopology": ["model_url", "face_limit", "quad", "bake", "part_names"],
    "mesh": ["model_url", "seg_type", "image_url", "transform", "granularity", "hint", "segmentation_granularity",
             "split_by_connectivity", "ref_image_url", "tripo_segment_task_id", "completion_mode", "part_names"],
    "convert": ["model_url", "format", "texture_format", "texture_size", "face_limit", "quad", "force_symmetry", "flatten_bottom",
                "flatten_bottom_threshold", "scale_factor", "pivot_to_center_bottom", "export_vertex_colors", "bake", "pack_uv",
                "fbx_preset", "with_animation", "animate_in_place", "part_names", "export_orientation"],
    "splat": ["model_seed"],
}


def model_for(family, kwargs):
    model = kwargs.get("model", MODELS[family][0])
    if model not in MODELS[family]:
        raise SeedanceAPIError("Unsupported Tripo model for this node")
    return model


def enabled(kwargs, field, default=False):
    value = kwargs.get(field, "api_default")
    return default if value == "api_default" else value is True or value == "true"


def active_fields(family, kwargs):
    model = model_for(family, kwargs)
    fields = set(FAMILY_FIELDS[family])
    if family == "generate":
        hv3 = model.startswith(("tripo-h-v3.0", "tripo-h-v3.1"))
        p1, p2 = model.startswith("tripo-p-p1"), model.startswith("tripo-p-p2")
        text_mode, multi = "text-to-3d" in model, "multiview" in model
        for field in ("prompt", "negative_prompt", "image_seed"):
            if not text_mode:
                fields.discard(field)
        if text_mode:
            fields -= {"texture_alignment", "orientation"}
        if not model.endswith("image-to-3d"):
            fields.discard("enable_image_autofix")
        if not multi:
            fields -= {"input_mode", "multiview_task_id"}
        elif kwargs.get("input_mode", "views") != "multiviewTaskId":
            fields.discard("multiview_task_id")
        if not hv3:
            fields -= {"geometry_quality", "smart_low_poly", "generate_parts"}
        if not (hv3 or p2):
            fields.discard("quad")
        if not (hv3 or p1 or p2):
            fields -= {"texture_quality", "auto_size", "compress"}
        if not (enabled(kwargs, "texture", True) or enabled(kwargs, "pbr", True)):
            fields -= {"texture_quality", "texture_alignment", "orientation", "texture_seed"}
    elif family == "texture":
        mode = kwargs.get("texture_prompt_mode", "text")
        if mode != "text":
            fields -= {"texture_prompt_text", "style_image_url"}
        if mode != "image":
            fields.discard("texture_image_url")
        if mode != "images":
            fields -= {f"texture_{view}_image_url" for view in VIEWS}
        if model.endswith("v2.5"):
            fields.discard("compress")
    elif family == "retopology" and model.endswith("v1"):
        fields -= {"bake", "part_names"}
    elif family == "mesh":
        fields = {"model_url"}
        if model.endswith("segment-v2"):
            fields |= {"ref_image_url"}
            reference = kwargs.get("ref_image_url")
            if (not isinstance(reference, str) or not reference.strip()) and kwargs.get("image1") is None:
                fields |= {"segmentation_granularity", "split_by_connectivity"}
        elif model.endswith("smartsegment"):
            fields |= {"seg_type", "granularity", "hint"}
            if kwargs.get("seg_type", "image") == "image":
                fields.discard("model_url")
                fields.add("image_url")
            else:
                fields.add("transform")
        elif model.endswith("complete"):
            fields = {"tripo_segment_task_id", "completion_mode", "part_names"}
    elif family == "convert":
        if not enabled(kwargs, "quad"):
            fields.discard("force_symmetry")
        if not enabled(kwargs, "flatten_bottom"):
            fields.discard("flatten_bottom_threshold")
        if kwargs.get("format", "GLTF") not in ("OBJ", "GLTF"):
            fields.discard("export_vertex_colors")
        if kwargs.get("format", "GLTF") != "FBX":
            fields.discard("fbx_preset")
    return fields


def http_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.hostname) and parsed.username is None and not any(c.isspace() for c in value)
    except ValueError:
        return False


def part_names(value):
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, str):
        value = value.strip()
        if not value or value == "null":
            return []
        try:
            value = json.loads(value) if value.startswith("[") else value.split(",")
        except ValueError as exc:
            raise SeedanceAPIError("part_names must be a JSON string array or comma-separated names") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SeedanceAPIError("part_names requires strings")
    result = [item.strip() for item in value]
    if any(not item or "," in item for item in result) or len(set(result)) != len(result) or len(",".join(result)) > 1024:
        raise SeedanceAPIError("part_names must be nonempty, unique, comma-free names totaling at most 1024 characters")
    return result


def image_roles(family, kwargs):
    model = model_for(family, kwargs)
    if family == "generate":
        if "text-to-3d" in model or ("multiview" in model and kwargs.get("input_mode", "views") == "multiviewTaskId"):
            return {}
        return {f"image{i}": None for i in range(1, 5 if "multiview" in model else 2)}
    if family == "splat":
        return {"image1": None}
    if family == "texture":
        mode = kwargs.get("texture_prompt_mode", "text")
        if mode == "text":
            return {"style_image": "style_image_url"}
        if mode == "image":
            return {"image1": "texture_image_url"}
        return {f"image{i}": f"texture_{view}_image_url" for i, view in enumerate(VIEWS, 1)}
    if model.endswith("segment-v2"):
        return {"image1": "ref_image_url"}
    if model.endswith("smartsegment") and kwargs.get("seg_type", "image") == "image":
        return {"image1": "image_url"}
    return {}


def validate(family, kwargs, strict=False):
    model = model_for(family, kwargs)
    fields, roles = active_fields(family, kwargs), image_roles(family, kwargs)
    images = references(kwargs, 4)
    for index, _ in images:
        if f"image{index}" not in roles:
            raise SeedanceAPIError("Disconnect image references that do not apply to this Tripo mode")
    if kwargs.get("style_image") is not None and "style_image" not in roles:
        raise SeedanceAPIError("style_image applies only to text-driven retexturing")
    for field in fields:
        value = kwargs.get(field, FIELDS[field][1]["default"])
        if field == "part_names":
            part_names(value)
            continue
        spec, options = FIELDS[field]
        if isinstance(spec, list):
            if value not in spec:
                raise SeedanceAPIError(f"Unsupported Tripo {field}")
        elif spec == "STRING":
            if value is None and not strict:
                continue
            if not isinstance(value, str):
                raise SeedanceAPIError(f"{field} must be text")
            if field.endswith("_url") and value.strip() and not http_url(value.strip()):
                raise SeedanceAPIError(f"{field} must be a public HTTP(S) URL")
        elif spec in ("INT", "FLOAT"):
            if isinstance(value, bool) or not isinstance(value, int if spec == "INT" else (int, float)) or not math.isfinite(value):
                raise SeedanceAPIError(f"{field} must be a finite {spec.lower()}")
            if not options["min"] <= value <= options["max"]:
                raise SeedanceAPIError(f"{field} is outside its supported range")
    for local, remote in roles.items():
        if remote and kwargs.get(local) is not None and (kwargs.get(remote) or "").strip():
            raise SeedanceAPIError(f"Choose {local} OR {remote}, not both")
    if "prompt" in fields:
        prompt = kwargs.get("prompt", "")
        if len(prompt or "") > 1024 or (strict and not (prompt or "").strip()):
            raise SeedanceAPIError("Text-to-3D requires 1-1024 prompt characters")
    if "negative_prompt" in fields and len(kwargs.get("negative_prompt") or "") > 255:
        raise SeedanceAPIError("negative_prompt must not exceed 255 characters")
    count = kwargs.get("face_limit", 0)
    if family == "generate" and count:
        if model.startswith("tripo-p-p1"):
            lower, upper = 50, 20000
        elif model.startswith("tripo-p-p2"):
            lower, upper = 48, 25000 if enabled(kwargs, "quad") else 50000
        else:
            lower = 1
            upper = 500000 if "v2.5" in model else 1000000 if "v3.0" in model else 1500000
            if "geometry_quality" in fields and kwargs.get("geometry_quality") == "detailed":
                upper = 2000000
            if "quad" in fields and enabled(kwargs, "quad"):
                upper = 150000
        if not lower <= count <= upper:
            raise SeedanceAPIError(f"face_limit for this model/options must be {lower}-{upper}, or 0 to omit")
    if family == "convert" and count and not 500 <= count <= 2000000:
        raise SeedanceAPIError("Conversion face_limit must be 500-2000000 or 0 to omit")
    if "texture_size" in fields and 0 < kwargs.get("texture_size", 0) < 256:
        raise SeedanceAPIError("texture_size must be 256-8192 or 0 to omit")
    if "generate_parts" in fields and enabled(kwargs, "generate_parts"):
        if enabled(kwargs, "texture", True) or enabled(kwargs, "pbr", True) or enabled(kwargs, "quad"):
            raise SeedanceAPIError("generate_parts requires texture=false, pbr=false and quad=false")
    if "transform" in fields and (strict or kwargs.get("transform", "") is not None):
        try:
            matrix = [float(item.strip()) for item in kwargs.get("transform", FIELDS["transform"][1]["default"]).split(",")]
        except (ValueError, AttributeError) as exc:
            raise SeedanceAPIError("transform requires 16 comma-separated numbers") from exc
        if len(matrix) != 16 or not all(math.isfinite(value) for value in matrix):
            raise SeedanceAPIError("transform requires 16 finite column-major numbers")
    if not strict:
        return True
    if family == "generate" and "text-to-3d" not in model:
        if "multiview" in model and kwargs.get("input_mode", "views") == "multiviewTaskId":
            if not kwargs.get("multiview_task_id", "").strip():
                raise SeedanceAPIError("A Tripo multiview_task_id is required")
        else:
            indexes = [index for index, _ in images]
            valid = 2 <= len(indexes) <= 4 if "multiview" in model else indexes == [1]
            if not valid or indexes != list(range(1, len(indexes) + 1)):
                raise SeedanceAPIError("Connect one image, or 2-4 contiguous front/left/back/right views for multiview")
    if family == "splat" and [index for index, _ in images] != [1]:
        raise SeedanceAPIError("Image-to-Splat requires exactly image1")
    for required in ("model_url", "tripo_segment_task_id"):
        if required in fields and not kwargs.get(required, "").strip():
            raise SeedanceAPIError(f"{required} is required")
    if family == "retopology" and model.endswith("v1") and not count:
        raise SeedanceAPIError("Retopology v1 requires a positive face_limit")
    if family == "texture":
        mode = kwargs.get("texture_prompt_mode", "text")
        if mode == "text" and not kwargs.get("texture_prompt_text", "").strip():
            raise SeedanceAPIError("Text retexturing requires texture_prompt_text")
        if mode in ("image", "images") and any(kwargs.get(local) is None and not kwargs.get(remote, "").strip() for local, remote in roles.items()):
            raise SeedanceAPIError("Supply every required retexturing image locally or by public URL")
    if model.endswith("smartsegment") and kwargs.get("seg_type", "image") == "image":
        if kwargs.get("image1") is None and not kwargs.get("image_url", "").strip():
            raise SeedanceAPIError("Image smart segmentation requires image1 or image_url")
    return True


def payload(family, kwargs, uploaded):
    validate(family, kwargs, strict=True)
    model, fields = model_for(family, kwargs), active_fields(family, kwargs)
    result, metadata = {"model": model}, {}
    for field in fields:
        value = kwargs.get(field, FIELDS[field][1]["default"])
        if field == "prompt":
            result["prompt"] = value.strip()
        elif field == "part_names":
            selected = part_names(value)
            if selected:
                metadata[field] = selected
        elif field in BOOL_FIELDS:
            if value != "api_default":
                metadata[field] = value == "true"
        elif value not in (None, "", "api_default"):
            if (field in ("face_limit", "texture_size") and value == 0) or (field.endswith("_seed") and value == -1):
                continue
            metadata[field] = value.strip() if isinstance(value, str) else value
    images = []
    for local, remote in image_roles(family, kwargs).items():
        if local not in uploaded:
            continue
        if remote:
            metadata[remote] = uploaded[local]
        else:
            images.append(uploaded[local])
    if images:
        result["images"] = images
    if model.endswith("smartsegment") and kwargs.get("seg_type", "image") == "image" and "image1" in uploaded:
        metadata.pop("image_url", None)
        result["images"] = [uploaded["image1"]]
    if metadata:
        result["metadata"] = metadata
    return result
