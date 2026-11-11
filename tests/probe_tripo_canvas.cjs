// Optional isolated-server acceptance: workflow validation and local media only.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { chromium } = require("playwright");
const { PNG } = require("pngjs");

function nonblank(buffer) {
    const png = PNG.sync.read(buffer);
    const colors = new Set();
    for (let i = 0; i < png.data.length; i += 16) colors.add(`${png.data[i]},${png.data[i+1]},${png.data[i+2]}`);
    assert.ok(colors.size > 100, `3D canvas lacks visible image detail (${colors.size} sampled colors)`);
}

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.ZHENZHEN_BROWSER_EXECUTABLE,
        args: ["--enable-unsafe-swiftshader"] });
    try {
        const page = await browser.newPage({ viewport: { width: 1700, height: 1100 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.goto(process.env.ZHENZHEN_TRIPO_UI_URL ?? "http://127.0.0.1:8298", { waitUntil: "networkidle", timeout: 90000 });
        await page.evaluate(async () => { window.__tripoApp = (await import("/scripts/app.js")).app; });
        await page.waitForFunction(() => window.__tripoApp?.graph);
        await page.keyboard.press("Escape");
        const folder = path.join(__dirname, "..", "workflow");
        const files = fs.readdirSync(folder).filter((name) => /^zhenzhen-tripo-.*-lowprice\.json$/.test(name));
        assert.equal(files.length, 29);
        for (const filename of files) {
            const workflow = JSON.parse(fs.readFileSync(path.join(folder, filename), "utf8"));
            const report = await page.evaluate(async (workflow) => {
                const app = window.__tripoApp;
                const settle = () => new Promise((resolve) => setTimeout(resolve, 90));
                await app.loadGraphData(workflow); await settle();
                const sources = app.graph._nodes.filter((node) => node.comfyClass?.startsWith("T8Zhenzhen_Tripo_"));
                const before = sources.map((node) => ({ id: node.id, inputs: node.inputs.map((input) => input.name),
                    links: node.inputs.map((input) => input.link), widgets: node.serialize().widgets_values,
                    model: node.widgets.find((widget) => widget.name === "model").value }));
                for (const source of sources) {
                    const model = source.widgets.find((widget) => widget.name === "model");
                    const original = model.value;
                    for (const value of [...model.options.values, original]) {
                        model.value = value; model.callback?.(value); await settle();
                    }
                    source.setSize([850, source.size[1]]); source.setSize([510, source.size[1]]);
                }
                await app.loadGraphData(app.graph.serialize()); await settle();
                const prompt = await app.graphToPrompt();
                const response = await fetch("/zhenzhen_tripo_fixture/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: prompt.output }) });
                const validation = await response.json();
                return { validation, nodes: before.map((previous) => {
                    const node = app.graph.getNodeById(previous.id);
                    return { previous, inputs: node.inputs.map((input) => input.name), links: node.inputs.map((input) => input.link),
                        widgets: node.serialize().widgets_values, values: prompt.output[String(node.id)].inputs,
                        footer: node.widgets.filter((item) => item.name === "贞贞的平价小屋APIKEY获取").length,
                        outputs: node.outputs.length, control: node.widgets.find((widget) => widget.name === "control_after_generate").value };
                }) };
            }, workflow);
            if (!report.validation.valid) console.log(JSON.stringify(report));
            assert.equal(report.validation.valid, true, `${filename}: ${JSON.stringify(report.validation)}`);
            for (const node of report.nodes) {
                assert.deepEqual(node.inputs, node.previous.inputs);
                assert.deepEqual(node.links, node.previous.links);
                assert.deepEqual(node.widgets, node.previous.widgets);
                assert.equal(node.values.model, node.previous.model);
                assert.equal(node.outputs, 8);
                assert.equal(node.footer, 1);
                assert.equal(node.control, "fixed");
                assert.equal(node.values.seed, 0);
                assert.ok(Array.isArray(node.values.api_config));
            }
            console.log(`CANVAS PASS ${filename}: model switching, resize, reload, links and backend queue validation`);
        }
        const directory = process.env.ZHENZHEN_UI_SCREENSHOT_DIR;
        if (directory) fs.mkdirSync(directory, { recursive: true });
        for (const filename of ["generated.glb", "segmented.glb", "completed.glb"]) {
            await page.setViewportSize({ width: 1700, height: 1100 });
            const saved = await page.evaluate(async (filename) => {
                const app = window.__tripoApp;
                app.graph.clear();
                const fixture = window.LiteGraph.createNode("T8ZhenzhenTripoLocalFixture");
                const preview = window.LiteGraph.createNode("Preview3D");
                const save = window.LiteGraph.createNode("SaveGLB");
                for (const node of [fixture, preview, save]) app.graph.add(node);
                fixture.widgets.find((widget) => widget.name === "model_file").value = filename;
                fixture.pos = [40, 180]; preview.pos = [420, 80]; save.pos = [1200, 180];
                preview.setSize([650, 650]);
                assertLink(fixture.connect(0, preview, preview.inputs.findIndex((item) => item.name === "model_file")));
                assertLink(fixture.connect(0, save, save.inputs.findIndex((item) => item.name === "mesh")));
                function assertLink(link) { if (!link) throw new Error("Native FILE_3D connection failed"); }
                app.canvas.ds.scale = .88; app.canvas.ds.offset = [90, 70]; app.canvas.setDirty(true, true);
                const prompt = await app.graphToPrompt();
                const { api } = await import("/scripts/api.js");
                const response = await fetch("/prompt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
                    prompt: prompt.output, client_id: api.clientId, extra_data: { extra_pnginfo: { workflow: prompt.workflow } } }) });
                const submitted = await response.json();
                if (!response.ok) throw new Error(JSON.stringify(submitted));
                let record;
                for (let i = 0; i < 60; i++) {
                    record = (await (await fetch(`/history/${submitted.prompt_id}`)).json())[submitted.prompt_id];
                    if (record?.status?.completed) break;
                    await new Promise((resolve) => setTimeout(resolve, 200));
                }
                if (record?.status?.status_str !== "success") throw new Error(JSON.stringify(record?.status));
                preview.onExecuted?.(record.outputs[String(preview.id)]);
                return record.outputs[String(save.id)]["3d"];
            }, filename);
            assert.ok(saved.length > 0);
            if (process.env.ZHENZHEN_TRIPO_PROOF_DIR) {
                const file = saved[0];
                const query = new URLSearchParams({ filename: file.filename, subfolder: file.subfolder ?? "", type: "output" });
                const response = await page.request.get(`http://127.0.0.1:8298/view?${query}`);
                assert.equal(response.status(), 200);
                const original = fs.readFileSync(path.join(process.env.ZHENZHEN_TRIPO_PROOF_DIR, filename));
                assert.equal(crypto.createHash("sha256").update(await response.body()).digest("hex"),
                    crypto.createHash("sha256").update(original).digest("hex"));
            }
            await page.waitForTimeout(1800);
            const viewport = await page.evaluate(() => Array.from(document.querySelectorAll("canvas")).map((canvas) => {
                const r = canvas.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height };
            }).find((r) => r.width > 200 && r.width < 900 && r.x > 200 && r.height > 200));
            assert.ok(viewport, "Native 3D canvas not visible");
            const before = await page.screenshot({ clip: viewport });
            nonblank(before);
            if (directory) fs.writeFileSync(path.join(directory, filename + ".png"), before);
            await page.mouse.move(viewport.x + viewport.width*.5, viewport.y + viewport.height*.5);
            await page.mouse.down(); await page.mouse.move(viewport.x+viewport.width*.7, viewport.y+viewport.height*.58, { steps: 15 }); await page.mouse.up();
            await page.waitForTimeout(500);
            const after = await page.screenshot({ clip: viewport });
            assert.notEqual(crypto.createHash("sha256").update(before).digest("hex"), crypto.createHash("sha256").update(after).digest("hex"));
            if (directory) fs.writeFileSync(path.join(directory, filename + ".rotated.png"), after);
            await page.setViewportSize({ width: 390, height: 844 });
            await page.evaluate(() => {
                const app = window.__tripoApp;
                app.canvas.ds.scale = .43; app.canvas.ds.offset = [-250, 120]; app.canvas.setDirty(true, true);
            });
            await page.waitForTimeout(650);
            const mobile = await page.evaluate(() => Array.from(document.querySelectorAll("canvas")).map((canvas) => {
                const r = canvas.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height };
            }).find((r) => r.x > 50 && r.y < 500 && r.width > 150 && r.width < 330 && r.height > 150));
            assert.ok(mobile && mobile.x + mobile.width <= 390 && mobile.y + mobile.height <= 844);
            const mobileImage = await page.screenshot({ clip: mobile });
            nonblank(mobileImage);
            if (directory) fs.writeFileSync(path.join(directory, filename + ".mobile.png"), mobileImage);
            console.log(`NATIVE PASS ${filename}: local FILE_3D preview/save, orbit change, desktop/mobile framing`);
        }
        assert.deepEqual(errors, []);
        console.log("PASS zero page errors; no generation API calls made by canvas checks");
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
