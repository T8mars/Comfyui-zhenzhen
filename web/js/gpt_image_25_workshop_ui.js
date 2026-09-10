import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const NODE_NAME = "T8Zhenzhen_GPT_Image_2_5_Workshop";
const CONCURRENT_PREFIX = "ComflyConcurrent_";
const CONCURRENT_SUFFIX = "_Submit";

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function originalNodeName(name) {
    if (name.startsWith(CONCURRENT_PREFIX) && name.endsWith(CONCURRENT_SUFFIX)) {
        return name.slice(CONCURRENT_PREFIX.length, -CONCURRENT_SUFFIX.length);
    }
    return name;
}

function syncCustomSize(node) {
    const isCustom = String(widgetByName(node, "size")?.value ?? "") === "custom";
    const widthChanged = setZhenzhenWidgetVisible(
        widgetByName(node, "custom_width"),
        isCustom,
    );
    const heightChanged = setZhenzhenWidgetVisible(
        widgetByName(node, "custom_height"),
        isCustom,
    );
    if (widthChanged || heightChanged) {
        resizeZhenzhenNode(node);
    }
}

function installSizeCallback(node) {
    const widget = widgetByName(node, "size");
    if (!widget || widget.zhenzhenGptImage25SizeCallback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = function () {
        const result = originalCallback?.apply(this, arguments);
        syncCustomSize(node);
        return result;
    };
    widget.zhenzhenGptImage25SizeCallback = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.GptImage25WorkshopUi",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== NODE_NAME) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            installSizeCallback(this);
            syncCustomSize(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            installSizeCallback(this);
            syncCustomSize(this);
            return result;
        };
    },
});
