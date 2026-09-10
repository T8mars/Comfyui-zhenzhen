import { app } from "../../../scripts/app.js";
import {
    resizeSeedanceNode,
    setSeedanceInputVisible,
    setSeedanceWidgetVisible,
} from "./dynamic_widget_ui.js";

const HAILUO_H3_MAX_NODE_NAMES = new Set([
    "Comfly_hailuo_h3_max_video_lowprice",
    "ComflyConcurrent_Comfly_hailuo_h3_max_video_lowprice_Submit",
]);
const DEFAULT_MODEL = "hailuo-h3-max-t2v";

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function refresh(node) {
    const model = String(widgetByName(node, "model")?.value ?? DEFAULT_MODEL);
    const isI2V = model.endsWith("-i2v");
    setSeedanceWidgetVisible(widgetByName(node, "ratio"), !isI2V);
    for (const input of node.inputs ?? []) {
        if (input.name === "api_config") {
            setSeedanceInputVisible(node, input, true);
        } else if (input.name === "image1" || input.name === "image2") {
            setSeedanceInputVisible(node, input, isI2V);
        }
    }
    resizeSeedanceNode(node);
}

function scheduleRefresh(node) {
    if (node.zhenzhenHailuoH3MaxRefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenHailuoH3MaxRefreshFrame);
    }
    node.zhenzhenHailuoH3MaxRefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenHailuoH3MaxRefreshFrame = null;
        refresh(node);
    });
}

function wrapModelWidget(node) {
    const widget = widgetByName(node, "model");
    if (!widget || widget.zhenzhenHailuoH3MaxCallback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        scheduleRefresh(node);
        return result;
    };
    widget.zhenzhenHailuoH3MaxCallback = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.HailuoH3MaxModelUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!HAILUO_H3_MAX_NODE_NAMES.has(nodeData.name)) {
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
