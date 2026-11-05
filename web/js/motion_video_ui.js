import { app } from "../../../scripts/app.js";
import { resizeZhenzhenNode, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const NODE = "T8Zhenzhen_Motion_Video_LowPrice";
const INSTALLED = Symbol("zhenzhenMotionVideoUI");
const originalName = (value) => String(value ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");

function schedule(node) {
    if (node.zhenzhenMotionFrame != null) cancelAnimationFrame(node.zhenzhenMotionFrame);
    node.zhenzhenMotionFrame = requestAnimationFrame(() => {
        node.zhenzhenMotionFrame = null;
        const revise = node.widgets?.find((widget) => widget.name === "operation")?.value === "revise";
        for (const name of ["revise_from", "revision_instruction"]) {
            setZhenzhenWidgetVisible(node.widgets?.find((widget) => widget.name === name), revise);
        }
        resizeZhenzhenNode(node, 460);
    });
}

function install(node) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    const operation = node.widgets?.find((widget) => widget.name === "operation");
    if (operation) {
        const callback = operation.callback;
        operation.callback = function () {
            const result = callback?.apply(this, arguments);
            schedule(node);
            return result;
        };
    }
    schedule(node);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.MotionVideoUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (originalName(nodeData.name) !== NODE) return;
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
        if (originalName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type) === NODE) install(node);
    },
});
