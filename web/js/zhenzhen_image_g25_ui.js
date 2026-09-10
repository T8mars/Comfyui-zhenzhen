import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const NODE_NAME = "T8Zhenzhen_Image_G25_Official";
const CONCURRENT_PREFIX = "ComflyConcurrent_";
const CONCURRENT_SUFFIX = "_Submit";

function originalNodeName(name) {
    if (name.startsWith(CONCURRENT_PREFIX) && name.endsWith(CONCURRENT_SUFFIX)) {
        return name.slice(CONCURRENT_PREFIX.length, -CONCURRENT_SUFFIX.length);
    }
    return name;
}

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function syncControls(node) {
    const size = String(widgetByName(node, "size")?.value ?? "");
    const outputFormat = String(
        widgetByName(node, "output_format")?.value ?? "png",
    );
    const changed = [
        setZhenzhenWidgetVisible(widgetByName(node, "custom_size"), size === "custom"),
        setZhenzhenWidgetVisible(widgetByName(node, "resolution"), size !== "custom"),
        setZhenzhenWidgetVisible(
            widgetByName(node, "output_compression"),
            outputFormat === "jpeg" || outputFormat === "webp",
        ),
    ].some(Boolean);
    if (changed) {
        resizeZhenzhenNode(node, 410);
    }
}

function installCallback(node, widgetName) {
    const widget = widgetByName(node, widgetName);
    if (!widget || widget.zhenzhenImageG25Callback) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = function () {
        const result = originalCallback?.apply(this, arguments);
        syncControls(node);
        return result;
    };
    widget.zhenzhenImageG25Callback = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.ImageG25Ui",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== NODE_NAME) {
            return;
        }
        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            installCallback(this, "size");
            installCallback(this, "output_format");
            syncControls(this);
            return result;
        };
        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            installCallback(this, "size");
            installCallback(this, "output_format");
            syncControls(this);
            return result;
        };
    },
});
