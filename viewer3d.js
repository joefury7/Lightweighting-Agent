// 3D preview of the exact part the NX journal builds.
// Geometry comes from POST /cad/preview_geometry (journal replica: blank profile + pocket outlines
// clipped exactly as in the mass calculation); it is meshed here with three.js. Rotate: left drag,
// zoom: wheel, pan: right drag.
import * as THREE from 'three';
import { OrbitControls } from './vendor/three/OrbitControls.js';

const API = 'http://127.0.0.1:8000/cad/preview_geometry';
const state = { renderer: null, scene: null, camera: null, controls: null, part: null, edges: null,
                clip: new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0), section: false, wire: false,
                lastKey: null, busy: false, pending: false, R: 280 };

function host() { return document.getElementById('viewer3d'); }
function setStatus(txt, kind) {
  const el = document.getElementById('viewer3d-status');
  if (!el) return;
  el.textContent = txt || '';
  el.className = 'viewer-status' + (kind ? ' ' + kind : '');
}

function init() {
  if (state.renderer) return true;
  const el = host();
  if (!el) return false;
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x0f141c);
  renderer.localClippingEnabled = true;
  el.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x1a1f28, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(1, 1.6, 1.2); scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.5); fill.position.set(-1.2, -0.6, -1); scene.add(fill);
  const camera = new THREE.PerspectiveCamera(35, 1, 1, 20000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.08; controls.screenSpacePanning = true;
  Object.assign(state, { renderer, scene, camera, controls });
  new ResizeObserver(resize).observe(el);
  resize();
  (function loop() { requestAnimationFrame(loop); controls.update(); renderer.render(scene, camera); })();
  return true;
}

function resize() {
  const el = host();
  if (!el || !state.renderer) return;
  const w = el.clientWidth || 600, h = el.clientHeight || 500;
  state.renderer.setSize(w, h, false);
  state.camera.aspect = w / h;
  state.camera.updateProjectionMatrix();
}

const conicZ = (r, Rc, k) => (r * r) / (Rc * (1 + Math.sqrt(Math.max(1e-4, 1 - (1 + k) * r * r / (Rc * Rc)))));

// geometry builders (mirror coordinates: z = optical axis; converted to y-up at the end)
function pushTri(arr, a, b, c) { arr.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]); }

function addPlanarRegion(arr, ring, holes, z, up) {
  const contour = ring.map(p => new THREE.Vector2(p[0], p[1]));
  const hs = (holes || []).map(h => h.map(p => new THREE.Vector2(p[0], p[1])));
  const tris = THREE.ShapeUtils.triangulateShape(contour, hs);
  const pts = contour.concat(...hs);
  for (const t of tris) {
    const [a, b, c] = t.map(i => [pts[i].x, pts[i].y, z]);
    if (up) pushTri(arr, a, b, c); else pushTri(arr, a, c, b);
  }
}

function addWalls(arr, ring, z0, z1) {
  for (let i = 0; i < ring.length; i++) {
    const p = ring[i], q = ring[(i + 1) % ring.length];
    const a = [p[0], p[1], z0], b = [q[0], q[1], z0], c = [q[0], q[1], z1], d = [p[0], p[1], z1];
    pushTri(arr, a, b, c); pushTri(arr, a, c, d);
  }
}

function addRevolved(arr, profile, seg) {
  // profile: [[r, z], ...] revolved about z
  for (let j = 0; j < seg; j++) {
    const t0 = 2 * Math.PI * j / seg, t1 = 2 * Math.PI * (j + 1) / seg;
    const c0 = Math.cos(t0), s0 = Math.sin(t0), c1 = Math.cos(t1), s1 = Math.sin(t1);
    for (let i = 0; i < profile.length - 1; i++) {
      const [r0, z0] = profile[i], [r1, z1] = profile[i + 1];
      const a = [r0 * c0, r0 * s0, z0], b = [r0 * c1, r0 * s1, z0], c = [r1 * c1, r1 * s1, z1], d = [r1 * c0, r1 * s0, z1];
      pushTri(arr, a, b, c); pushTri(arr, a, c, d);
    }
  }
}

function buildPart(g) {
  const pos = [];
  const { R, r_hole: rh, H, R_curv: Rc, k } = g;
  const front = [];
  for (let i = 0; i <= 60; i++) { const r = rh + (R - rh) * i / 60; front.push([r, conicZ(r, Rc, k)]); }
  addRevolved(pos, front, 256);                                                  // optical surface
  addRevolved(pos, [[R, conicZ(R, Rc, k)], [R, -H]], 256);                       // outer wall
  addRevolved(pos, [[rh, -H], [rh, conicZ(rh, Rc, k)]], 256);                    // central hole wall
  for (const b of g.back_face) addPlanarRegion(pos, b.outer, b.holes, -H, false); // back face (open pockets)
  for (const p of g.pockets) {                                                   // pocket walls + ceilings
    addWalls(pos, p.outer, p.z_lo, p.z_hi);
    for (const h of p.holes || []) addWalls(pos, h, p.z_lo, p.z_hi);
    addPlanarRegion(pos, p.outer, p.holes, p.z_hi, false);
  }
  for (const u of g.unites || []) {
    addWalls(pos, u.outer, u.z_lo, u.z_hi);
    addPlanarRegion(pos, u.outer, [], u.z_hi, true);
    addPlanarRegion(pos, u.outer, [], u.z_lo, false);
  }
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geom.computeVertexNormals();
  geom.rotateX(-Math.PI / 2);   // optical axis -> screen up
  return geom;
}

function show(g) {
  const { scene } = state;
  if (state.part) { scene.remove(state.part); state.part.geometry.dispose(); }
  if (state.edges) { scene.remove(state.edges); state.edges.geometry.dispose(); }
  const geom = buildPart(g);
  const mat = new THREE.MeshStandardMaterial({ color: 0xa9b6c8, metalness: 0.15, roughness: 0.55, side: THREE.DoubleSide,
                                               flatShading: true, clippingPlanes: state.section ? [state.clip] : [],
                                               polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  state.part = new THREE.Mesh(geom, mat);
  const eg = new THREE.EdgesGeometry(geom, 25);
  state.edges = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x2b3442, clippingPlanes: state.section ? [state.clip] : [] }));
  mat.wireframe = state.wire;
  scene.add(state.part); scene.add(state.edges);
  const first = state.R !== g.R || !state.lastKey;
  state.R = g.R;
  if (first) view('iso');
}

export function view(name) {
  if (!state.camera) return;
  const d = state.R * 3.4;
  const dirs = { iso: [0.75, -0.6, 0.9], front: [0, 1, 0.0001], back: [0, -1, 0.0001], side: [1, 0.05, 0] };
  const v = new THREE.Vector3(...(dirs[name] || dirs.iso)).normalize().multiplyScalar(d);
  state.camera.position.copy(v);
  state.controls.target.set(0, -state.R * 0.05, 0);
  state.camera.near = d / 100; state.camera.far = d * 10; state.camera.updateProjectionMatrix();
  state.controls.update();
}

export function toggleSection() {
  state.section = !state.section;
  for (const o of [state.part, state.edges]) if (o) o.material.clippingPlanes = state.section ? [state.clip] : [];
  return state.section;
}

export function toggleWire() {
  state.wire = !state.wire;
  if (state.part) state.part.material.wireframe = state.wire;
  return state.wire;
}

export async function refresh(force = false) {
  if (!init()) return;
  const codeEl = document.getElementById('code-output');
  const code = codeEl ? codeEl.textContent : '';
  if (!code) { setStatus('No geometry yet'); return; }
  if (!force && code === state.lastKey) return;
  if (state.busy) { state.pending = true; return; }
  state.busy = true;
  setStatus('Building 3D geometry…', 'busy');
  try {
    const t0 = performance.now();
    const res = await fetch(API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ journal_code: code }) });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const g = await res.json();
    show(g);
    state.lastKey = code;
    setStatus(`Exact journal geometry · ${g.mass_kg.toFixed(3)} kg · built in ${Math.round(performance.now() - t0)} ms`);
  } catch (e) {
    setStatus('3D preview failed: ' + e.message, 'error');
  } finally {
    state.busy = false;
    if (state.pending) { state.pending = false; refresh(); }
  }
}

window.Viewer3D = { refresh, view, toggleSection, toggleWire };
