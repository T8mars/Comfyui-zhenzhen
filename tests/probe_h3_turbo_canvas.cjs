const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 1700, height: 1100 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.goto("http://127.0.0.1:8298", { waitUntil: "networkidle", timeout: 90000 });
        await page.evaluate(async () => { window.__h3 = (await import("/scripts/app.js")).app; });
        await page.waitForFunction(() => window.__h3?.graph);
        await page.keyboard.press("Escape");
        const folder = path.join(__dirname, "..", "workflow");
        const files = fs.readdirSync(folder).filter((name) => /^zhenzhen-(minimax-h3-comfyui-max|minimax-h3-image|qwen-image-2.1-turbo)-/.test(name));
        assert.equal(files.length, 8);
        const reuse = await (await page.request.post("http://127.0.0.1:8298/h3_turbo_fixture/reuse", { data: {} })).json();
        assert.ok(reuse.ready && reuse.recorded >= 6);
        const output = process.env.H3_TURBO_SCREENSHOTS;
        if (output) fs.mkdirSync(output, { recursive: true });
        async function execute() {
            return page.evaluate(async () => {
                const app = window.__h3;
                const graph = await app.graphToPrompt();
                const { api } = await import("/scripts/api.js");
                const response = await fetch("/prompt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: graph.output, client_id: api.clientId }) });
                const submitted = await response.json();
                if (!response.ok) throw new Error(JSON.stringify(submitted));
                for (let i = 0; i < 240; i++) {
                    const record = (await (await fetch(`/history/${submitted.prompt_id}`)).json())[submitted.prompt_id];
                    if (record?.status?.completed) {
                        if (record.status.status_str !== "success") throw new Error("Native execution failed: " + JSON.stringify(record.status.messages.map((m) => m[0])));
                        return record.outputs;
                    }
                    await new Promise((resolve) => setTimeout(resolve, 500));
                }
                throw new Error("Native execution timed out");
            });
        }
        for (const filename of files) {
            const workflow = JSON.parse(fs.readFileSync(path.join(folder, filename), "utf8"));
            const report = await page.evaluate(async (workflow) => {
                const app = window.__h3;
                const settle = () => new Promise((resolve) => setTimeout(resolve, 100));
                await app.loadGraphData(workflow); await settle();
                const original = app.graph._nodes.find((node) => /^T8Zhenzhen_(Minimax_H3_|Qwen_Image_21_Turbo)/.test(node.comfyClass));
                const before = original.inputs.map(({ name, link }) => ({ name, link }));
                const widgetValues = original.serialize().widgets_values;
                original.setSize([900, original.size[1]]); original.setSize([510, original.size[1]]);
                await app.loadGraphData(app.graph.serialize()); await settle();
                const node = app.graph.getNodeById(original.id);
                for (const item of app.graph._nodes) {
                    if (item.comfyClass === "T8Zhenzhen_API_Settings") item.widgets.find((w) => w.name === "apikey").value = "sk-test";
                }
                const prompt = await app.graphToPrompt();
                return { before, after: node.inputs.map(({ name, link }) => ({ name, link })), widgetValues, afterWidgets: node.serialize().widgets_values,
                    control: node.widgets.find((w) => w.name === "control_after_generate").value,
                    footer: node.widgets.filter((w) => w.name === "贞贞的平价小屋APIKEY获取").length,
                    validation: await (await fetch("/h3_turbo_fixture/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: prompt.output }) })).json() };
            }, workflow);
            assert.deepEqual(report.before, report.after);
            assert.deepEqual(report.widgetValues, report.afterWidgets);
            assert.equal(report.control, "fixed");
            assert.equal(report.footer, 1);
            assert.equal(report.validation.valid, true, filename + ": " + JSON.stringify(report.validation));
            const result = await execute();
            const save = workflow.nodes.find((node) => node.type === (filename.includes("comfyui-max") ? "SaveVideo" : "SaveImage"));
            const entries = result[String(save.id)]?.images;
            assert.equal(entries?.length, 1, filename + ": native save");
            const response = await page.request.get("http://127.0.0.1:8298/view?" + new URLSearchParams(entries[0]));
            assert.equal(response.status(), 200);
            const bytes = await response.body();
            assert.ok(bytes.length > 1000);
            if (output) fs.writeFileSync(path.join(output, filename + ".saved" + path.extname(entries[0].filename)), bytes);
            const before = await (await page.request.get("http://127.0.0.1:8298/h3_turbo_fixture/counts")).json();
            await execute();
            assert.deepEqual(await (await page.request.get("http://127.0.0.1:8298/h3_turbo_fixture/counts")).json(), before);
            console.log("NATIVE PASS " + filename + ": resize/reload/stable sockets/footer/queue/save/Fixed cache");
        }
        const keys = ["T8Zhenzhen_Minimax_H3_ComfyUI_Max_LowPrice", "T8Zhenzhen_Minimax_H3_Image_LowPrice", "T8Zhenzhen_Qwen_Image_21_Turbo_LowPrice"];
        for (const key of keys) for (const concurrent of [false, true]) {
            const report = await page.evaluate(async ({ key, concurrent }) => {
                const app = window.__h3; app.graph.clear();
                const create = (kind) => { const node = LiteGraph.createNode(kind); app.graph.add(node); return node; };
                const node = create(concurrent ? "ComflyConcurrent_" + key + "_Submit" : key);
                const text = create("PrimitiveStringMultiline");
                text.widgets.find((w) => w.name === "value").value = "A blue ceramic cup on a white studio table.";
                window.comfyAPI.widgetInputs.convertToInput(node, node.widgets.find((w) => w.name === "prompt"));
                text.connect(0, node, node.inputs.findIndex((input) => input.name === "prompt"));
                const image = create("LoadImage");
                image.widgets[0].value = "select_h3_turbo_1.png";
                const cap = key.includes("ComfyUI_Max") ? 9 : key.includes("Minimax_H3_Image") ? 16 : 4;
                for (let i = 1; i <= cap; i++) image.connect(0, node, node.inputs.findIndex((input) => input.name === "image" + i));
                const resolution = node.widgets.find((widget) => widget.name === "resolution");
                window.comfyAPI.widgetInputs.convertToInput(node, resolution);
                const primitive = create("PrimitiveNode");
                primitive.connect(0, node, node.inputs.findIndex((input) => input.name === "resolution"));
                const tier = key.includes("ComfyUI_Max") ? "480p" : key.includes("Minimax_H3_Image") ? "1k" : "720p";
                primitive.widgets[0].value = tier;
                primitive.widgets[0].callback?.(tier);
                if (concurrent) {
                    const collector = create(key.includes("ComfyUI_Max") ? "ComflyConcurrent_Video_Await" : "ComflyConcurrent_Image_Await");
                    node.connect(0, collector, collector.inputs.findIndex((input) => input.name === "task_1"));
                }
                const before = node.inputs.map(({ name, link }) => ({ name, link }));
                node.setSize([900, node.size[1]]); node.setSize([500, node.size[1]]);
                await app.loadGraphData(app.graph.serialize());
                await new Promise((resolve) => setTimeout(resolve, 100));
                const restored = app.graph.getNodeById(node.id);
                const prompt = await app.graphToPrompt();
                return { before, after: restored.inputs.map(({ name, link }) => ({ name, link })), tier, submittedResolution: prompt.output[String(node.id)].inputs.resolution, footer: restored.widgets.filter((w) => w.name === "贞贞的平价小屋APIKEY获取").length,
                    validation: await (await fetch("/h3_turbo_fixture/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: prompt.output }) })).json() };
            }, { key, concurrent });
            assert.deepEqual(report.before, report.after);
            assert.equal(report.submittedResolution, report.tier);
            assert.equal(report.footer, 1);
            assert.equal(report.validation.valid, true, key + ": " + JSON.stringify(report.validation));
        }
        console.log("CANVAS PASS six serial/concurrent external prompts/resolutions and full-capacity reference links");
        const savedIds = await page.evaluate(() => {
            const app = window.__h3; app.graph.clear();
            const create = (key) => { const node = LiteGraph.createNode(key); app.graph.add(node); return node; };
            const config = create("T8Zhenzhen_API_Settings");
            config.widgets.find((w) => w.name === "apikey").value = "sk-test";
            const a = create("ComflyConcurrent_T8Zhenzhen_Minimax_H3_Image_LowPrice_Submit");
            const b = create("ComflyConcurrent_T8Zhenzhen_Qwen_Image_21_Turbo_LowPrice_Submit");
            for (const node of [a, b]) {
                node.widgets.find((w) => w.name === "prompt").value = "A cup on a white studio table.";
                node.widgets.find((w) => w.name === "skip_error").value = true;
                node.widgets.find((w) => w.name === "control_after_generate").value = "fixed";
                config.connect(1, node, node.inputs.findIndex((input) => input.name === "api_config"));
            }
            const collector = create("ComflyConcurrent_Image_Await");
            a.connect(0, collector, collector.inputs.findIndex((input) => input.name === "task_1"));
            b.connect(0, collector, collector.inputs.findIndex((input) => input.name === "task_2"));
            return [0, 1].map((slot) => { const save = create("SaveImage"); collector.connect(slot, save, 0); return save.id; });
        });
        await page.request.post("http://127.0.0.1:8298/h3_turbo_fixture/fail-once", { data: { case: "minimax_text" } });
        const concurrent = await execute();
        assert.ok(savedIds.every((id) => concurrent[String(id)]?.images?.length === 1));
        console.log("NATIVE PASS mixed-model concurrency with one skipped sibling failure");
        if (output) {
            await page.evaluate(async (workflow) => {
                const app = window.__h3; await app.loadGraphData(workflow);
                const node = app.graph._nodes.find((item) => item.comfyClass === "T8Zhenzhen_Minimax_H3_Image_LowPrice");
                app.canvas.ds.scale = .85; app.canvas.centerOnNode(node); app.canvas.setDirty(true, true);
            }, JSON.parse(fs.readFileSync(path.join(folder, "zhenzhen-minimax-h3-image-edit-lowprice.json"), "utf8")));
            await page.waitForTimeout(300);
            await page.screenshot({ path: path.join(output, "desktop.png") });
            await page.setViewportSize({ width: 390, height: 844 });
            await page.waitForTimeout(300);
            await page.evaluate(() => { const app = window.__h3; const node = app.graph._nodes.find((item) => item.comfyClass === "T8Zhenzhen_Minimax_H3_Image_LowPrice"); node.setSize([500, node.size[1]]); const scale = .62; app.canvas.ds.scale = scale; app.canvas.ds.offset = [65 / scale - node.pos[0], 180 / scale - node.pos[1]]; app.canvas.setDirty(true, true); });
            await page.waitForTimeout(300);
            await page.screenshot({ path: path.join(output, "mobile.png") });
        }
        assert.deepEqual(errors, []);
        console.log("PASS zero page errors; no upstream creation requests");
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
