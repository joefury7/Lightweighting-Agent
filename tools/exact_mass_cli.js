// node tools/exact_mass_cli.js '{"diameter":560,...}'  -> prints exact isogrid mass (kg) using app.js code
const fs = require('fs'), vm = require('vm'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8');
const ctx = { document: { readyState: 'loading', getElementById: () => null, addEventListener() {}, querySelectorAll: () => [], querySelector: () => null }, console, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {}, addEventListener() {}, Math, JSON, Number, fetch: () => Promise.reject(new Error('offline')) };
ctx.window = ctx; vm.createContext(ctx);
vm.runInContext(src + '\n;globalThis.__m = calculateExactIsogridMass;', ctx);
const p = JSON.parse(process.argv[2]);
const r = ctx.__m(p.diameter, p.centralHoleDia, p.depth, p.faceplate, p.ribThick, p.cellSize, p.filletRadius, p.radiusCurv || 1085, p.conicConstant ?? -1.22, p.density || 2530);
process.stdout.write(String(r.mass));
