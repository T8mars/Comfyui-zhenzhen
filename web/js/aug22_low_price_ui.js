import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const OMNI_NODES = new Set([
    "Comfly_zhenzhen_video_g_omni_flash_lowprice_v2",
    "Comfly_zhenzhen_video_g_omni_1_1_flash_lowprice",
]);
const HUNYUAN_NODE = "Comfly_hunyuan3d_v3_1_lowprice";
const REGION_NODE = "Comfly_zhenzhen_image_gk_v2_region_edit_lowprice";
const MODE_DEFAULTS = {
    object_indices: "[0]",
    boxes: "[[0, 0, 512, 512]]",
    selection_regions: '[{"x": 0, "y": 0, "width": 512, "height": 512}]',
};

function originalNodeName(name) {
    const prefix = "ComflyConcurrent_";
    const suffix = "_Submit";
    if (name.startsWith(prefix) && name.endsWith(suffix)) {
        return name.slice(prefix.length, -suffix.length);
    }
    return name;
}

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function refreshOmni(node) {
    const mode = String(widgetByName(node, "mode")?.value ?? "text");
    const visibleImages = mode === "frame" ? 1 : mode === "reference_images" ? 3 : 0;
    for (const input of node.inputs ?? []) {
        const imageMatch = /^image([1-3])$/.exec(input.name);
        if (imageMatch) {
            setZhenzhenInputVisible(node, input, Number(imageMatch[1]) <= visibleImages);
        } else if (input.name === "input_video") {
            setZhenzhenInputVisible(node, input, mode === "reference_video");
        }
    }
    setZhenzhenWidgetVisible(widgetByName(node, "video_url"), mode === "reference_video");
    setZhenzhenWidgetVisible(widgetByName(node, "seconds"), mode !== "reference_video");
    resizeZhenzhenNode(node, 390);
}

function refreshHunyuan(node) {
    const model = String(widgetByName(node, "model")?.value ?? "");
    const imageMode = model === "hunyuan3d-v3.1-image-to-3d";
    for (const input of node.inputs ?? []) {
        if (/^image[1-8]$/.test(input.name)) {
            setZhenzhenInputVisible(node, input, imageMode);
        }
    }
    resizeZhenzhenNode(node, 420);
}

function refreshRegion(node, previousMode = null) {
    const modeWidget = widgetByName(node, "selection_mode");
    const jsonWidget = widgetByName(node, "selection_json");
    const mode = String(modeWidget?.value ?? "object_indices");
    if (jsonWidget) {
        const current = String(jsonWidget.value ?? "").trim();
        const knownDefault = !current || Object.values(MODE_DEFAULTS).includes(current);
        if (knownDefault && previousMode !== mode) {
            jsonWidget.value = MODE_DEFAULTS[mode] ?? MODE_DEFAULTS.object_indices;
            jsonWidget.callback?.(jsonWidget.value);
        }
        jsonWidget.options ??= {};
        jsonWidget.options.tooltip = `JSON ${mode}`;
    }
    node.zhenzhenGKV2LastMode = mode;
    resizeZhenzhenNode(node, 420);
}

function wrapRefreshWidget(node, name, refresh) {
    const widget = widgetByName(node, name);
    const marker = `zhenzhenAug22Callback_${name}`;
    if (!widget || widget[marker]) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const previousMode = String(node.zhenzhenGKV2LastMode ?? "");
        const result = originalCallback?.apply(widget, args);
        refresh(node, previousMode);
        return result;
    };
    widget[marker] = true;
}

function scheduleRefresh(node, refresh) {
    if (node.zhenzhenAug22RefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenAug22RefreshFrame);
    }
    node.zhenzhenAug22RefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenAug22RefreshFrame = null;
        refresh(node);
    });
}

app.registerExtension({
    name: "ComfyuiZhenzhen.Aug22LowPriceUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const nodeName = originalNodeName(nodeData.name);
        const definition = OMNI_NODES.has(nodeName)
            ? ["mode", refreshOmni]
            : {
                [HUNYUAN_NODE]: ["model", refreshHunyuan],
                [REGION_NODE]: ["selection_mode", refreshRegion],
            }[nodeName];
        if (!definition) {
            return;
        }
        const [selector, refresh] = definition;

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapRefreshWidget(this, selector, refresh);
            scheduleRefresh(this, refresh);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            scheduleRefresh(this, refresh);
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            scheduleRefresh(this, refresh);
            return result;
        };
    },
});
