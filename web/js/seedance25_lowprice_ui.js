import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const NODE_NAME = "Comfly_seedance25_standard_low_price";
const DEFAULT_MODEL = "seedance-2.5-standard-t2v";
const MEDIA_LIMITS = { image: 30, video: 10, audio: 10 };
const MEDIA_INPUT = /^(image|video|audio)([1-9]\d*)$/;

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

function mediaInput(name) {
    const match = MEDIA_INPUT.exec(String(name));
    if (!match) {
        return null;
    }
    return { family: match[1], index: Number(match[2]) };
}

function nextVisibleSlots(node) {
    const highestConnected = { image: 0, video: 0, audio: 0 };
    for (const input of node.inputs ?? []) {
        const media = mediaInput(input.name);
        if (media && input.link != null) {
            highestConnected[media.family] = Math.max(
                highestConnected[media.family],
                media.index,
            );
        }
    }
    return Object.fromEntries(
        Object.entries(MEDIA_LIMITS).map(([family, limit]) => [
            family,
            Math.min(highestConnected[family] + 1, limit),
        ]),
    );
}

function inputAllowed(model, name, nextVisible) {
    if (name === "api_config") {
        return true;
    }
    if (model.endsWith("-i2v")) {
        return name === "image1" || name === "image2";
    }
    if (model.endsWith("-multi")) {
        const media = mediaInput(name);
        return Boolean(
            media
            && media.index <= MEDIA_LIMITS[media.family]
            && media.index <= nextVisible[media.family]
        );
    }
    return false;
}

function refreshNode(node) {
    const model = String(widgetByName(node, "model")?.value ?? DEFAULT_MODEL);
    const nextVisible = nextVisibleSlots(node);
    setZhenzhenWidgetVisible(widgetByName(node, "ratio"), !model.endsWith("-i2v"));
    for (const input of node.inputs ?? []) {
        setZhenzhenInputVisible(
            node,
            input,
            inputAllowed(model, input.name, nextVisible),
        );
    }
    resizeZhenzhenNode(node, 430);
}

function wrapModelRefresh(node) {
    const widget = widgetByName(node, "model");
    if (!widget || widget.zhenzhenSeedance25Callback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        refreshNode(node);
        return result;
    };
    widget.zhenzhenSeedance25Callback = true;
}

function scheduleRefresh(node) {
    if (node.zhenzhenSeedance25RefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenSeedance25RefreshFrame);
    }
    node.zhenzhenSeedance25RefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenSeedance25RefreshFrame = null;
        wrapModelRefresh(node);
        refreshNode(node);
    });
}

app.registerExtension({
    name: "ComfyuiZhenzhen.Seedance25LowPriceUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== NODE_NAME) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
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
