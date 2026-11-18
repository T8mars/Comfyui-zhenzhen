import { app } from "../../../scripts/app.js";
import { resizeZhenzhenNode, setZhenzhenInputVisible, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const KEY = "Comfly_LLm_API";
const INSTALLED = Symbol("zhenzhenLLMPresets");

function refresh(node) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const preset = widget("model_preset")?.value !== "custom";
    for (const name of ["model", "api_baseurl", "temperature"]) setZhenzhenWidgetVisible(widget(name), !preset);
    for (const name of ["stream", "max_tokens"]) setZhenzhenWidgetVisible(widget(name), preset);
    const config = node.inputs?.find((input) => input.name === "api_config");
    setZhenzhenInputVisible(node, config, preset);
    setZhenzhenWidgetVisible(widget("api_key"), !preset || config?.link == null);
    const footer = node.widgets?.find((item) => item.zhenzhenApiKeyAcquisitionLink);
    if (footer) {
        const low = preset || /^https:\/\/api\.seedance\.nz(?:\/|$)/.test(String(widget("api_baseurl")?.value ?? ""));
        footer.name = footer.label = low ? "贞贞的平价小屋APIKEY获取" : "贞贞的AI工坊APIKEY获取";
        footer.callback = () => window.open(low ? "https://api.seedance.nz/sign-up?aff=5f4w" : "https://ai.t8star.org/register?aff=dP7j", "_blank", "noopener,noreferrer");
    }
    resizeZhenzhenNode(node, 500);
}

app.registerExtension({
    name: "ComfyuiZhenzhen.LLMLowPricePresets",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== KEY) return;
        const schedule = (node) => {
            if (node.zhenzhenLLMPresetFrame != null) cancelAnimationFrame(node.zhenzhenLLMPresetFrame);
            node.zhenzhenLLMPresetFrame = requestAnimationFrame(() => { node.zhenzhenLLMPresetFrame = null; refresh(node); });
        };
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            if (!this[INSTALLED]) {
                this[INSTALLED] = true;
                for (const name of ["model_preset", "api_baseurl"]) {
                    const widget = this.widgets?.find((item) => item.name === name);
                    if (!widget) continue;
                    const callback = widget.callback;
                    widget.callback = (...args) => { const result = callback?.apply(widget, args); schedule(this); return result; };
                }
            }
            schedule(this);
            return result;
        };
        for (const hook of ["onConfigure", "onConnectionsChange", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () { const result = previous?.apply(this, arguments); schedule(this); return result; };
        }
    },
});
