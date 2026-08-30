import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const FLUX3_NODE_NAME = "Comfly_flux3_video_lowprice";
const FLUX3_DEFAULT_MODEL = "flux-3-video-t2v";
const IMAGE_INPUT = /^image([1-9]|10)$/;
const DYNAMIC_INPUTS = new Set([
    "api_config",
    "input_video",
    "video_url",
    "draft_cache",
]);

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

function flux3Mode(model) {
    if (model.endsWith("-draft-enhance")) {
        return "draft-enhance";
    }
    if (model.endsWith("-i2v")) {
        return "i2v";
    }
    if (model.endsWith("-v2v")) {
        return "v2v";
    }
    return "t2v";
}

function nextVisibleImageSlot(node) {
    let highestConnected = 0;
    for (const input of node.inputs ?? []) {
        const match = IMAGE_INPUT.exec(input.name);
        if (match && input.link != null) {
            highestConnected = Math.max(highestConnected, Number(match[1]));
        }
    }
    return Math.min(highestConnected + 1, 10);
}

function inputAllowed(mode, input, nextImage) {
    if (input.name === "api_config") {
        return true;
    }
    const imageMatch = IMAGE_INPUT.exec(input.name);
    if (imageMatch) {
        return mode === "i2v" && Number(imageMatch[1]) <= nextImage;
    }
    if (input.name === "input_video" || input.name === "video_url") {
        return mode === "v2v";
    }
    if (input.name === "draft_cache") {
        return mode === "draft-enhance";
    }
    return false;
}

function refreshFlux3Node(node) {
    const model = String(
        widgetByName(node, "model")?.value ?? FLUX3_DEFAULT_MODEL,
    );
    const mode = flux3Mode(model);
    const nextImage = nextVisibleImageSlot(node);

    setZhenzhenWidgetVisible(
        widgetByName(node, "prompt"),
        mode !== "draft-enhance",
    );
    setZhenzhenWidgetVisible(
        widgetByName(node, "draft"),
        mode !== "draft-enhance",
    );
    setZhenzhenWidgetVisible(
        widgetByName(node, "video_url"),
        mode === "v2v",
    );
    setZhenzhenWidgetVisible(
        widgetByName(node, "draft_cache"),
        mode === "draft-enhance",
    );

    for (const input of node.inputs ?? []) {
        if (IMAGE_INPUT.test(input.name) || DYNAMIC_INPUTS.has(input.name)) {
            setZhenzhenInputVisible(
                node,
                input,
                inputAllowed(mode, input, nextImage),
            );
        }
    }
    resizeZhenzhenNode(node, 440);
}

function scheduleFlux3Refresh(node) {
    if (node.zhenzhenFlux3RefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenFlux3RefreshFrame);
    }
    node.zhenzhenFlux3RefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenFlux3RefreshFrame = null;
        refreshFlux3Node(node);
    });
}

function wrapModelRefresh(node) {
    const widget = widgetByName(node, "model");
    if (!widget || widget.zhenzhenFlux3Callback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        scheduleFlux3Refresh(node);
        return result;
    };
    widget.zhenzhenFlux3Callback = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.Flux3ModelUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== FLUX3_NODE_NAME) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapModelRefresh(this);
            scheduleFlux3Refresh(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            scheduleFlux3Refresh(this);
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            scheduleFlux3Refresh(this);
            return result;
        };
    },
});
