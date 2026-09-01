import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenInputVisible,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const QWEN_NODE_NAME = "Comfly_qwen_image_3_0_lowprice";
const MINIMAX_NODE_NAME = "Comfly_minimax_h3_ow_video_lowprice";
const MINIMAX_FAST_NODE_NAME = "Comfly_minimax_h3_ow_fast_video_lowprice";
const CONTEXT_IR_NODE_NAME = "Comfly_minmax_h3_context_ir_lowprice";
const QWEN_DEFAULT_MODEL = "qwen-image-3.0-t2i";
const MINIMAX_DEFAULT_MODEL = "minimax-h3-ow-t2v";
const MINIMAX_FAST_DEFAULT_MODEL = "minimax-h3-ow-i2v-fast";
const CONTEXT_IR_DEFAULT_MODEL = "minmax-h3-context-ir-text";
const CONTEXT_IR_MEDIA_INPUT = /^(image[1-9]|video[1-3]|audio[1-3])$/;

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

function refreshQwenNode(node) {
    const model = String(widgetByName(node, "model")?.value ?? QWEN_DEFAULT_MODEL);
    const sizingMode = String(widgetByName(node, "sizing_mode")?.value ?? "auto");
    setZhenzhenWidgetVisible(widgetByName(node, "resolution"), sizingMode === "ratio");
    setZhenzhenWidgetVisible(widgetByName(node, "ratio"), sizingMode === "ratio");
    setZhenzhenWidgetVisible(
        widgetByName(node, "custom_size"),
        sizingMode === "custom_size",
    );

    const editing = model.endsWith("-i2i");
    for (const input of node.inputs ?? []) {
        const visible = input.name === "api_config" || (
            editing && /^image[1-3]$/.test(input.name)
        );
        setZhenzhenInputVisible(node, input, visible);
    }
    resizeZhenzhenNode(node, 400);
}

function refreshMinimaxNode(node, fallbackModel = MINIMAX_DEFAULT_MODEL) {
    const model = String(widgetByName(node, "model")?.value ?? fallbackModel);
    const isAudioDrive = model.includes("-audio-drive-fast");
    const maxImages = model.endsWith("-r2v-fast")
        ? 9
        : (
            isAudioDrive || model.includes("-i2v") || model.includes("-r2v")
                ? 1
                : 0
        );
    for (const input of node.inputs ?? []) {
        const match = /^image(\d+)$/.exec(input.name);
        const visible = input.name === "api_config"
            || (input.name === "audio" && isAudioDrive)
            || (match && Number(match[1]) <= maxImages);
        setZhenzhenInputVisible(node, input, visible);
    }
    resizeZhenzhenNode(node, 400);
}

function contextIRInputAllowed(model, name) {
    if (name === "api_config") {
        return true;
    }
    if (model.endsWith("-image")) {
        return name === "image1" || name === "image2";
    }
    if (model.endsWith("-multimodal")) {
        return CONTEXT_IR_MEDIA_INPUT.test(name);
    }
    return false;
}

function refreshContextIRNode(node) {
    const model = String(
        widgetByName(node, "model")?.value ?? CONTEXT_IR_DEFAULT_MODEL,
    );
    setZhenzhenWidgetVisible(
        widgetByName(node, "ratio"),
        !model.endsWith("-image"),
    );
    for (const input of node.inputs ?? []) {
        if (input.name === "api_config" || CONTEXT_IR_MEDIA_INPUT.test(input.name)) {
            setZhenzhenInputVisible(
                node,
                input,
                contextIRInputAllowed(model, input.name),
            );
        }
    }
    resizeZhenzhenNode(node, 420);
}

function wrapRefreshWidget(node, name, refresh, marker) {
    const widget = widgetByName(node, name);
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
    name: "ComfyuiZhenzhen.QwenMinimaxModelUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const nodeName = originalNodeName(nodeData.name);
        if (![
            QWEN_NODE_NAME,
            MINIMAX_NODE_NAME,
            MINIMAX_FAST_NODE_NAME,
            CONTEXT_IR_NODE_NAME,
        ].includes(nodeName)) {
            return;
        }
        let refresh;
        if (nodeName === QWEN_NODE_NAME) {
            refresh = refreshQwenNode;
        } else if (nodeName === CONTEXT_IR_NODE_NAME) {
            refresh = refreshContextIRNode;
        } else {
            refresh = (node) => refreshMinimaxNode(
                node,
                nodeName === MINIMAX_FAST_NODE_NAME
                    ? MINIMAX_FAST_DEFAULT_MODEL
                    : MINIMAX_DEFAULT_MODEL,
            );
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            wrapRefreshWidget(this, "model", refresh, "zhenzhenQwenMinimaxModelCallback");
            if (nodeName === QWEN_NODE_NAME) {
                wrapRefreshWidget(
                    this,
                    "sizing_mode",
                    refresh,
                    "zhenzhenQwenSizingModeCallback",
                );
            }
            refresh(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
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
