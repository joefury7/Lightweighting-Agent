// Headless generator: produces the EXACT NX journal text that the app's generateNXCode() emits,
// for a JSON parameter set.  Usage: node tools/gen_journal.js '{"cellSize":64.7,...}'
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');
const captured = {};
const fakeEl = () => ({ value: '', innerText: '', textContent: '', style: {}, classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } }, addEventListener(){}, setAttribute(){}, appendChild(){}, querySelectorAll(){ return []; }, getContext(){ return null; } });
const document = {
  getElementById: (id) => {
    if (id === 'code-output') { return { set textContent(v) { captured.code = v; }, get textContent() { return captured.code; } }; }
    return null;
  },
  querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, createElement: fakeEl,
  readyState: 'loading', body: fakeEl(),
};
const ctx = { document, window: {}, console, setTimeout: () => 0, clearTimeout(){}, setInterval: () => 0, fetch: () => Promise.reject(new Error('offline')), localStorage: { getItem(){ return null; }, setItem(){} }, navigator: {}, performance: { now: () => 0 }, Math, JSON, Date };
ctx.window = ctx; ctx.globalThis = ctx; ctx.addEventListener = () => {};
vm.createContext(ctx);
vm.runInContext(src + '\n;globalThis.__state = state; globalThis.__gen = generateNXCode;', ctx);
const p = JSON.parse(process.argv[2] || '{}');
Object.assign(ctx.__state, p);
ctx.__gen(p.__pocketCount || 0, p.__finalMass || 0);
process.stdout.write(captured.code || '');
