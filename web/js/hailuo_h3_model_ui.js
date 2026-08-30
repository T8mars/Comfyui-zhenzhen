import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const HAILUO_H3_NODE_NAME = "Comfly_hailuo_h3_video_lowprice";
const T2V_MODEL = "hailuo-h3-t2v";
const HAILUO_MEDIA_INPUT = /^(image[1-9]|video[1-3]|audio[1-3])$/;

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

function inputAllowed(model, name) {
    if (name === "api_config") {
        return true;
    }
    if (model.endsWith("-i2v")) {
        return name === "image1" || name === "image2";
    }
    if (model.endsWith("-multi")) {
        return HAILUO_MEDIA_INPUT.test(name);
    }
    return false;
}

function refreshHailuoH3Node(node) {
    const model = String(widgetByName(node, "model")?.value ?? T2V_MODEL);
    setZhenzhenWidgetVisible(
        widgetByName(node, "ratio"),
        !model.endsWith("-i2v"),
    );

    for (const input of node.inputs ?? []) {
        if (input.name === "api_config" || HAILUO_MEDIA_INPUT.test(input.name)) {
            setZhenzhenInputVisible(
                node,
                input,
                inputAllowed(model, input.name),
            );
        }
    }
    resizeZhenzhenNode(node, 420);
}

function scheduleHailuoH3Refresh(node) {
    if (node.zhenzhenHailuoH3RefreshFrame != null) {
        cancelAnimationFrame(node.zhenzhenHailuoH3RefreshFrame);
    }
    node.zhenzhenHailuoH3RefreshFrame = requestAnimationFrame(() => {
        node.zhenzhenHailuoH3RefreshFrame = null;
        refreshHailuoH3Node(node);
    });
}

function wrapModelRefresh(node) {
    const widget = widgetByName(node, "model");
    if (!widget || widget.zhenzhenHailuoH3Callback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = (...args) => {
        const result = originalCallback?.apply(widget, args);
        scheduleHailuoH3Refresh(node);
        return result;
    };
    widget.zhenzhenHailuoH3Callback = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.HailuoH3ModelUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== HAILUO_H3_NODE_NAME) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapModelRefresh(this);
            scheduleHailuoH3Refresh(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            scheduleHailuoH3Refresh(this);
            return result;
        };

        const originalOnConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalOnConnectionsChange?.apply(this, arguments);
            scheduleHailuoH3Refresh(this);
            return result;
        };
    },
});
