import { app } from "../../../scripts/app.js";

const G_V2_NODE_NAME = "Comfly_zhenzhen_image_g_v2_lowprice";
const NB_NODE_NAME = "Comfly_zhenzhen_image_nb_lowprice";
const V31_NODE_NAME = "Comfly_zhenzhen_video_v31_lowprice";

function originalNodeName(name) {
    const prefix = "ComflyConcurrent_";
    const suffix = "_Submit";
    if (name.startsWith(prefix) && name.endsWith(suffix)) {
        return name.slice(prefix.length, -suffix.length);
    }
    return name;
}

const STANDARD_SIZES = [
    "1:1", "2:3", "3:2", "3:4", "4:3",
    "4:5", "5:4", "9:16", "16:9", "21:9",
];
const EXTREME_SIZES = [
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1",
    "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
];

const NB_MODEL_OPTIONS = {
    "zhenzhen-image-nb-flash": {
        resolutions: ["1k"],
        sizes: ["auto", ...STANDARD_SIZES],
        maxN: 1,
    },
    "zhenzhen-image-nb-2": {
        resolutions: ["0.5k", "1k", "2k", "4k"],
        sizes: EXTREME_SIZES,
        maxN: 1,
    },
    "zhenzhen-image-nb-2-lite": {
        resolutions: ["1k"],
        sizes: EXTREME_SIZES,
        maxN: 4,
    },
    "zhenzhen-image-nb-pro": {
        resolutions: ["1k", "2k", "4k"],
        sizes: STANDARD_SIZES,
        maxN: 1,
    },
};

const WIDTH_HEIGHT_SIZE_RE = /^\d+x\d+$/i;

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function updateCombo(widget, values, preferred = values[0]) {
    if (!widget) {
        return;
    }
    widget.options ??= {};
    widget.options.values = [...values];
    if (!values.includes(String(widget.value))) {
        widget.value = values.includes(preferred) ? preferred : values[0];
        widget.callback?.(widget.value);
    }
}

function updateInteger(widget, maximum) {
    if (!widget) {
        return;
    }
    widget.options ??= {};
    widget.options.min = 1;
    widget.options.max = maximum;
    const nextValue = Math.min(maximum, Math.max(1, Number(widget.value) || 1));
    if (widget.value !== nextValue) {
        widget.value = nextValue;
        widget.callback?.(nextValue);
    }
}

function setWidgetVisible(widget, visible) {
    if (!widget) {
        return;
    }
    if (visible) {
        if (widget.zhenzhenOriginalType !== undefined) {
            widget.type = widget.zhenzhenOriginalType;
            widget.computeSize = widget.zhenzhenOriginalComputeSize;
            delete widget.zhenzhenOriginalType;
            delete widget.zhenzhenOriginalComputeSize;
        }
        return;
    }
    if (widget.type === "hidden") {
        return;
    }
    widget.zhenzhenOriginalType = widget.type;
    widget.zhenzhenOriginalComputeSize = widget.computeSize;
    widget.type = "hidden";
    widget.computeSize = () => [0, -4];
}

function resizeNode(node) {
    const computed = node.computeSize?.();
    if (!Array.isArray(computed)) {
        return;
    }
    const currentWidth = Number(node.size?.[0]) || computed[0];
    node.setSize?.([Math.max(currentWidth, computed[0]), computed[1]]);
}

function refreshGV2Node(node) {
    const sizeWidget = widgetByName(node, "size");
    const customSizeWidget = widgetByName(node, "custom_size");
    let selectedSize = String(sizeWidget?.value ?? "").trim().toLowerCase();

    // Older workflows stored a raw WxH value directly in the size widget.
    if (WIDTH_HEIGHT_SIZE_RE.test(selectedSize)) {
        if (customSizeWidget) {
            customSizeWidget.value = selectedSize;
        }
        if (sizeWidget) {
            sizeWidget.value = "custom";
        }
        selectedSize = "custom";
    }

    setWidgetVisible(customSizeWidget, selectedSize === "custom");
    resizeNode(node);
    node.setDirtyCanvas?.(true, true);
}

function refreshNBNode(node) {
    const model = String(widgetByName(node, "model")?.value ?? "");
    const options = NB_MODEL_OPTIONS[model] ?? NB_MODEL_OPTIONS["zhenzhen-image-nb-flash"];
    updateCombo(widgetByName(node, "resolution"), options.resolutions, "1k");
    updateCombo(widgetByName(node, "size"), options.sizes, "1:1");
    updateInteger(widgetByName(node, "n"), options.maxN);
    node.setDirtyCanvas?.(true, true);
}

function refreshV31Node(node) {
    const model = String(widgetByName(node, "model")?.value ?? "");
    for (const input of node.inputs ?? []) {
        if (!/^image[1-3]$/.test(input.name)) {
            continue;
        }
        const allowed = (
            model !== "zhenzhen-video-v31-lite"
            && !(model === "zhenzhen-video-v31-quality" && input.name === "image3")
        );
        input.hidden = !allowed && input.link == null;
    }
    node.setDirtyCanvas?.(true, true);
}

function wrapRefresh(node, widgetName, refresh) {
    const widget = widgetByName(node, widgetName);
    const marker = `zhenzhenDynamicCallback_${widgetName}`;
    if (!widget || widget[marker]) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        refresh(node);
        return result;
    };
    widget[marker] = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.NanoBananaV31UI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const nodeName = originalNodeName(nodeData.name);
        if (![G_V2_NODE_NAME, NB_NODE_NAME, V31_NODE_NAME].includes(nodeName)) {
            return;
        }
        const refresh = (
            nodeName === G_V2_NODE_NAME
                ? refreshGV2Node
                : nodeName === NB_NODE_NAME
                    ? refreshNBNode
                    : refreshV31Node
        );
        const refreshWidget = nodeName === G_V2_NODE_NAME ? "size" : "model";

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapRefresh(this, refreshWidget, refresh);
            refresh(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            wrapRefresh(this, refreshWidget, refresh);
            refresh(this);
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            refresh(this);
            return result;
        };
    },
});
