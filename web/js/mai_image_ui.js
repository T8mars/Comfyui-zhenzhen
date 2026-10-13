import { app } from "../../../scripts/app.js";
import { resizeZhenzhenNode, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const NODE_NAME = "T8Zhenzhen_MAI_Image_26_LowPrice";
const INSTALLED = Symbol("zhenzhenMaiImageUI");

function originalName(value) {
    return String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
}

function refresh(node) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const references = (node.inputs ?? []).some(
        (input) => /^image[1-5]$/.test(input.name) && input.link != null,
    );
    const automatic = Boolean(widget("auto_aspect_ratio")?.value);
    const size = String(widget("size")?.value ?? "1:1");
    setZhenzhenWidgetVisible(widget("auto_aspect_ratio"), !references);
    setZhenzhenWidgetVisible(widget("size"), !references && !automatic);
    setZhenzhenWidgetVisible(widget("resolution"), !references && (automatic || size !== "custom_pixels"));
    setZhenzhenWidgetVisible(widget("custom_ratio"), !references && !automatic && size === "custom_ratio");
    setZhenzhenWidgetVisible(widget("width"), !references && !automatic && size === "custom_pixels");
    setZhenzhenWidgetVisible(widget("height"), !references && !automatic && size === "custom_pixels");
    resizeZhenzhenNode(node, 440);
}

function schedule(node) {
    if (node.zhenzhenMaiFrame != null) cancelAnimationFrame(node.zhenzhenMaiFrame);
    node.zhenzhenMaiFrame = requestAnimationFrame(() => {
        node.zhenzhenMaiFrame = null;
        refresh(node);
    });
}

function install(node) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    for (const name of ["size", "auto_aspect_ratio"]) {
        const widget = node.widgets?.find((item) => item.name === name);
        if (!widget) continue;
        const callback = widget.callback;
        widget.callback = function () {
            const result = callback?.apply(this, arguments);
            schedule(node);
            return result;
        };
    }
    schedule(node);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.MaiImageUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalName(nodeData.name) !== NODE_NAME) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            install(this);
            return result;
        };
        for (const name of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const original = nodeType.prototype[name];
            nodeType.prototype[name] = function () {
                const result = original?.apply(this, arguments);
                schedule(this);
                return result;
            };
        }
    },
    nodeCreated(node) {
        const name = node.comfyClass ?? node.constructor?.comfyClass ?? node.type;
        if (originalName(name) === NODE_NAME) install(node);
    },
});
