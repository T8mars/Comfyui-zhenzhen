import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
const originalSeedanceNodeName = (name) => String(name ?? "").replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
import { setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const INSTALLED = Symbol("zhenzhenGifPreview");
const TARGETS = new Set(["T8Zhenzhen_Image_G26_LowPrice", "ComflyConcurrent_Image_Await"]);
const isGif = (entry) => typeof entry?.filename === "string" && /\.gif$/i.test(entry.filename);

function render(node, entries) {
    if (!entries.length) {
        if (node.zhenzhenGifWidget) {
            setZhenzhenWidgetVisible(node.zhenzhenGifWidget, false);
            node.zhenzhenGifContainer.replaceChildren();
            node.zhenzhenGifContainer.style.display = "none";
        }
        return;
    }
    if (!node.zhenzhenGifWidget) {
        const container = document.createElement("div");
        container.className = "zhenzhen-gif-preview";
        container.style.cssText = "width:100%;height:100%;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;overflow:auto;background:#202020";
        const widget = node.addDOMWidget("zhenzhen_gif_preview", "preview", container, { serialize: false, hideOnZoom: false });
        widget.serialize = false;
        widget.computeSize = (width) => [width, 330];
        node.zhenzhenGifWidget = widget;
        node.zhenzhenGifContainer = container;
    }
    setZhenzhenWidgetVisible(node.zhenzhenGifWidget, true);
    const container = node.zhenzhenGifContainer;
    container.style.display = "grid";
    container.replaceChildren();
    for (const [index, entry] of entries.entries()) {
        const url = api.apiURL("/view?" + new URLSearchParams({ filename: entry.filename,
            subfolder: entry.subfolder ?? "", type: entry.type ?? "output" }));
        const item = document.createElement("div");
        item.style.cssText = "min-width:0;display:flex;flex-direction:column;gap:4px;align-items:center";
        const image = document.createElement("img");
        image.src = url;
        image.alt = `GIF ${index + 1}`;
        image.style.cssText = "width:100%;min-height:0;flex:1;object-fit:contain";
        const save = document.createElement("a");
        save.href = url;
        save.download = entry.filename;
        save.textContent = `GIF ${index + 1} · 保存 / Save`;
        save.style.cssText = "color:#93c5fd;font:12px sans-serif;padding:4px;text-align:center";
        item.append(image, save);
        container.append(item);
    }
    node.setSize([node.size[0], Math.max(node.size[1], node.computeSize()[1])]);
    node.graph?.setDirtyCanvas(true, true);
}

function install(node) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    const previous = node.onExecuted;
    node.onExecuted = function (message) {
        const gifs = message?.zhenzhen_gifs ?? (message?.images ?? []).filter(isGif);
        if (!gifs.length) {
            render(this, []);
            return previous?.apply(this, arguments);
        }
        // Current ComfyUI treats animated .gif as video. Keep its native renderer
        // for other results, and play original GIF bytes in an HTML image instead.
        const native = { ...message, images: (message.images ?? []).filter((entry) => !isGif(entry)), zhenzhen_gifs: gifs };
        delete native.animated;
        if (app.nodeOutputs) app.nodeOutputs[String(this.id)] = native;
        const result = previous?.call(this, native);
        this.previewMediaType = "image";
        render(this, gifs);
        return result;
    };
    const configured = node.onConfigure;
    node.onConfigure = function () {
        const result = configured?.apply(this, arguments);
        requestAnimationFrame(() => {
            const cached = app.nodeOutputs?.[String(this.id)];
            if (cached?.zhenzhen_gifs?.length) render(this, cached.zhenzhen_gifs);
        });
        return result;
    };
}

app.registerExtension({
    name: "ComfyuiZhenzhen.GIFPreview",
    async nodeCreated(node) {
        const name = originalSeedanceNodeName(node.comfyClass ?? node.constructor?.comfyClass ?? node.type ?? "");
        if (TARGETS.has(name)) install(node);
    },
});
