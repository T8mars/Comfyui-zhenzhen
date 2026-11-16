import assert from "node:assert/strict";
import fs from "node:fs";
import { enableZhenzhenConcreteInputVisibility, setZhenzhenInputVisible } from "../web/js/dynamic_widget_ui.js";

let profiles = 0;
for (const shared of [false, true]) for (const marker of [null, "__zhenzhen_hidden_input__", "__seedance_hidden_input__"]) {
    const media = { name: "image2", type: "IMAGE", link: null, hidden: true };
    if (marker) Object.assign(media, { pos: new Float32Array([-100000, -100000]), widget: { name: marker } });
    const prompt = { name: "prompt", type: "STRING", link: 7, widget: { name: "prompt" }, pos: [12, 34] };
    const inputs = [media, prompt];
    const node = { inputs, pos: [400, 100], size: [500, 500],
        getConnectionPos(isInput, index) { return this.inputs[index].pos ?? [10, index * 20 + 14]; },
        drawSlots() {}, _setConcreteSlots() {}, };
    node._concreteInputs = shared ? inputs : inputs.map((input) => ({ ...input }));
    enableZhenzhenConcreteInputVisibility(node);
    node.drawSlots();
    setZhenzhenInputVisible(node, media, true);
    node.drawSlots();
    assert.notEqual(media.pos?.[0], -100000, `raw position shared=${shared}, legacy=${marker}`);
    assert.notEqual(media.widget?.name, "__zhenzhen_hidden_input__");
    assert.notEqual(node._concreteInputs[0].pos?.[0], -100000);
    assert.notEqual(node._concreteInputs[0].widget?.name, "__zhenzhen_hidden_input__");
    assert.equal(node.getConnectionPos(true, 0)[0] > -50000, true);
    assert.equal(node.inputs, inputs);
    assert.deepEqual(prompt.widget, { name: "prompt" });
    assert.deepEqual(prompt.pos, [12, 34]);
    for (let i = 0; i < 5; i++) {
        setZhenzhenInputVisible(node, media, false); node.drawSlots();
        setZhenzhenInputVisible(node, media, true); node.drawSlots();
        assert.notEqual(media.pos?.[0], -100000);
    }
    setZhenzhenInputVisible(node, media, false); node.drawSlots();
    const data = { inputs: node.inputs.map((input) => ({ ...input })) };
    node.onSerialize(data);
    assert.ok(data.inputs.every((input) => input.widget?.name !== "__zhenzhen_hidden_input__" && input.pos?.[0] !== -100000));
    assert.deepEqual(data.inputs[1].widget, { name: "prompt" });
    assert.deepEqual(data.inputs[1].pos, [12, 34]);
    assert.equal(prompt.link, 7);
    setZhenzhenInputVisible(node, prompt, false);
    assert.equal(prompt.hidden, false, "Connected converted input stays visible");
    prompt.link = null;
    setZhenzhenInputVisible(node, prompt, false); node.drawSlots();
    setZhenzhenInputVisible(node, prompt, true); node.drawSlots();
    assert.deepEqual(prompt.widget, { name: "prompt" });
    assert.deepEqual(prompt.pos, [12, 34]);
    const aliased = { inputs: node.inputs };
    node.onSerialize(aliased);
    assert.notEqual(aliased.inputs, node.inputs, "Serialization does not mutate live slot objects");
    assert.deepEqual(aliased.inputs[1].widget, { name: "prompt" });
    assert.equal(node.inputs, inputs);
    node._concreteInputs = node.inputs.map((input) => ({ ...input }));
    node._setConcreteSlots();
    setZhenzhenInputVisible(node, media, true); node.drawSlots();
    assert.notEqual(node._concreteInputs[0].pos?.[0], -100000);
    profiles++;
}
for (const file of fs.readdirSync(new URL("../web/js/", import.meta.url))) {
    if (!file.endsWith(".js")) continue;
    const source = fs.readFileSync(new URL(`../web/js/${file}`, import.meta.url), "utf8");
    assert.ok(!/this\.inputs\s*=/.test(source), `${file}: never replace live input arrays for layout`);
    if (file !== "dynamic_widget_ui.js") assert.ok(!/input\.hidden\s*=/.test(source), `${file}: route visibility through the shared restorer`);
}
console.log(`PASS ${profiles} shared/copied/legacy profiles, repeated restore, clean save, rebuilt slots and converted inputs`);
