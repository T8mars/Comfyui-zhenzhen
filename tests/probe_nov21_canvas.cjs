// Isolated ComfyUI canvas acceptance, with no generation requests.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { chromium } = require("playwright");

(async () => {
    const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    try {
        const page = await browser.newPage({ viewport: { width: 1650, height: 1050 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.route("**/*", (route) => {
            const request = route.request();
            if (request.method() !== "POST") return route.continue();
            const url = new URL(request.url());
            if (url.origin !== "http://127.0.0.1:8298") return route.abort();
            if (!["/api/prompt", "/prompt"].includes(url.pathname)) return route.continue();
            if (process.env.ZHENZHEN_MIORA_SAMPLE) {
                const nodes = Object.values(request.postDataJSON().prompt);
                if (nodes.every((node) => ["Load3DAdvanced", "Preview3D", "SaveGLB"].includes(node.class_type)))
                    return route.continue();
            }
            return route.abort();
        });
        await page.goto("http://127.0.0.1:8298", { waitUntil: "networkidle", timeout: 90000 });
        await page.evaluate(async () => { window.__nov21 = (await import("/scripts/app.js")).app; });
        await page.keyboard.press("Escape");
        await page.waitForFunction(() => Boolean(window.__nov21?.graph && window.LiteGraph?.registered_node_types.T8Zhenzhen_Miora_3D_LowPrice));
        const folder = path.join(__dirname, "..", "workflow");
        const candidates = fs.readdirSync(folder).filter((name) => name.endsWith("-lowprice.json") &&
            /^(kling-v4-long-image-|heygen-avatar-6-|miora-3d-|zhenzhen-gm-2\.5-|zhenzhen-gm-4-|zhenzhen-hy-4-|minimax-h3-comfyui-.*-token-)/.test(name));
        assert.equal(candidates.length, 26);
        for (const file of candidates) {
            const workflow = JSON.parse(fs.readFileSync(path.join(folder, file), "utf8"));
            const state = await page.evaluate(async (workflow) => {
                const app = window.__nov21;
                const settle = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                await app.loadGraphData(workflow); await settle();
                const target = () => app.graph.getNodeById(2);
                const snapshot = () => ({
                    names: target().inputs.map((input) => input.name),
                    links: target().inputs.map((input) => input.link),
                    widgets: target().serialize().widgets_values,
                    footer: target().widgets.filter((widget) => widget.zhenzhenApiKeyAcquisitionLink).map((widget) => widget.name),
                });
                const before = snapshot();
                target().setSize([850, 800]); target().setSize([550, 650]);
                await app.loadGraphData(app.graph.serialize()); await settle();
                const prompt = await app.graphToPrompt();
                return { before, after: snapshot(), config: prompt.output[2]?.inputs.api_config,
                    missing: app.graph._nodes.filter((node) => !LiteGraph.registered_node_types[node.type]).map((node) => node.type) };
            }, workflow);
            assert.deepEqual(state.missing, [], file);
            assert.deepEqual(state.before.footer, ["贞贞的平价小屋APIKEY获取"], file);
            assert.deepEqual(state.after, state.before, file);
            assert.deepEqual(state.config, ["1", 1], file);
        }
        console.log("PASS 26 workflows loaded, resized and round-tripped with links and Low Price footers intact");

        const count = await page.evaluate(async () => {
            const app = window.__nov21;
            const settle = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            let count = 0;
            for (const [key, max] of [
                ["T8Zhenzhen_Kling_V4_Long_Image_LowPrice", 3],
                ["ComflyConcurrent_T8Zhenzhen_Kling_V4_Long_Image_LowPrice_Submit", 3],
                ["T8Zhenzhen_Minimax_H3_ComfyUI_Max_10020_Token_LowPrice", 6],
                ["ComflyConcurrent_T8Zhenzhen_Minimax_H3_ComfyUI_Max_10021_Token_LowPrice_Submit", 6],
                ["T8Zhenzhen_Minimax_H3_ComfyUI_CharSwap_Token_LowPrice", 5],
                ["T8Zhenzhen_Miora_3D_LowPrice", 8],
            ]) {
                app.graph.clear();
                const node = LiteGraph.createNode(key), source = LiteGraph.createNode("EmptyImage");
                app.graph.add(node); node.pos = [550, 100];
                app.graph.add(source); source.pos = [100, 100];
                await settle();
                for (let i = 1; i <= max; i++) {
                    const field = "image" + i, slot = node.inputs.findIndex((input) => input.name === field);
                    const where = node.getConnectionPos(true, slot);
                    if (node.inputs[slot].hidden || node.getSlotInPosition(...where)?.input?.name !== field)
                        throw Error(`${key} ${field} not connectable`);
                    const later = node.inputs.find((input) => input.name === "image" + (i + 1));
                    if (later && !later.hidden) throw Error(`${key} ${later.name} exposed prematurely`);
                    if (!source.connect(0, node, slot)) throw Error(`Failed to connect ${key} ${field}`);
                    await settle();
                    count++;
                }
                node.disconnectInput(node.findInputSlot("image" + max)); await settle();
                if (node.inputs.find((input) => input.name === "image" + max).hidden) throw Error("Disconnect hid the next usable socket");
                const mode = node.widgets.find((widget) => widget.name === "skill");
                if (mode) {
                    mode.value = "webpage"; mode.callback?.(mode.value); await settle();
                    if (node.inputs.find((input) => input.name === "style_image").hidden
                        || node.inputs.find((input) => input.name === "image1").hidden
                        || !node.inputs.find((input) => input.name === "image" + max).hidden)
                        throw Error("Kling mode switch lost linked product references or failed to expose style");
                }
            }
            return count;
        });
        assert.equal(count, 31);
        if (process.env.ZHENZHEN_MIORA_SAMPLE) {
            const previewId = await page.evaluate(() => {
                const app = window.__nov21;
                app.graph.clear();
                const preview = LiteGraph.createNode("Preview3D");
                app.graph.add(preview); preview.pos = [430, 80]; preview.setSize([650, 650]);
                app.canvas.ds.scale = .88; app.canvas.ds.offset = [90, 70]; app.canvas.setDirty(true, true);
                return String(preview.id);
            });
            await page.waitForFunction((id) => typeof window.__nov21.graph.getNodeById(id)?.onExecuted === "function", previewId);
            const { files, previewResult } = await page.evaluate(async () => {
                const prompt = {
                    1: { class_type: "Load3DAdvanced", inputs: {
                        model_file: "3d/zz-miora-proof.glb", viewport_state: {}, width: 1024, height: 1024,
                    } },
                    2: { class_type: "Preview3D", inputs: { model_file: ["1", 0] } },
                    3: { class_type: "SaveGLB", inputs: { mesh: ["1", 0], filename_prefix: "miora-proof" } },
                };
                const response = await fetch("/prompt", { method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ prompt }) });
                const submitted = await response.json();
                if (!response.ok) throw Error(JSON.stringify(submitted));
                for (let i = 0; i < 80; i++) {
                    const result = (await (await fetch(`/history/${submitted.prompt_id}`)).json())[submitted.prompt_id];
                    if (result?.status?.completed) {
                        if (result.status.status_str !== "success") throw Error(JSON.stringify(result.status));
                        return { files: result.outputs["3"]["3d"], previewResult: result.outputs["2"] };
                    }
                    await new Promise((resolve) => setTimeout(resolve, 250));
                }
                throw Error("Native Miora preview/save timed out");
            });
            assert.equal(files.length, 1);
            const file = files[0];
            const query = new URLSearchParams({ filename: file.filename, subfolder: file.subfolder ?? "", type: "output" });
            const response = await page.request.get(`http://127.0.0.1:8298/view?${query}`);
            assert.equal(response.status(), 200);
            const hash = (buffer) => crypto.createHash("sha256").update(buffer).digest("hex");
            assert.equal(hash(await response.body()), hash(fs.readFileSync(process.env.ZHENZHEN_MIORA_SAMPLE)));
            await Promise.all([
                page.waitForResponse((response) => response.ok() && response.url().includes(previewResult.result[0]), { timeout: 30000 }),
                page.evaluate(({ id, output }) => window.__nov21.graph.getNodeById(id).onExecuted(output),
                    { id: previewId, output: previewResult }),
            ]);
            const canvas = () => page.evaluate(() => [...document.querySelectorAll("canvas")].map((canvas) => {
                const r = canvas.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height };
            }).filter((r) => r.x > 50 && r.width > 150 && r.width < 850 && r.height > 150)
                .sort((a, b) => b.width * b.height - a.width * a.height)[0]);
            const capture = async (viewport) => {
                const data = await page.screenshot({ clip: viewport });
                const { PNG } = require("pngjs"), pixels = PNG.sync.read(data).data, colors = new Set();
                for (let i = 0; i < pixels.length; i += 32) colors.add(pixels.readUInt32BE(i));
                assert.ok(colors.size > 100, "Expected a rendered 3D object, not a blank canvas");
                return data;
            };
            await page.waitForTimeout(2200);
            const viewport = await canvas();
            assert.ok(viewport, "Miora desktop preview canvas missing");
            const before = await capture(viewport);
            await page.mouse.move(viewport.x + viewport.width * .5, viewport.y + viewport.height * .5);
            await page.mouse.down();
            await page.mouse.move(viewport.x + viewport.width * .72, viewport.y + viewport.height * .59, { steps: 15 });
            await page.mouse.up(); await page.waitForTimeout(500);
            assert.notEqual(hash(before), hash(await capture(viewport)));
            await page.setViewportSize({ width: 390, height: 844 });
            await page.evaluate(() => {
                const app = window.__nov21;
                app.canvas.ds.scale = .43; app.canvas.ds.offset = [-250, 120]; app.canvas.setDirty(true, true);
            });
            await page.waitForTimeout(650);
            const mobile = await canvas();
            assert.ok(mobile && mobile.x + mobile.width <= 390 && mobile.y + mobile.height <= 844);
            await capture(mobile);
            console.log("PASS actual Miora GLB saved byte-for-byte and rendered interactively at desktop and mobile sizes");
        }
        assert.deepEqual(errors, []);
        console.log("PASS 31 progressive connections, hit testing, disconnection and mode switching; zero page errors");
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
