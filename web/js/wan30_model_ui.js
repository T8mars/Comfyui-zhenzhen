import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const NODE_NAME = "Comfly_wan_3_0_video_lowprice";
const DEFAULT_MODEL = "wan-3.0-i2v";
const THINKING_MODELS = new Set([
    "wan-3.0-global-i2v",
    "wan-3.0-global-r2v",
]);
const IMAGE_INPUT = /^image([1-9]|10)$/;
const VIDEO_INPUT = /^video([1-5])$/;
const AUDIO_INPUT = /^audio([1-5])$/;

function originalNodeName(name) {
    const value = String(name ?? "");
    const prefix = "ComflyConcurrent_";
    const suffix = "_Submit";
    if (value.startsWith(prefix) && value.endsWith(suffix)) {
        return value.slice(prefix.length, -suffix.length);
    }
    return value;
}

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function nextVisibleSlot(node, pattern, maximum) {
    let highestConnected = 0;
    for (const input of node.inputs ?? []) {
        const match = pattern.exec(input.name);
        if (match && input.link != null) {
            highestConnected = Math.max(highestConnected, Number(match[1]));
        }
    }
    return Math.min(maximum, highestConnected + 1);
}

function inputAllowed(model, input, limits) {
    if (input.name === "api_config") {
        return true;
    }
    const imageMatch = IMAGE_INPUT.exec(input.name);
    if (imageMatch) {
        const index = Number(imageMatch[1]);
        return model.endsWith("-i2v")
            ? index <= 2
            : index <= limits.images;
    }
    const videoMatch = VIDEO_INPUT.exec(input.name);
    if (videoMatch) {
        return model.endsWith("-r2v")
            && Number(videoMatch[1]) <= limits.videos;
    }
    const audioMatch = AUDIO_INPUT.exec(input.name);
    if (audioMatch) {
        return model.endsWith("-r2v")
            && Number(audioMatch[1]) <= limits.audios;
    }
    return false;
}

function refreshWan30Node(node) {
    const model = String(widgetByName(node, "model")?.value ?? DEFAULT_MODEL);
    const isR2V = model.endsWith("-r2v");
    const supportsThinking = THINKING_MODELS.has(model);
    const limits = {
        images: nextVisibleSlot(node, IMAGE_INPUT, 10),
        videos: nextVisibleSlot(node, VIDEO_INPUT, 5),
        audios: nextVisibleSlot(node, AUDIO_INPUT, 5),
    };

    setZhenzhenWidgetVisible(
        widgetByName(node, "enable_thinking"),
        supportsThinking,
    );
    setZhenzhenWidgetVisible(widgetByName(node, "file_url"), isR2V);
    setZhenzhenWidgetVisible(widgetByName(node, "link_url"), isR2V);
    for (const input of node.inputs ?? []) {
        if (
            input.name === "api_config"
            || IMAGE_INPUT.test(input.name)
            || VIDEO_INPUT.test(input.name)
            || AUDIO_INPUT.test(input.name)
        ) {
            setZhenzhenInputVisible(
                node,
                input,
                inputAllowed(model, input, limits),
            );
        }
    }
    resizeZhenzhenNode(node, 430);
}

function scheduleRefresh(node) {
    if (node.zhenzhenWan30RefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenWan30RefreshFrame);
    }
    node.zhenzhenWan30RefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenWan30RefreshFrame = null;
        refreshWan30Node(node);
    });
}

function wrapModelRefresh(node) {
    const widget = widgetByName(node, "model");
    if (!widget || widget.zhenzhenWan30Callback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        scheduleRefresh(node);
        return result;
    };
    widget.zhenzhenWan30Callback = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.Wan30ModelUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== NODE_NAME) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapModelRefresh(this);
            scheduleRefresh(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            scheduleRefresh(this);
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            scheduleRefresh(this);
            return result;
        };
    },
});
