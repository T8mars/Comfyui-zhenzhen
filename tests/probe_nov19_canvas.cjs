// Real ComfyUI frontend, with every generation request blocked.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const workflow = path.join(__dirname, "..", "workflow");

(async () => {
    const browser = await chromium.launch();
    try {
        const page = await browser.newPage({ viewport: { width: 1700, height: 1300 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.route("**/*", (route) => route.request().method() === "POST" ? route.abort() : route.continue());
        await page.goto("http://127.0.0.1:8298", { waitUntil: "networkidle" });
        await page.evaluate(async () => { window.__nov19 = (await import("/scripts/app.js")).app; });
        await page.keyboard.press("Escape");
        await page.waitForFunction(() => Boolean(window.__nov19?.graph && window.LiteGraph?.registered_node_types.Comfly_LLm_API));
        const files = fs.readdirSync(workflow).filter((name) => /^zhenzhen-(kling-v4-image-|mai-image-2-7-|qwen-audio-3\.1-tts-|g6\.2-)/.test(name));
        assert.equal(files.length, 15);
        for (const file of files) {
            const data = JSON.parse(fs.readFileSync(path.join(workflow, file), "utf8"));
            const report = await page.evaluate(async (data) => {
                const app = window.__nov19;
                const settle = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve))));
                await app.loadGraphData(data); await settle();
                const target = () => app.graph.getNodeById(2);
                const snapshot = () => ({
                    key: target().comfyClass,
                    links: target().inputs.map(({ name, link }) => ({ name, link })),
                    values: target().serialize().widgets_values,
                    footer: target().widgets.filter((item) => item.name === "贞贞的平价小屋APIKEY获取").length,
                });
                const before = snapshot();
                const prompt = await app.graphToPrompt();
                target().setSize([900, 800]); target().setSize([540, 650]);
                await app.loadGraphData(app.graph.serialize()); await settle();
                return { before, after: snapshot(), inputs: prompt.output[2]?.inputs,
                    missing: app.graph._nodes.filter((node) => !LiteGraph.registered_node_types[node.type]).map((node) => node.type) };
            }, data);
            assert.deepEqual(report.missing, [], file);
            assert.equal(report.before.footer, 1, file);
            assert.deepEqual(report.after, report.before, file);
            assert.deepEqual(report.inputs.api_config, ["1", 1], file);
            if (file.includes("astra")) {
                assert.equal(report.inputs.model_preset, "zhenzhen/g6.2-astra");
                assert.equal(report.inputs.stream, false);
                assert.equal(report.inputs.max_tokens, 512);
            }
            if (file.includes("vision-stream")) {
                assert.equal(report.inputs.model_preset, "zhenzhen/g6.2-sol");
                assert.equal(report.inputs.stream, true);
                assert.deepEqual(report.inputs.ref_image, ["3", 0]);
            }
        }
        console.log("PASS 15 examples load, keep their links and widgets on reload, and use the Low Price footer");

        for (const file of ["zhenzhen-llm-api-Image-expansione.json", "zhenzhen-llm-api-Identify-the-image.json", "zhenzhen-video-analyze.json"]) {
            const data = JSON.parse(fs.readFileSync(path.join(workflow, file), "utf8"));
            const legacy = data.nodes.find((node) => node.type === "Comfly_LLm_API");
            // Isolate the existing node from unrelated third-party viewer/loader nodes.
            legacy.widgets_values[1] = "";
            for (const slot of legacy.inputs ?? []) slot.link = null;
            const state = await page.evaluate(async (legacy) => {
                const app = window.__nov19;
                app.graph.clear();
                const node = LiteGraph.createNode(legacy.type);
                app.graph.add(node);
                node.configure(legacy);
                await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                return { prefix: node.serialize().widgets_values.slice(0, legacy.widgets_values.length),
                    preset: node.widgets.find((item) => item.name === "model_preset").value };
            }, legacy);
            assert.deepEqual(state.prefix, legacy.widgets_values, file);
            assert.equal(state.preset, "custom", file);
        }
        console.log("PASS three bundled legacy LLM widget prefixes and custom defaults");

        const result = await page.evaluate(async () => {
            const app = window.__nov19, rows = [];
            const settle = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve))));
            const specs = [
                ["T8Zhenzhen_Kling_V4_Image_LowPrice", "image", 10],
                ["T8Zhenzhen_MAI_Image_27_LowPrice", "image", 5],
                ["ComflyConcurrent_T8Zhenzhen_MAI_Image_27_LowPrice_Submit", "image", 5],
                ["T8Zhenzhen_Qwen_Audio_31_TTS_LowPrice", "audio", 3],
            ];
            for (const [key, family, count] of specs) {
                app.graph.clear();
                let node = LiteGraph.createNode(key);
                app.graph.add(node); node.pos = [750, 100];
                const source = LiteGraph.createNode(family === "audio" ? "LoadAudio" : "EmptyImage");
                app.graph.add(source); source.pos = [100, 100];
                const widget = (name) => node.widgets.find((item) => item.name === name);
                const change = (name, value) => { const item = widget(name); item.value = value; item.callback?.(value); };
                await settle();
                if (family === "audio") {
                    if (!node.inputs.filter((item) => /^audio\d+$/.test(item.name)).every((item) => item.hidden)) throw Error("Flash exposes reference audio");
                    change("model", "qwen-audio-3.1-tts-plus"); await settle();
                    if (widget("voice").options.values.length !== 5) throw Error("Plus voice options are not filtered");
                    change("model", "qwen-audio-3.1-tts-next"); await settle();
                }
                for (let i = 1; i <= count; i++) {
                    const name = family + i;
                    const slot = node.inputs.findIndex((item) => item.name === name);
                    const item = node.inputs[slot];
                    const pos = node.getConnectionPos(true, slot);
                    if (item.hidden || node.getSlotInPosition(...pos)?.input?.name !== name) throw Error(key + ": not connectable: " + name);
                    const next = node.inputs.find((item) => item.name === family + (i + 1));
                    if (next && !next.hidden) throw Error(key + ": exposed too soon: " + next.name);
                    if (!source.connect(0, node, slot)) throw Error(key + ": failed to link " + name);
                    await settle();
                }
                const id = node.id;
                const links = node.inputs.map((item) => item.link);
                await app.loadGraphData(app.graph.serialize()); await settle();
                node = app.graph.getNodeById(id);
                if (JSON.stringify(node.inputs.map((item) => item.link)) !== JSON.stringify(links)) throw Error(key + ": links shifted");
                if (family === "audio") {
                    change("model", "qwen-audio-3.1-tts-flash"); await settle();
                    if (widget("voice").options.values.length !== 70) throw Error("Flash voice options are not restored");
                    if (node.inputs.filter((item) => /^audio\d+$/.test(item.name)).some((item) => item.hidden || item.link == null)) throw Error("Switching model discarded connected audio");
                }
                rows.push({ key, connected: count });
            }
            return rows;
        });
        assert.equal(result.reduce((sum, row) => sum + row.connected, 0), 23);
        assert.deepEqual(errors, []);
        console.log("PASS 23 progressive image/audio connections, disconnect-safe mode switching and reload; zero page errors");
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
