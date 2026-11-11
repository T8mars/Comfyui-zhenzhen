// Isolated acceptance reuses completed task responses; no generation POSTs escape the fixture.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
    const browser = await chromium.launch({ headless: true, executablePath: process.env.ZHENZHEN_BROWSER_EXECUTABLE });
    try {
        const page = await browser.newPage({ viewport: { width: 1700, height: 1100 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.goto(process.env.SEEDANCE55_UI_URL ?? "http://127.0.0.1:8298", { waitUntil: "networkidle", timeout: 90000 });
        await page.evaluate(async () => { window.__s55 = (await import("/scripts/app.js")).app; });
        await page.waitForFunction(() => window.__s55?.graph);
        await page.keyboard.press("Escape");
        const folder = path.join(__dirname, "..", "workflow");
        const files = fs.readdirSync(folder).filter((name) => /^(?:zhenzhen-(?:dola-)?seedream-(?:v)?5\.5-|zhenzhen-seedream55-transparent-|zhenzhen-seedance-2\.5-.*draft-to-video)/.test(name));
        assert.equal(files.length, 11);
        const legacy = fs.readdirSync(folder).filter((name) => name.startsWith("zhenzhen-seedance-2.5-") && !name.includes("draft-to-video"));
        for (const filename of [...files, ...legacy]) {
            const workflow = JSON.parse(fs.readFileSync(path.join(folder, filename), "utf8"));
            const report = await page.evaluate(async (workflow) => {
                const app = window.__s55;
                const settle = () => new Promise((resolve) => setTimeout(resolve, 75));
                await app.loadGraphData(workflow); await settle();
                const sources = app.graph._nodes.filter((node) => ["Comfly_seedance25_standard_low_price", "T8Zhenzhen_Seedance_25_Draft_To_Video_LowPrice", "T8Zhenzhen_Seedream_55_Image_LowPrice", "T8Zhenzhen_Seedream_55_Layers_LowPrice"].includes(node.comfyClass));
                const before = sources.map((node) => ({ id: node.id, inputs: node.inputs.map((input) => input.name), links:node.inputs.map((input)=>input.link), widgets:node.serialize().widgets_values, model: node.widgets.find((widget) => widget.name === "model").value }));
                for (const node of sources) {
                    const model = node.widgets.find((widget) => widget.name === "model");
                    const original = model.value;
                    for (const value of [...model.options.values, original]) { model.value = value; model.callback?.(value); await settle(); }
                    const draft = node.widgets.find((widget) => widget.name === "draft");
                    if (draft) { const value = draft.value; for (const next of [true, false, value]) { draft.value = next; draft.callback?.(next); await settle(); } }
                    node.setSize([900, node.size[1]]); node.setSize([510, node.size[1]]);
                }
                await app.loadGraphData(app.graph.serialize()); await settle();
                const prompt = await app.graphToPrompt();
                const validation = await (await fetch("/seedance55_fixture/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: prompt.output }) })).json();
                return { validation, nodes: before.map((previous) => {
                    const node = app.graph.getNodeById(previous.id);
                    return { previous, inputs: node.inputs.map((input) => input.name), links:node.inputs.map((input)=>input.link), widgets:node.serialize().widgets_values, footer:node.widgets.filter((widget)=>widget.name==="贞贞的平价小屋APIKEY获取").length, values: prompt.output[String(node.id)].inputs,
                        control: node.widgets.find((widget) => widget.name === "control_after_generate")?.value };
                }) };
            }, workflow);
            assert.equal(report.validation.valid, true, `${filename}: ${JSON.stringify(report.validation)}`);
            for (const node of report.nodes) {
                assert.deepEqual(node.previous.inputs, node.inputs);
                assert.deepEqual(node.previous.links,node.links);
                assert.deepEqual(node.previous.widgets,node.widgets);
                assert.equal(node.footer,1);
                assert.equal(node.previous.model, node.values.model);
                if (node.control !== undefined) assert.equal(node.control, "fixed");
                assert.ok(Array.isArray(node.values.api_config));
                if (legacy.includes(filename)) {
                    assert.equal(node.values.draft, false);
                    assert.equal(node.values.skip_error, false);
                }
                if (filename.includes("-chain-") && node.values.draft !== undefined) {
                    assert.equal(node.values.draft, true);
                    assert.equal(node.values.skip_error, false);
                }
            }
            console.log(`CANVAS PASS ${filename}: switch, resize, reload, stable links and backend queue validation`);
        }
        const legacyValues = JSON.parse(fs.readFileSync(path.join(folder, legacy[0]), "utf8")).nodes.find((node) => node.type === "Comfly_seedance25_standard_low_price").widgets_values;
        const migrated = await page.evaluate(async (prefix) => {
            const app = window.__s55;
            const reports = [];
            for (const key of ["Comfly_seedance25_standard_low_price", "ComflyConcurrent_Comfly_seedance25_standard_low_price_Submit"]) {
                for (const skip of [false, true]) for (const draft of [undefined, false, true]) {
                    app.graph.clear();
                    const node = window.LiteGraph.createNode(key);
                    app.graph.add(node);
                    const values = [...prefix.slice(0, 8), skip];
                    if (draft !== undefined) values.push(draft);
                    node.configure({ widgets_values: values });
                    const id = node.id;
                    await app.loadGraphData(app.graph.serialize());
                    const restored = app.graph.getNodeById(id);
                    const value = (name) => restored.widgets.find((widget) => widget.name === name).value;
                    reports.push({ skip, draft: draft ?? false, actualSkip: value("skip_error"), actualDraft: value("draft"), control: value("control_after_generate") });
                }
            }
            return reports;
        }, legacyValues);
        for (const report of migrated) {
            assert.equal(report.actualSkip, report.skip);
            assert.equal(report.actualDraft, report.draft);
            assert.equal(report.control, "fixed");
        }
        console.log("CANVAS PASS 12 serial/concurrent legacy boolean migration and reload cases");
        const reuse = await (await page.request.post(new URL("/seedance55_fixture/reuse", page.url()).href, { data: {} })).json();
        assert.equal(reuse.ready, true);
        const output = process.env.SEEDANCE_UI_SCREENSHOT_DIR;
        if (output) fs.mkdirSync(output, { recursive: true });
        async function frameLayerNode() {
            await page.evaluate(() => {
                const app = window.__s55;
                const node = app.graph._nodes.find((item) => item.comfyClass === "T8Zhenzhen_Seedream_55_Layers_LowPrice");
                const scale = Math.min(.9, (innerWidth - 110) / node.size[0], (innerHeight - 180) / (node.size[1] + 30));
                app.canvas.ds.scale = scale;
                app.canvas.ds.offset = [75 / scale - node.pos[0], 125 / scale - node.pos[1]];
                app.canvas.setDirty(true, true);
            });
            await page.waitForTimeout(500);
        }
        async function execute() {
            return page.evaluate(async () => {
                const app = window.__s55;
                const prompt = await app.graphToPrompt();
                const { api } = await import("/scripts/api.js");
                const response = await fetch("/prompt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: prompt.output, client_id: api.clientId }) });
                const submitted = await response.json();
                if (!response.ok) throw new Error(JSON.stringify(submitted));
                let record;
                for (let i = 0; i < 180; i++) {
                    record = (await (await fetch(`/history/${submitted.prompt_id}`)).json())[submitted.prompt_id];
                    if (record?.status?.completed) break;
                    await new Promise((resolve) => setTimeout(resolve, 500));
                }
                if (record?.status?.status_str !== "success") throw new Error("Local reuse execution failed: " + JSON.stringify(record?.status?.messages?.map((item) => item[0])));
                return record.outputs;
            });
        }
        const videos = process.env.SEEDANCE55_TEST_STAGE === "videos";
        const executions = files.filter((filename) => videos
            ? filename.includes("-chain-") && (!process.env.SEEDANCE55_VIDEO_REGION || filename.includes("global") === (process.env.SEEDANCE55_VIDEO_REGION === "global"))
            : filename.includes("5.5") || filename.includes("seedream55"));
        for (const filename of executions) {
            const workflow = JSON.parse(fs.readFileSync(path.join(folder, filename), "utf8"));
            await page.evaluate(async (workflow) => {
                const app = window.__s55;
                await app.loadGraphData(workflow);
                for (const node of app.graph._nodes) {
                    if (node.comfyClass === "T8Zhenzhen_API_Settings") node.widgets.find((widget) => widget.name === "apikey").value = "sk-test";
                    const control = node.widgets?.find((widget) => widget.name === "control_after_generate");
                    if (control) control.value = "fixed";
                }
                app.canvas.ds.scale = .65; app.canvas.ds.offset = [10, 20]; app.canvas.setDirty(true, true);
            }, workflow);
            const result = await execute();
            const saves = workflow.nodes.filter((node) => node.type === (videos ? "SaveVideo" : "SaveImage"));
            const entries = saves.flatMap((node) => result[String(node.id)]?.images ?? []);
            if (videos) {
                assert.equal(entries.length, 2, "Both draft and enhanced video must be saved");
                if (output) for (let index = 0; index < entries.length; index++) {
                    const bytes = await (await page.request.get(new URL("/view?"+new URLSearchParams(entries[index]), page.url()).href)).body();
                    assert.ok(bytes.length > 1000);
                    fs.writeFileSync(path.join(output, filename+`-${index}.saved`+path.extname(entries[index].filename)), bytes);
                }
            }
            if (!videos) {
                assert.equal(entries.length, filename.includes("layer-decomposition") ? 2 : 1);
                for (let index = 0; index < entries.length; index++) {
                    const bytes = await (await page.request.get(new URL("/view?"+new URLSearchParams(entries[index]), page.url()).href)).body();
                    assert.ok(bytes.length > 1000);
                    if (output) fs.writeFileSync(path.join(output, filename+`-${index}.saved.png`), bytes);
                }
                const countUrl = new URL("/seedance55_fixture/counts", page.url()).href;
                const before = await (await page.request.get(countUrl)).json();
                await execute();
                const after = await (await page.request.get(countUrl)).json();
                assert.deepEqual(after, before, "Fixed rerun must not resubmit completed inputs");
                if (output && filename.includes("layer-decomposition")) {
                    await frameLayerNode();
                    await page.screenshot({ path: path.join(output, filename+".desktop.png") });
                    await page.setViewportSize({ width: 390, height: 844 });
                    await frameLayerNode();
                    await page.screenshot({ path: path.join(output, filename+".mobile.png") });
                    await page.setViewportSize({ width: 1700, height: 1100 });
                }
            }
            console.log(`NATIVE REUSE PASS ${filename}: actual node download/decode and native saving${videos ? "" : ", original alpha/list outputs and Fixed caching"}`);
        }
        if (!videos) {
            const built = await page.evaluate(async () => {
                const app=window.__s55; app.graph.clear();
                const create=(type)=>{const node=window.LiteGraph.createNode(type);app.graph.add(node);return node;};
                const config=create("T8Zhenzhen_API_Settings");config.widgets.find((w)=>w.name==="apikey").value="sk-test";
                const a=create("ComflyConcurrent_T8Zhenzhen_Seedream_55_Image_LowPrice_Submit"),b=create("ComflyConcurrent_T8Zhenzhen_Seedream_55_Image_LowPrice_Submit"),collector=create("ComflyConcurrent_Image_Await");
                for(const [node,model] of [[a,"seedream-v5.5-t2i"],[b,"dola-seedream-5.5-t2i"]]){
                    node.widgets.find((w)=>w.name==="model").value=model;
                    node.widgets.find((w)=>w.name==="prompt").value="An isolated green leaf on transparent background";
                    node.widgets.find((w)=>w.name==="skip_error").value=true;
                    node.widgets.find((w)=>w.name==="control_after_generate").value="fixed";
                    config.connect(1,node,node.inputs.findIndex((i)=>i.name==="api_config"));
                }
                a.connect(0,collector,collector.inputs.findIndex((i)=>i.name==="task_1"));
                b.connect(0,collector,collector.inputs.findIndex((i)=>i.name==="task_2"));
                const saveIds=[];
                for(const slot of [0,1]){const save=create("SaveImage");save.widgets[0].value="seedance55_concurrent_"+slot;collector.connect(slot,save,0);saveIds.push(save.id);}
                return saveIds;
            });
            await page.request.post(new URL("/seedance55_fixture/fail-once",page.url()).href,{data:{case:"domestic_t2i"}});
            const result=await execute();
            assert.ok(built.every((id)=>result[String(id)]?.images?.length===1));
            console.log("NATIVE REUSE PASS concurrent RGBA save with one skipped sibling failure");
        }
        assert.deepEqual(errors, []);
        console.log("PASS zero page errors; task creation blocked by isolated fixture");
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
