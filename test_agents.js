const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("agents.js", "utf8");
const context = { window: {} };

vm.runInNewContext(source, context);

const LEAF_OS = context.window.LEAF_OS;

assert.equal(LEAF_OS.name, "LEAF");
assert.equal(LEAF_OS.getAgents().length, 4);
assert.equal(LEAF_OS.getAgent("clip-agent").name, "Clip Agent");
assert.equal(LEAF_OS.getAgent("unknown"), null);

const result = LEAF_OS.setAgentStatus("clip-agent", "working");
assert.equal(result.success, true);
assert.equal(LEAF_OS.getStatus().activeAgents, 1);

const invalid = LEAF_OS.setAgentStatus("clip-agent", "invalid");
assert.equal(invalid.success, false);

console.log("LEAF OS: todas las pruebas pasaron.");
