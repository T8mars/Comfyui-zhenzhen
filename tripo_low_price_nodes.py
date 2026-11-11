"""Independent Tripo model and mesh tools on the Low Price channel."""

import json

try:
    from . import tripo_contracts as tripo, tripo_artifacts
    from . import seedance_low_price_nodes as api
    from . import preview_muse_flux_low_price_nodes as common
    from . import image_artifacts
    from .nov05_low_price_nodes import submit_3d, poll_3d
    from .aug22_low_price_nodes import File3D, placeholder_file3d
    from .execution_seed import EXECUTION_SEED_SPEC
except ImportError:
    import tripo_contracts as tripo
    import tripo_artifacts
    import seedance_low_price_nodes as api
    import preview_muse_flux_low_price_nodes as common
    import image_artifacts
    from nov05_low_price_nodes import submit_3d, poll_3d
    from aug22_low_price_nodes import File3D, placeholder_file3d
    from execution_seed import EXECUTION_SEED_SPEC


def download_file(url, filename_prefix, default_extension=None, logger_prefix=None):
    return image_artifacts.download_file(url, "zhenzhen/" + filename_prefix)[0]


class Tripo3DBase:
    CATEGORY = "zhenzhen/Seedance2 Low Price/3D/Tripo"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    FAMILY = "generate"
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True
    RETURN_TYPES = ("FILE_3D",) + ("STRING",) * 7
    RETURN_NAMES = ("model_3d", "model_url", "local_path", "task_id", "tripo_task_id", "files_json", "part_names_json", "response")

    @classmethod
    def INPUT_TYPES(cls):
        required = {"model": (tripo.MODELS[cls.FAMILY], {"default": tripo.MODELS[cls.FAMILY][0]})}
        required.update({field: tripo.FIELDS[field] for field in tripo.FAMILY_FIELDS[cls.FAMILY]})
        optional = {f"image{i}": ("IMAGE", {"tooltip": f"{view}; front/left/back/right; one image per socket"})
                    for i, view in enumerate(tripo.VIEWS, 1)}
        if cls.FAMILY == "texture":
            optional["style_image"] = ("IMAGE", {"tooltip": "Optional style reference for text retexturing"})
        optional.update(api_config=(api.CONFIG_TYPE,), skip_error=("BOOLEAN", {"default": False}), seed=EXECUTION_SEED_SPEC)
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(cls, strict=False, **kwargs):
        if not strict:
            if any(name in kwargs and kwargs[name] is None for name in ("model", "input_mode", "texture_prompt_mode", "seg_type")):
                return True
            kwargs = {key: value for key, value in kwargs.items() if value is not None}
        try:
            tripo.validate(cls.FAMILY, kwargs, strict=strict)
        except api.SeedanceLowPriceError as error:
            return str(error)
        return True

    def execute(self, api_config=None, skip_error=False, seed=0, **kwargs):
        del seed
        try:
            return self._execute_inner(api_config=api_config, **kwargs)
        except Exception as error:
            if not skip_error:
                raise
            response = json.dumps({"error": f"{type(error).__name__}: {error}"}, ensure_ascii=False)
            placeholder = "" if self.FAMILY == "splat" else placeholder_file3d(str(error))
            return {"ui": {"text": [response]}, "result": (placeholder, "", "", "", "", "[]", "[]", response)}

    def _execute_inner(self, api_config=None, **kwargs):
        tripo.validate(self.FAMILY, kwargs, strict=True)
        # A connected blank key must never fall through to environment/config keys.
        if api._unwrap_api_config(api_config) is None:
            raise api.SeedanceLowPriceError("Connect this workflow's Low Price API Settings with a non-empty API key")
        config = api.resolve_config(api_config)
        encoded = []
        for local in tripo.image_roles(self.FAMILY, kwargs):
            if kwargs.get(local) is not None:
                data = common.encode_references({"image1": kwargs[local]}, 1, per_file=tripo.IMAGE_LIMIT)[0][1]
                encoded.append((local, data))
        uploaded = {local: api.upload_media(data, f"tripo_{local}.png", "image/png", config) for local, data in encoded}
        payload = tripo.payload(self.FAMILY, kwargs, uploaded)
        task, _ = submit_3d(payload, config)
        final = poll_3d(task, config)
        main, files, tripo_id, parts = tripo_artifacts.download_results(final, download_file)
        first = main["local_path"] if self.FAMILY == "splat" else File3D(main["local_path"], file_format=main["actual_format"])
        return {"ui": {"text": [main["local_path"]]}, "result": (first, main["url"], main["local_path"], task, tripo_id,
            json.dumps(files, ensure_ascii=False), json.dumps(parts, ensure_ascii=False), json.dumps(final, ensure_ascii=False))}


class T8ZhenzhenTripoGenerate(Tripo3DBase):
    pass


class T8ZhenzhenTripoTexture(Tripo3DBase):
    FAMILY = "texture"


class T8ZhenzhenTripoRetopology(Tripo3DBase):
    FAMILY = "retopology"


class T8ZhenzhenTripoMesh(Tripo3DBase):
    FAMILY = "mesh"


class T8ZhenzhenTripoConvert(Tripo3DBase):
    FAMILY = "convert"


class T8ZhenzhenTripoSplat(Tripo3DBase):
    FAMILY = "splat"
    RETURN_TYPES = ("STRING",) * 8
    RETURN_NAMES = ("splat_path",) + Tripo3DBase.RETURN_NAMES[1:]


TRIPO_CLASSES = {"generate": T8ZhenzhenTripoGenerate, "texture": T8ZhenzhenTripoTexture,
    "retopology": T8ZhenzhenTripoRetopology, "mesh": T8ZhenzhenTripoMesh,
    "convert": T8ZhenzhenTripoConvert, "splat": T8ZhenzhenTripoSplat}
TRIPO_KEYS = {family: f"T8Zhenzhen_Tripo_{family.title()}_LowPrice" for family in TRIPO_CLASSES}
