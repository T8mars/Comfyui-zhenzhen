import { app } from "../../../scripts/app.js";

const NODE_NAME = "Comfly_midjourney_lowprice";
const CONVERTED_WIDGET_PREFIX = "converted-widget";
const ALWAYS_VISIBLE = new Set(["operation", "skip_error"]);
const IMAGE_FIELDS = [
    "image1", "image_url1",
    "image2", "image_url2",
    "image3", "image_url3",
    "image4", "image_url4",
];
const STRUCTURED_FIELDS = [
    "quality", "style", "version", "seed", "negative_prompt",
    "stylize", "chaos", "weird", "tile", "niji", "iw", "cw", "sw",
    "cref", "sref", "dref", "dw", "repeat", "raw", "draft", "hd",
    "stop", "extra",
];

function originalNodeName(name) {
    const prefix = "ComflyConcurrent_";
    const suffix = "_Submit";
    if (name.startsWith(prefix) && name.endsWith(suffix)) {
        return name.slice(prefix.length, -suffix.length);
    }
    return name;
}

const ACTION_FIELDS = {
    "midjourney-imagine": [
        "prompt", "speed", "size", ...STRUCTURED_FIELDS, ...IMAGE_FIELDS,
        "metadata_json",
    ],
    "midjourney-blend": [
        "speed", "size", "dimensions", ...IMAGE_FIELDS, "metadata_json",
    ],
    "midjourney-describe": [
        "speed", "image1", "image_url1", "metadata_json",
    ],
    "midjourney-edits": [
        "prompt", "speed", "size", ...STRUCTURED_FIELDS, ...IMAGE_FIELDS,
        "metadata_json",
    ],
    "midjourney-upscale": [
        "task_id", "index", "custom_id", "speed", "metadata_json",
    ],
    "midjourney-variation": [
        "task_id", "index", "custom_id", "speed", "metadata_json",
    ],
    "midjourney-high-variation": [
        "task_id", "index", "custom_id", "speed", "metadata_json",
    ],
    "midjourney-low-variation": [
        "task_id", "index", "custom_id", "speed", "metadata_json",
    ],
    "midjourney-reroll": [
        "task_id", "custom_id", "speed", "metadata_json",
    ],
    "midjourney-zoom": [
        "task_id", "index", "custom_id", "zoom_ratio", "speed",
        "metadata_json",
    ],
    "midjourney-pan": [
        "task_id", "index", "custom_id", "direction", "speed",
        "metadata_json",
    ],
    "midjourney-inpaint": [
        "task_id", "index", "custom_id", "speed", "metadata_json",
    ],
    "midjourney-modal": [
        "task_id", "prompt", "speed", "modal_mode", "mask", "mask_url",
        "metadata_json",
    ],
    "midjourney-video": [
        "prompt", "image1", "image_url1", "task_id", "index",
        "video_type", "animate_mode", "motion", "batch_size",
        "end_image", "end_url",
    ],
    "midjourney-remix-strong": [
        "task_id", "index", "prompt", "speed",
    ],
    "midjourney-remix-subtle": [
        "task_id", "index", "prompt", "speed",
    ],
};

const MANAGED_FIELDS = new Set(
    Object.values(ACTION_FIELDS).flat().concat([...ALWAYS_VISIBLE]),
);

function isConvertedWidget(widget) {
    return (
        String(widget?.type ?? "").startsWith(CONVERTED_WIDGET_PREFIX)
        || Object.prototype.hasOwnProperty.call(widget ?? {}, "origType")
    );
}

function setWidgetVisible(widget, visible) {
    if (!widget || !MANAGED_FIELDS.has(widget.name) || isConvertedWidget(widget)) {
        return;
    }
    if (!widget.zhenzhenMidjourneyOriginal) {
        widget.zhenzhenMidjourneyOriginal = {
            type: widget.type,
            computeSize: widget.computeSize,
        };
    }
    const original = widget.zhenzhenMidjourneyOriginal;
    if (visible) {
        widget.type = original.type;
        widget.computeSize = original.computeSize;
    } else {
        widget.type = "hidden";
        widget.computeSize = () => [0, -4];
    }
}

function activeFields(node) {
    const operationWidget = node.widgets?.find(
        (widget) => widget.name === "operation",
    );
    const operation = String(
        operationWidget?.value ?? "midjourney-imagine",
    );
    const fields = new Set(ACTION_FIELDS[operation] ?? []);
    for (const name of ALWAYS_VISIBLE) {
        fields.add(name);
    }
    if (operation === "midjourney-modal") {
        const modeWidget = node.widgets?.find(
            (widget) => widget.name === "modal_mode",
        );
        if (String(modeWidget?.value ?? "region") === "outpaint") {
            fields.delete("mask");
            fields.delete("mask_url");
        }
    }
    return fields;
}

function refreshNode(node) {
    const fields = activeFields(node);
    for (const widget of node.widgets ?? []) {
        setWidgetVisible(widget, fields.has(widget.name));
    }
    for (const input of node.inputs ?? []) {
        if (!MANAGED_FIELDS.has(input.name)) {
            continue;
        }
        const connected = input.link != null;
        input.hidden = !fields.has(input.name) && !connected;
    }
    requestAnimationFrame(() => {
        const computed = node.computeSize?.();
        if (computed) {
            node.setSize?.([
                Math.max(node.size?.[0] ?? 340, computed[0], 340),
                Math.max(computed[1], 120),
            ]);
        }
        node.setDirtyCanvas?.(true, true);
    });
}

function wrapRefreshWidget(node, name) {
    const widget = node.widgets?.find((candidate) => candidate.name === name);
    if (!widget || widget.zhenzhenMidjourneyCallback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        refreshNode(node);
        return result;
    };
    widget.zhenzhenMidjourneyCallback = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.MidjourneyActionUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== NODE_NAME) {
            return;
        }
        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapRefreshWidget(this, "operation");
            wrapRefreshWidget(this, "modal_mode");
            refreshNode(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            refreshNode(this);
            return result;
        };

        const originalOnConnectionsChange =
            nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            refreshNode(this);
            return result;
        };
    },
});
