import { app } from "../../../scripts/app.js";
import { resizeZhenzhenNode, setZhenzhenWidgetVisible } from "./dynamic_widget_ui.js";

const KEY = "T8Zhenzhen_Doubao_Seed_TTS_20_LowPrice";
const INSTALLED = Symbol("zhenzhenTTSUI");
const ADVANCED = ["voice_model", "explicit_dialect", "bit_rate", "silence_duration", "max_length_to_filter_parenthesis", "latex_parser", "ssml",
    "disable_default_bit_rate", "disable_markdown_filter", "enable_latex_tn", "disable_emoji_filter", "enable_subtitle", "tone_fidelity", "aigc_watermark", "aigc_metadata_enable",
    "section_id", "aigc_metadata_content_producer", "aigc_metadata_produce_id", "aigc_metadata_content_propagator", "aigc_metadata_propagate_id"];
let catalogPromise;

async function catalog() {
    if (!catalogPromise) catalogPromise = fetch(new URL("../data/doubao_tts_voices.json", import.meta.url)).then(async (response) => {
        if (!response.ok) throw new Error("Voice catalog request failed");
        const data = await response.json();
        if (!Array.isArray(data.voices) || !data.voices.length) throw new Error("Voice catalog is unavailable");
        return data;
    }).catch((error) => { catalogPromise = null; throw error; });
    return catalogPromise;
}

function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text) item.textContent = text;
    return item;
}

function style() {
    if (document.getElementById("zhenzhen-voice-style")) return;
    const sheet = element("style"); sheet.id = "zhenzhen-voice-style";
    sheet.textContent = `
.zhenzhen-voice-dialog{width:740px;max-width:calc(100vw - 32px);max-height:calc(100dvh - 32px);box-sizing:border-box;padding:16px;border:1px solid var(--border-color,#555);border-radius:6px;background:var(--comfy-menu-bg,#252525);color:var(--input-text,#eee);font:14px sans-serif;letter-spacing:0}
.zhenzhen-voice-dialog::backdrop{background:rgba(0,0,0,.55)}
.zhenzhen-voice-header{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px;font-size:17px}
.zhenzhen-voice-dialog button,.zhenzhen-voice-dialog input,.zhenzhen-voice-dialog select{font:inherit;letter-spacing:0;color:inherit;background:var(--comfy-input-bg,#333);border:1px solid var(--border-color,#555);border-radius:4px;box-sizing:border-box;min-width:0;padding:8px}
.zhenzhen-voice-header button{width:32px;height:32px;padding:0;cursor:pointer}
.zhenzhen-voice-search{width:100%;margin-bottom:10px}
.zhenzhen-voice-filters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:10px}
.zhenzhen-voice-results{max-height:min(58dvh,520px);overflow-y:auto;border-top:1px solid var(--border-color,#555)}
.zhenzhen-voice-results button{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--border-color,#444);border-radius:0;cursor:pointer;padding:10px 8px;background:transparent}
.zhenzhen-voice-results button:hover,.zhenzhen-voice-results button:focus-visible{background:var(--comfy-input-bg,#333)}
.zhenzhen-voice-results button[aria-selected=true]{border-left:3px solid var(--p-primary-color,#69b9df)}
.zhenzhen-voice-name{font-weight:600;margin-bottom:5px;overflow-wrap:anywhere}
.zhenzhen-voice-detail{font-size:12px;opacity:.8;overflow-wrap:anywhere;margin-top:4px}
.zhenzhen-voice-id{font-family:monospace;font-size:12px;overflow-wrap:anywhere;margin-top:5px}
.zhenzhen-voice-footer{display:flex;justify-content:space-between;gap:12px;padding-top:12px;font-size:12px}
.zhenzhen-voice-footer a{color:inherit}
@media(max-width:480px){.zhenzhen-voice-filters{grid-template-columns:minmax(0,1fr)}.zhenzhen-voice-results{max-height:45dvh}}
`;
    document.head.append(sheet);
}

async function openPicker(node) {
    if (node.inputs?.some((input) => input.name === "speaker" && input.link != null)) throw new Error("Speaker is connected to another node");
    const data = await catalog();
    style();
    const dialog = element("dialog", "zhenzhen-voice-dialog");
    dialog.setAttribute("aria-label", "Doubao voice library");
    const header = element("div", "zhenzhen-voice-header");
    header.append(element("span", "", "Doubao Voice Library"));
    const close = element("button", "", "x"); close.title = "Close"; close.setAttribute("aria-label", "Close"); close.onclick = () => dialog.close(); header.append(close);
    const search = element("input", "zhenzhen-voice-search"); search.type = "search"; search.placeholder = "Search name or voice ID"; search.setAttribute("aria-label", "Search voices");
    const filters = element("div", "zhenzhen-voice-filters");
    const select = (label, values) => {
        const item = element("select"); item.setAttribute("aria-label", label);
        for (const [value, title] of [["", label], ...values]) { const option = element("option", "", title); option.value = value; item.append(option); }
        filters.append(item); return item;
    };
    const gender = select("All genders", [["female", "Female"], ["male", "Male"]]);
    const language = select("All languages", [...new Set(data.voices.flatMap((voice) => voice.lang ?? []))].sort().map((value) => [value, value]));
    const scenes = { general: "General", roleplay: "Role-play", service: "Customer service", dubbing: "Video dubbing", audiobook: "Audiobooks", education: "Education", accent: "Accents" };
    const scene = select("All uses", Object.entries(scenes));
    const results = element("div", "zhenzhen-voice-results"); results.setAttribute("role", "listbox"); results.setAttribute("aria-label", "Voices");
    const footer = element("div", "zhenzhen-voice-footer"), count = element("span");
    const official = element("a", "", "Official voices"); official.href = data.official_source; official.target = "_blank"; official.rel = "noopener noreferrer";
    footer.append(count, official); dialog.append(header, search, filters, results, footer);
    const render = () => {
        const query = search.value.trim().toLocaleLowerCase();
        const voices = data.voices.filter((voice) => {
            const sex = voice.id.includes("_female_") ? "female" : voice.id.includes("_male_") ? "male" : "";
            const terms = [voice.name, voice.id, ...(voice.lang ?? []), ...(voice.scene ?? []), ...(voice.cap ?? [])].join(" ").toLocaleLowerCase();
            return (!query || terms.includes(query)) && (!gender.value || sex === gender.value) && (!language.value || voice.lang?.includes(language.value)) && (!scene.value || voice.scene?.includes(scene.value));
        });
        results.replaceChildren(); count.textContent = `${voices.length} / ${data.voices.length}`;
        for (const voice of voices) {
            const button = element("button"); button.type = "button"; button.setAttribute("role", "option");
            button.setAttribute("aria-selected", String(node.widgets.find((widget) => widget.name === "speaker")?.value === voice.id));
            button.append(element("div", "zhenzhen-voice-name", voice.name), element("div", "zhenzhen-voice-detail", [...(voice.lang ?? []), ...(voice.scene ?? []).map((value) => scenes[value] ?? value), ...(voice.cap ?? [])].join(" | ")), element("div", "zhenzhen-voice-id", voice.id));
            button.onclick = () => {
                if (node.inputs?.some((input) => input.name === "speaker" && input.link != null)) return;
                const speaker = node.widgets.find((widget) => widget.name === "speaker");
                speaker.value = voice.id; speaker.callback?.(voice.id); node.setDirtyCanvas?.(true, true); dialog.close();
            };
            results.append(button);
        }
    };
    search.oninput = render; gender.onchange = render; language.onchange = render; scene.onchange = render;
    dialog.onclick = (event) => { if (event.target === dialog) dialog.close(); };
    dialog.onclose = () => dialog.remove(); document.body.append(dialog); render(); dialog.showModal(); search.focus();
}

function refresh(node) {
    const widget = (name) => node.widgets?.find((item) => item.name === name);
    const advanced = Boolean(widget("advanced_mode")?.value);
    const speaker = String(widget("speaker")?.value ?? "");
    const reset = (name, value) => {
        const item = widget(name);
        if (item && item.value !== value && !Object.hasOwn(item, "origType") && !node.inputs?.some((input) => input.name === name && input.link != null)) item.value = value;
    };
    if (speaker.includes("uranus")) { reset("voice_model", "api_default"); reset("ssml", ""); }
    if (speaker !== "zh_female_vv_uranus_bigtts") reset("explicit_dialect", "api_default");
    for (const field of ADVANCED) setZhenzhenWidgetVisible(widget(field), advanced);
    setZhenzhenWidgetVisible(widget("ssml"), advanced && !speaker.includes("uranus"));
    setZhenzhenWidgetVisible(widget("voice_model"), advanced && !speaker.includes("uranus"));
    setZhenzhenWidgetVisible(widget("explicit_dialect"), advanced && speaker === "zh_female_vv_uranus_bigtts");
    setZhenzhenWidgetVisible(widget("context_texts"), widget("voice_model")?.value === "api_default");
    resizeZhenzhenNode(node, 540);
}

function install(node) {
    if (node[INSTALLED]) return;
    node[INSTALLED] = true;
    const button = node.addWidget("button", "Voice Library", null, () => openPicker(node).catch((error) => {
        app.extensionManager?.toast?.add({ severity: "error", summary: "Voice Library", detail: error.message });
    }));
    button.serialize = false;
    button.options = { ...(button.options ?? {}), serialize: false };
    const footer = node.widgets.findIndex((item) => item !== button && item.name === "贞贞的平价小屋APIKEY获取");
    if (footer >= 0) {
        node.widgets.splice(node.widgets.indexOf(button), 1);
        node.widgets.splice(footer, 0, button);
    }
    node.zhenzhenTTSRefresh = () => {
        if (node.zhenzhenTTSFrame != null) cancelAnimationFrame(node.zhenzhenTTSFrame);
        node.zhenzhenTTSFrame = requestAnimationFrame(() => { node.zhenzhenTTSFrame = null; refresh(node); });
    };
    for (const name of ["advanced_mode", "voice_model", "speaker"]) {
        const widget = node.widgets?.find((item) => item.name === name);
        if (!widget) continue;
        const previous = widget.callback;
        widget.callback = function (...args) { const result = previous?.apply(this, args); node.zhenzhenTTSRefresh(); return result; };
    }
    node.zhenzhenTTSRefresh();
}

app.registerExtension({
    name: "ComfyuiZhenzhen.DoubaoTTSUI",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== KEY) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () { const result = created?.apply(this, arguments); install(this); return result; };
        for (const hook of ["onConfigure", "onAfterGraphConfigured"]) {
            const previous = nodeType.prototype[hook];
            nodeType.prototype[hook] = function () { const result = previous?.apply(this, arguments); this.zhenzhenTTSRefresh?.(); return result; };
        }
    },
    async nodeCreated(node) { if ((node.comfyClass ?? node.constructor?.comfyClass ?? node.type) === KEY) install(node); },
});
