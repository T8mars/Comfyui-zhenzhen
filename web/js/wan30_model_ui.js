import { app } from "../../../scripts/app.js";
import {
    resizeSeedanceNode,
    setSeedanceInputVisible,
    setSeedanceWidgetVisible,
} from "./dynamic_widget_ui.js";

const WAN30_NODE_NAMES = new Set([
    "Comfly_wan_3_0_video_lowprice",
    "ComflyConcurrent_Comfly_wan_3_0_video_lowprice_Submit",
]);
const DEFAULT_MODEL = "wan-3.0-i2v";
const IMAGE_INPUT = /^image([1-9]|10)$/;
const VIDEO_INPUT = /^video([1-5])$/;
const AUDIO_INPUT = /^audio([1-5])$/;

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
    const image = IMAGE_INPUT.exec(input.name);
    if (image) {
        return model.endsWith("-i2v")
            ? Number(image[1]) <= 2
            : Number(image[1]) <= limits.images;
    }
    const video = VIDEO_INPUT.exec(input.name);
    if (video) {
        return model.endsWith("-r2v") && Number(video[1]) <= limits.videos;
    }
    const audio = AUDIO_INPUT.exec(input.name);
    return Boolean(
        audio
        && model.endsWith("-r2v")
        && Number(audio[1]) <= limits.audios
    );
}

function refresh(node) {
    const model = String(widgetByName(node, "model")?.value ?? DEFAULT_MODEL);
    const isR2V = model.endsWith("-r2v");
    const isGlobal = model.includes("-global-");
    const limits = {
        images: nextVisibleSlot(node, IMAGE_INPUT, 10),
        videos: nextVisibleSlot(node, VIDEO_INPUT, 5),
        audios: nextVisibleSlot(node, AUDIO_INPUT, 5),
    };

    setSeedanceWidgetVisible(widgetByName(node, "enable_thinking"), isGlobal);
    setSeedanceWidgetVisible(widgetByName(node, "file_url"), isR2V);
    setSeedanceWidgetVisible(widgetByName(node, "link_url"), isR2V);
    for (const input of node.inputs ?? []) {
        if (
            input.name === "api_config"
            || IMAGE_INPUT.test(input.name)
            || VIDEO_INPUT.test(input.name)
            || AUDIO_INPUT.test(input.name)
        ) {
            setSeedanceInputVisible(node, input, inputAllowed(model, input, limits));
        }
    }
    resizeSeedanceNode(node);
}

function scheduleRefresh(node) {
    if (node.zhenzhenWan30RefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenWan30RefreshFrame);
    }
    node.zhenzhenWan30RefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenWan30RefreshFrame = null;
        refresh(node);
    });
}

function wrapModelWidget(node) {
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
        if (!WAN30_NODE_NAMES.has(nodeData.name)) {
            return;
        }
        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapModelWidget(this);
            scheduleRefresh(this);
            return result;
        };
        for (const eventName of [
            "onConfigure",
            "onConnectionsChange",
            "onAfterGraphConfigured",
        ]) {
            const original = nodeType.prototype[eventName];
            nodeType.prototype[eventName] = function () {
                const result = original?.apply(this, arguments);
                scheduleRefresh(this);
                return result;
            };
        }
    },
});

