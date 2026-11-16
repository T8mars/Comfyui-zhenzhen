// No generation POSTs. Verify actual rendered/hit-testable sockets, not just schemas.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const ROOT = path.join(__dirname, "..");
const keys = new Set();
for (const name of fs.readdirSync(path.join(ROOT, "web/js"))) {
    if (!name.endsWith(".js")) continue;
    const code = fs.readFileSync(path.join(ROOT, "web/js", name), "utf8");
    if (!code.includes("setZhenzhenInputVisible")) continue;
    for (const match of code.matchAll(/\b(?:T8Zhenzhen_|Comfly_)[A-Za-z0-9_]+/g)) keys.add(match[0]);
}
for (const kind of ["T2V", "I2V", "Omni", "Custom_Element", "Custom_Voice"]) keys.add(`T8Zhenzhen_Kling_V4_${kind}_LowPrice`);

(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 1800, height: 1300 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.route("**/*", (route) => {
            const request = route.request();
            if (request.method() === "POST" && /\/prompt(?:\?|$)|\/v1\/|\/upload\//.test(request.url())) return route.abort();
            return route.continue();
        });
        await page.goto("http://127.0.0.1:8298", { waitUntil: "networkidle", timeout: 90000 });
        await page.evaluate(async () => { window.__ports = (await import("/scripts/app.js")).app; });
        await page.waitForFunction(() => window.__ports?.graph);
        await page.keyboard.press("Escape");
        const info = await (await page.request.get("http://127.0.0.1:8298/object_info")).json();
        let profiles = 0, families = 0;
        const selected = process.env.ZHENZHEN_PORT_KEYS?.split(",");
        for (const base of [...keys].filter((key) => info[key] && (!selected || selected.includes(key))).sort()) {
            const schema = { ...info[base].input.required, ...info[base].input.optional };
            if (!Object.values(schema).some((spec) => ["IMAGE", "VIDEO", "AUDIO"].includes(spec[0]))) continue;
            families++;
            for (const key of [base, `ComflyConcurrent_${base}_Submit`].filter((key) => info[key])) {
                const report = await page.evaluate(async ({ key }) => {
                    const app = window.__ports;
                    const settle = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                    const markers = new Set(["__zhenzhen_hidden_input__", "__seedance_hidden_input__"]);
                    const media = (node) => node.inputs.filter((input) => ["IMAGE", "VIDEO", "AUDIO"].includes(String(input.type)));
                    const check = (node) => {
                        const positions = new Set();
                        for (const input of media(node).filter((input) => !input.hidden || input.link != null)) {
                            const index = node.inputs.indexOf(input);
                            const pos = Array.from(node.getConnectionPos(true, index, new Float32Array(2)));
                            if (pos.some((value) => !Number.isFinite(value) || value < -50000) || markers.has(input.widget?.name)) throw new Error(`${key}/${input.name}: raw slot remains hidden`);
                            const concrete = node._concreteInputs?.find((item) => item.name === input.name);
                            if (markers.has(concrete?.widget?.name) || concrete?.pos?.[0] === -100000) throw new Error(`${key}/${input.name}: concrete slot remains hidden`);
                            const hit = node.getSlotInPosition(...pos);
                            if (hit?.input?.name !== input.name) throw new Error(`${key}/${input.name}: socket not hit-testable (${hit?.input?.name})`);
                            const token = pos.join(",");
                            if (positions.has(token)) throw new Error(`${key}/${input.name}: socket overlaps`);
                            positions.add(token);
                        }
                    };
                    app.graph.clear();
                    let node = LiteGraph.createNode(key); app.graph.add(node);
                    const selectors = node.widgets.filter((widget) => ["model", "mode", "operation", "modal_mode", "reference_type", "input_mode", "texture_prompt_mode", "source_mode", "seg_type"].includes(widget.name)
                        && Array.isArray(widget.options?.values));
                    let variants = [{}];
                    for (const widget of selectors) variants = variants.flatMap((variant) => widget.options.values.map((value) => ({ ...variant, [widget.name]: value })));
                    const results = [];
                    for (const values of variants) {
                        app.graph.clear(); node = LiteGraph.createNode(key); app.graph.add(node); node.pos = [600, 100];
                        for (const [name, value] of Object.entries(values)) {
                            const widget = node.widgets.find((item) => item.name === name); widget.value = value; widget.callback?.(value);
                        }
                        await settle();
                        const managed = new Set(node.inputs.filter((input) => typeof input.hidden === "boolean").map((input) => input.name));
                        const dirty = app.graph.serialize();
                        for (const input of dirty.nodes.find((item) => item.type === key).inputs.filter((input) => managed.has(input.name) && ["IMAGE", "VIDEO", "AUDIO"].includes(String(input.type)))) {
                            input.widget = { name: "__zhenzhen_hidden_input__" }; input.pos = [-100000, -100000]; input.hidden = true;
                        }
                        await app.loadGraphData(dirty); await settle();
                        node = app.graph._nodes.find((item) => item.comfyClass === key);
                        const originalNames = node.inputs.map((input) => input.name);
                        check(node);
                        const counts = {};
                        for (const prefix of ["image", "video", "audio"]) {
                            const inputs = node.inputs.filter((input) => new RegExp(`^${prefix}\\d+$`).test(input.name));
                            if (!inputs.length) continue;
                            const source = LiteGraph.createNode("EmptyImage"); app.graph.add(source);
                            source.outputs[0].type = prefix === "image" ? "IMAGE" : prefix.toUpperCase();
                            let count = 0;
                            for (const input of inputs) {
                                if (input.hidden && input.link == null) break;
                                if (!source.connect(0, node, node.inputs.indexOf(input))) throw new Error(`${key}/${input.name}: connection rejected`);
                                await settle(); check(node); count++;
                            }
                            counts[prefix] = count;
                            const beforeLinks = node.inputs.map(({ name, link }) => ({ name, link }));
                            await app.loadGraphData(app.graph.serialize()); await settle();
                            node = app.graph._nodes.find((item) => item.comfyClass === key); check(node);
                            if (JSON.stringify(node.inputs.map(({ name, link }) => ({ name, link }))) !== JSON.stringify(beforeLinks)) throw new Error(`${key}: linked ${prefix} slots changed on reload`);
                            // Mutually exclusive image/video profiles are tested independently.
                            for (const input of node.inputs.filter((item) => new RegExp(`^${prefix}\\d+$`).test(item.name))) if (input.link != null) node.disconnectInput(node.inputs.indexOf(input));
                            await settle(); check(node);
                            app.graph.remove(app.graph.getNodeById(source.id));
                        }
                        for (const width of [900, 510]) { node.setSize([width, node.size[1]]); await settle(); check(node); }
                        const widgetValues = node.serialize().widgets_values;
                        const clean = app.graph.serialize();
                        if (clean.nodes.some((item) => item.inputs?.some((input) => markers.has(input.widget?.name) || input.pos?.[0] === -100000))) throw new Error(`${key}: temporary data leaked to workflow`);
                        await app.loadGraphData(clean); await settle(); node = app.graph._nodes.find((item) => item.comfyClass === key); check(node);
                        if (JSON.stringify(node.inputs.map((input) => input.name)) !== JSON.stringify(originalNames)) throw new Error(`${key}: input order changed`);
                        if (JSON.stringify(node.serialize().widgets_values) !== JSON.stringify(widgetValues)) throw new Error(`${key}: widget values changed`);
                        const base = key.replace(/^ComflyConcurrent_(.*)_Submit$/, "$1");
                        if (base === "T8Zhenzhen_GPT_Image_2_6_Workshop" && counts.image !== 16) throw new Error("Workshop does not reach 16 references");
                        if (base === "T8Zhenzhen_Image_G26_LowPrice" && counts.image !== (values.mode === "gif" ? 0 : 16)) throw new Error("G2.6 does not reach its reference limit");
                        if (base === "T8Zhenzhen_Seedream_55_Image_LowPrice" && counts.image !== (values.model.endsWith("-i2i") ? 10 : 0)) throw new Error("Seedream 5.5 does not reach its reference limit");
                        if (base === "Comfly_zhenzhen_video_v31_lowprice" && counts.image !== (values.model.endsWith("-lite") ? 0 : values.model.endsWith("-quality") ? 2 : 3)) throw new Error("V3.1 media visibility does not match the selected model");
                        results.push({ values, counts });
                    }
                    return results;
                }, { key });
                profiles += report.length;
                console.log(`CANVAS PASS ${key}: ${report.length} profiles, actual positions/hit testing/old markers/disconnect/resize/reload`);
            }
        }
        const output = process.env.ZHENZHEN_PORT_SCREENSHOTS;
        if (output) fs.mkdirSync(output, { recursive: true });
        let mouseConnections = 0;
        for (const [base, model, maximum] of [
            ["T8Zhenzhen_Image_G26_LowPrice", "zhenzhen-image-g-v2.6-lowprice", 16],
            ["T8Zhenzhen_GPT_Image_2_6_Workshop", "gpt-image-2.6-flare", 16],
            ["T8Zhenzhen_Seedream_55_Image_LowPrice", "dola-seedream-5.5-i2i", 10],
        ]) for (const key of [base, `ComflyConcurrent_${base}_Submit`]) {
            await page.evaluate(async ({ key, model }) => {
                const app = window.__ports; app.graph.clear();
                const node = LiteGraph.createNode(key); app.graph.add(node); node.pos = [650, 100];
                const source = LiteGraph.createNode("EmptyImage"); app.graph.add(source); source.pos = [100, 100];
                const widget = node.widgets.find((item) => item.name === "model"); widget.value = model; widget.callback?.(model);
                await new Promise((resolve) => setTimeout(resolve, 100));
                const dirty = app.graph.serialize();
                for (const input of dirty.nodes.find((item) => item.type === key).inputs.filter((input) => /^image\d+$/.test(input.name))) {
                    input.pos = [-100000, -100000]; input.widget = { name: key.startsWith("ComflyConcurrent_") ? "__seedance_hidden_input__" : "__zhenzhen_hidden_input__" }; input.hidden = true;
                }
                await app.loadGraphData(dirty);
                app.canvas.ds.scale = .9; app.canvas.ds.offset = [0, 0]; app.canvas.setDirty(true, true);
            }, { key, model });
            for (let index = 1; index <= maximum; index++) {
                await page.waitForTimeout(90);
                const points = await page.evaluate(({ key, index, maximum }) => {
                    const app = window.__ports, node = app.graph._nodes.find((item) => item.comfyClass === key), source = app.graph._nodes.find((item) => item.comfyClass === "EmptyImage");
                    const slot = node.inputs.findIndex((input) => input.name === `image${index}`);
                    if (node.inputs[slot].hidden) throw new Error(`${key}/image${index}: next socket did not expand`);
                    const visible = node.inputs.filter((input) => /^image\d+$/.test(input.name) && !input.hidden).length;
                    if (visible !== Math.min(maximum, index)) throw new Error(`${key}: ports must expand progressively, not remain all visible (${visible}/${index})`);
                    const rect = app.canvas.canvas.getBoundingClientRect(), ds = app.canvas.ds;
                    const screen = (pos) => [rect.left + (pos[0] + ds.offset[0]) * ds.scale, rect.top + (pos[1] + ds.offset[1]) * ds.scale];
                    return { from: screen(source.getConnectionPos(false, 0)), to: screen(node.getConnectionPos(true, slot)) };
                }, { key, index, maximum });
                await page.mouse.move(...points.from); await page.mouse.down(); await page.mouse.move(...points.to, { steps: 8 }); await page.mouse.up();
                await page.waitForTimeout(60);
                assert.equal(await page.evaluate(({ key, index }) => window.__ports.graph._nodes.find((item) => item.comfyClass === key).inputs.find((input) => input.name === `image${index}`).link != null, { key, index }), true, `${key}: mouse connection ${index}`);
                mouseConnections++;
            }
            const roundtrip = await page.evaluate(async (key) => {
                const app = window.__ports, node = app.graph._nodes.find((item) => item.comfyClass === key);
                const before = node.inputs.map(({ name, link }) => ({ name, link }));
                for (const name of ["model", "mode"]) {
                    const widget = node.widgets.find((item) => item.name === name);
                    if (!Array.isArray(widget?.options?.values)) continue;
                    const initial = widget.value;
                    for (const value of [...widget.options.values, initial]) {
                        widget.value = value; widget.callback?.(value);
                        await new Promise((resolve) => setTimeout(resolve, 70));
                        if (JSON.stringify(node.inputs.map(({ name, link }) => ({ name, link }))) !== JSON.stringify(before)) throw new Error(`${key}: model/mode switch changed real slots or links`);
                        for (const input of node.inputs.filter((item) => /^image\d+$/.test(item.name) && item.link != null)) {
                            if (input.hidden || input.widget?.name === "__zhenzhen_hidden_input__") throw new Error(`${key}: model switch hid a connected reference`);
                        }
                    }
                }
                await app.loadGraphData(app.graph.serialize());
                await new Promise((resolve) => setTimeout(resolve, 100));
                const restored = app.graph._nodes.find((item) => item.comfyClass === key);
                const prompt = await app.graphToPrompt();
                return { before, after: restored.inputs.map(({ name, link }) => ({ name, link })),
                    references: Object.keys(prompt.output[String(restored.id)].inputs).filter((name) => /^image\d+$/.test(name)) };
            }, key);
            assert.deepEqual(roundtrip.before, roundtrip.after);
            assert.deepEqual(roundtrip.references, Array.from({ length: maximum }, (_, index) => `image${index + 1}`));
            const converted = await page.evaluate(async (key) => {
                const app = window.__ports;
                let node = app.graph._nodes.find((item) => item.comfyClass === key);
                const prompt = node.widgets.find((item) => item.name === "prompt");
                const text = LiteGraph.createNode("PrimitiveStringMultiline"); app.graph.add(text);
                text.widgets.find((item) => item.name === "value").value = "Keep the reference subjects and edit the background.";
                window.comfyAPI.widgetInputs.convertToInput(node, prompt);
                text.connect(0, node, node.inputs.findIndex((input) => input.name === "prompt"));
                const resolution = node.widgets.find((item) => item.name === "resolution");
                if (resolution) {
                    window.comfyAPI.widgetInputs.convertToInput(node, resolution);
                    const primitive = LiteGraph.createNode("PrimitiveNode"); app.graph.add(primitive);
                    primitive.connect(0, node, node.inputs.findIndex((input) => input.name === "resolution"));
                    primitive.widgets[0].value = "1k"; primitive.widgets[0].callback?.("1k");
                }
                await new Promise((resolve) => setTimeout(resolve, 100));
                const before = node.inputs.map(({ name, link }) => ({ name, link }));
                await app.loadGraphData(app.graph.serialize()); await new Promise((resolve) => setTimeout(resolve, 100));
                node = app.graph._nodes.find((item) => item.comfyClass === key);
                return { before, after: node.inputs.map(({ name, link }) => ({ name, link })),
                    promptWidget: node.inputs.find((input) => input.name === "prompt").widget?.name,
                    resolutionWidget: resolution ? node.inputs.find((input) => input.name === "resolution").widget?.name : null };
            }, key);
            assert.deepEqual(converted.before, converted.after);
            assert.equal(converted.promptWidget, "prompt");
            if (converted.resolutionWidget !== null) assert.equal(converted.resolutionWidget, "resolution");
            if (output) await page.screenshot({ path: path.join(output, key + ".png") });
            console.log(`MOUSE PASS ${key}: ${maximum} real drag connections plus linked workflow reload`);
        }
        assert.deepEqual(errors, []);
        console.log(`PASS ${families} families, ${profiles} model/mode/serial/concurrent profiles, ${mouseConnections} physical connections; zero page errors and no generation requests`);
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
