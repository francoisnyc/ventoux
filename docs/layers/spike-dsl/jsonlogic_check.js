// The JsonLogic reference implementation on jsonlogic_cases.json. Run from this folder:
// npm install --prefix /tmp/jl json-logic-js@2.0.5 && NODE_PATH=/tmp/jl/node_modules node jsonlogic_check.js
const jsonLogic = require("json-logic-js");
const cases = require("./jsonlogic_cases.json");
console.log(`json-logic-js ${require("json-logic-js/package.json").version}`);
for (const c of cases) {
  let result;
  try {
    result = JSON.stringify(jsonLogic.apply(c.rule, c.data));
  } catch (e) {
    result = `ERROR ${e.message.slice(0, 60)}`;
  }
  console.log(`  ${c.name.padEnd(32)} -> ${result}`);
}
