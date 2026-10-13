import { app } from "../../../scripts/app.js";
import {
    resizeZhenzhenNode,
    setZhenzhenWidgetVisible,
} from "./dynamic_widget_ui.js";

const NODE_NAME = "Comfly_sd2_seedream_v5_pro_lowprice";
const CONCURRENT_PREFIX = "ComflyConcurrent_";
const CONCURRENT_SUFFIX = "_Submit";
const PRO_RESOLUTIONS = ["1k", "2k", "custom"];
const FLASH_RESOLUTIONS = ["1k", "1.5k", "2k", "custom"];

function originalNodeName(name) {
    const value = String(name ?? "");
    if (value.startsWith(CONCURRENT_PREFIX) && value.endsWith(CONCURRENT_SUFFIX)) {
        return value.slice(CONCURRENT_PREFIX.length, -CONCURRENT_SUFFIX.length);
    }
    return value;
}

function widgetByName(node, name) {
    return node.widgets?.find((widget) => widget.name === name);
}

function updateCombo(widget, values) {
    if (!widget) {
        return;
    }
    widget.options ??= {};
    widget.options.values = [...values];
    if (!values.includes(String(widget.value))) {
        widget.value = values[0];
        widget.callback?.(widget.value);
    }
}

function refreshSeedreamNode(node) {
    const family = String(widgetByName(node, "model_family")?.value ?? "");
    const isFlash = family.includes("-flash ");
    const resolution = widgetByName(node, "resolution");
    updateCombo(resolution, isFlash ? FLASH_RESOLUTIONS : PRO_RESOLUTIONS);

    const isCustom = String(resolution?.value ?? "") === "custom";
    const changed = [
        setZhenzhenWidgetVisible(widgetByName(node, "width"), isCustom),
        setZhenzhenWidgetVisible(widgetByName(node, "height"), isCustom),
    ].some(Boolean);
    if (changed) {
        resizeZhenzhenNode(node, 420);
    }
}

function installCallback(node, widgetName) {
    const widget = widgetByName(node, widgetName);
    const marker = `zhenzhenSeedreamCallback_${widgetName}`;
    if (!widget || widget[marker]) {
        return;
    }
    const originalCallback = widget.callback;
    widget.callback = function () {
        const result = originalCallback?.apply(this, arguments);
        refreshSeedreamNode(node);
        return result;
    };
    widget[marker] = true;
}

app.registerExtension({
    name: "ComfyuiZhenzhen.SeedreamModelUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalNodeName(nodeData.name) !== NODE_NAME) {
            return;
        }

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);
            installCallback(this, "model_family");
            installCallback(this, "resolution");
            refreshSeedreamNode(this);
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            installCallback(this, "model_family");
            installCallback(this, "resolution");
            refreshSeedreamNode(this);
            return result;
        };
    },
});
