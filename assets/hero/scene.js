// williamckim.com · Home hero and scroll story: one particle system, many shapes.
// ES module on three.js 0.186.1, through the page's import map. Loaded by hero3d.js.
//
// Every particle has a target position in each "stage": the ledger grid (the hero and
// chapter 1), a lifted system graph (chapter 2), each number in the story (chapter 3,
// sampled from text drawn on an offscreen canvas), 16 Grover bars (chapter 4) and the
// WK monogram (chapter 5). The page tells the scene which stage it is at through
// window.__story.stage, a float the scroll scrubs. The scene only reads it.
//
// The numbers are read from the chapter captions in the HTML ([data-glyph]), so the
// particles always draw what the page says. tests/check_motion.py compares the shapes
// the particles form against the proof strip's own text, drawn independently.
//
// Colours follow the site theme, and change live on the themechange event. Bloom
// (UnrealBloomPass) lights the lifted nodes in the dark theme. Rendering pauses when
// the tab is hidden or the stage is off screen. Reduced motion draws one still frame.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

// Theme palettes. Background stops match --grad-hero in style.css, so the canvas
// fades in over the CSS gradient without a visible change.
const PALETTES = {
  light: {
    bg: ["#f2f3f0", "#e2efe8", "#dbe3ef"], glow: "#fbeed0", base: "#8d948c",
    ledger: "#1e6b47", blueprint: "#2a4a78", violet: "#5b4b8a", amber: "#b27405",
    additive: false, bloom: 0, halo: 0.55
  },
  dark: {
    bg: ["#121416", "#13201a", "#141b27"], glow: "#2d2311", base: "#59626b",
    ledger: "#5cc28c", blueprint: "#8fb2ee", violet: "#b7a8f2", amber: "#e3a83d",
    additive: true, bloom: 0.85, halo: 0.4
  }
};
const FOV = 32, TILT = 38 * Math.PI / 180, GAP = 0.78, CELL = 0.62, LIFT = 1.6;

// ---- text to points -------------------------------------------------------------
// Draws text on an offscreen canvas and returns n points on its inked pixels, as
// [u, v] in 0..1 of the ink's bounding box (v down), plus the box's aspect ratio.
// Deterministic: the same text and n always give the same points.
export function sampleText(text, font, n, outline) {
  const px = 220, pad = 40;
  const c = document.createElement("canvas");
  const g = c.getContext("2d", { willReadFrequently: true });
  g.font = font.replace("{px}", px);
  const w = Math.ceil(g.measureText(text).width) + pad * 2 + (outline ? px * 0.5 : 0);
  const h = Math.ceil(px * 1.35) + pad * 2 + (outline ? px * 0.3 : 0);
  c.width = w; c.height = h;
  g.font = font.replace("{px}", px);
  g.fillStyle = "#000"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, w / 2, h / 2 + px * 0.04);
  if (outline) {
    g.lineWidth = px * 0.075;
    const bw = w - pad * 2, bh = h - pad * 2, r = px * 0.12;
    g.beginPath(); g.roundRect(pad, pad, bw, bh, r); g.stroke();
  }
  const data = g.getImageData(0, 0, w, h).data;
  const ink = [];
  let x0 = w, y0 = h, x1 = 0, y1 = 0;
  for (let y = 0; y < h; y += 2) {
    for (let x = 0; x < w; x += 2) {
      if (data[(y * w + x) * 4 + 3] > 140) {
        ink.push(x, y);
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
  }
  const count = ink.length / 2, out = new Float32Array(n * 2);
  const bw = Math.max(1, x1 - x0), bh = Math.max(1, y1 - y0);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < n; i++) {
    // Even coverage: walk the ink in a strided order, jitter within a pixel pair.
    const k = count ? Math.floor((i * count) / n + rnd() * (count / n)) % count : 0;
    out[i * 2] = (ink[k * 2] - x0 + rnd() * 2) / bw;
    out[i * 2 + 1] = (ink[k * 2 + 1] - y0 + rnd() * 2) / bh;
  }
  return { points: out, aspect: bw / bh, inked: count };
}

// Grover's algorithm on 16 states, marked state 7 as in the Lab's source repo:
// amplitudes after k iterations (oracle flips the sign, diffusion reflects about the mean).
function grover(k) {
  const a = new Array(16).fill(0.25);
  for (let it = 0; it < k; it++) {
    a[7] = -a[7];
    const mean = a.reduce((s, x) => s + x, 0) / 16;
    for (let i = 0; i < 16; i++) a[i] = 2 * mean - a[i];
  }
  return a;
}

export function init(stage) {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const small = matchMedia("(max-width: 720px), (pointer: coarse)").matches;
  // Particle budget: a ledger of COLS x ROWS cells, K x K points in each.
  const COLS = small ? 16 : 26, ROWS = 14, K = small ? 3 : 4;
  const CELLS = COLS * ROWS, N = CELLS * K * K;

  let W = stage.clientWidth, H = stage.clientHeight;
  const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false, powerPreference: "high-performance" });
  const DPR = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(DPR);
  renderer.setSize(W, H);
  stage.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, W / H, 0.1, 500);
  const group = new THREE.Group();
  scene.add(group);

  // ---- background: the hero gradient, drawn in the scene so bloom and fog sit on it
  const bgMat = new THREE.ShaderMaterial({
    depthWrite: false, depthTest: false,
    uniforms: { c0: { value: new THREE.Color() }, c1: { value: new THREE.Color() },
                c2: { value: new THREE.Color() }, cg: { value: new THREE.Color() }, uAspect: { value: W / H } },
    vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
    fragmentShader: `varying vec2 vUv; uniform vec3 c0, c1, c2, cg; uniform float uAspect;
      void main(){
        float t = clamp((vUv.x * uAspect + (1.0 - vUv.y)) / (uAspect + 1.0), 0.0, 1.0);
        vec3 c = t < 0.45 ? mix(c0, c1, t / 0.45) : mix(c1, c2, (t - 0.45) / 0.55);
        vec2 d = (vUv - vec2(0.86, 0.94)) / vec2(0.58, 0.46);
        c = mix(c, cg, 0.4 * (1.0 - smoothstep(0.0, 0.72, length(d))));
        gl_FragColor = vec4(c, 1.0);
      }`
  });
  const bg = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), bgMat);
  bg.frustumCulled = false;
  bg.renderOrder = -1;
  scene.add(bg);

  // ---- particles
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(N * 3), aAlpha = new Float32Array(N), aMix = new Float32Array(N),
        aGlow = new Float32Array(N), aSize = new Float32Array(N), seed = new Float32Array(N);
  for (let i = 0; i < N; i++) seed[i] = ((i * 2654435761) % 1000) / 1000;
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute("aAlpha", new THREE.BufferAttribute(aAlpha, 1).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute("aMix", new THREE.BufferAttribute(aMix, 1).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute("aGlow", new THREE.BufferAttribute(aGlow, 1).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute("aSize", new THREE.BufferAttribute(aSize, 1).setUsage(THREE.DynamicDrawUsage));
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: {
      uBase: { value: new THREE.Color() }, uAccent: { value: new THREE.Color() },
      uPx: { value: 1 }, uFogNear: { value: 10 }, uFogFar: { value: 20 }, uHalo: { value: 0.5 },
      uGlowBoost: { value: 1.6 }, uScrim: { value: 0 }, uDim: { value: 0 }
    },
    vertexShader: `attribute float aAlpha; attribute float aMix; attribute float aGlow; attribute float aSize;
      uniform float uPx, uFogNear, uFogFar, uScrim, uDim;
      varying float vAlpha; varying float vMix; varying float vGlow;
      void main(){
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * mv;
        float depth = -mv.z;
        gl_PointSize = aSize * (1.0 + aGlow * 1.2) * uPx / depth;
        vAlpha = aAlpha * (1.0 - smoothstep(uFogNear, uFogFar, depth));
        // Keep the words readable: in the hero, points thin out under the copy column
        // (left side on wide screens, everywhere on narrow ones).
        float sx = gl_Position.x / gl_Position.w;
        vAlpha *= 1.0 - uScrim * (1.0 - smoothstep(-0.25, 0.3, sx)) * 0.8;
        vAlpha *= 1.0 - uDim;
        vMix = aMix; vGlow = aGlow;
      }`,
    fragmentShader: `uniform vec3 uBase, uAccent; uniform float uHalo, uGlowBoost;
      varying float vAlpha; varying float vMix; varying float vGlow;
      void main(){
        float d = length(gl_PointCoord - 0.5);
        float core = 1.0 - smoothstep(0.16, 0.3, d);
        float halo = (1.0 - smoothstep(0.1, 0.5, d)) * uHalo * vGlow;
        float a = max(core, halo) * vAlpha;
        if (a < 0.01) discard;
        vec3 c = mix(uBase, uAccent, vMix) * (1.0 + vGlow * uGlowBoost * core);
        gl_FragColor = vec4(c, a);
      }`
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  group.add(points);

  // ---- post: render, bloom, output (tone and colour space)
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(W / 2, H / 2), 0.85, 0.55, 0.42);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  // ---- theme
  let P, accentOf = {};
  function applyTheme() {
    const dark = document.documentElement.getAttribute("data-theme-resolved") === "dark";
    P = PALETTES[dark ? "dark" : "light"];
    bgMat.uniforms.c0.value.set(P.bg[0]); bgMat.uniforms.c1.value.set(P.bg[1]);
    bgMat.uniforms.c2.value.set(P.bg[2]); bgMat.uniforms.cg.value.set(P.glow);
    mat.uniforms.uBase.value.set(P.base);
    mat.uniforms.uHalo.value = P.halo;
    mat.uniforms.uGlowBoost.value = P.additive ? 1.6 : 0.15;
    mat.blending = P.additive ? THREE.AdditiveBlending : THREE.NormalBlending;
    mat.needsUpdate = true;
    bloom.enabled = P.bloom > 0;
    bloom.strength = P.bloom;
    for (const k of ["ledger", "blueprint", "violet", "amber"]) accentOf[k] = new THREE.Color(P[k]);
  }
  applyTheme();

  // ---- the ledger: base positions, cell of each particle
  const cellOf = new Uint16Array(N), grid = new Float32Array(N * 3);
  const halfW = ((COLS - 1) / 2) * GAP + CELL / 2, halfD = ((ROWS - 1) / 2) * GAP + CELL / 2;
  const cellX = (c) => (c % COLS - (COLS - 1) / 2) * GAP, cellZ = (c) => (Math.floor(c / COLS) - (ROWS - 1) / 2) * GAP;
  for (let c = 0, i = 0; c < CELLS; c++) {
    for (let a = 0; a < K; a++) {
      for (let b = 0; b < K; b++, i++) {
        cellOf[i] = c;
        grid[i * 3] = cellX(c) + (a / (K - 1) - 0.5) * CELL * 0.8;
        grid[i * 3 + 1] = 0;
        grid[i * 3 + 2] = cellZ(c) + (b / (K - 1) - 0.5) * CELL * 0.8;
      }
    }
  }

  // ---- stages. Each: positions (N*3), alpha, mix, glow, size (N), and an accent.
  function stageOf(accent) {
    return { pos: new Float32Array(N * 3), alpha: new Float32Array(N).fill(1), mix: new Float32Array(N),
             glow: new Float32Array(N), size: new Float32Array(N).fill(1), accent: accent };
  }
  const DOT = 0.075;   // world size of a ledger point

  function gridStage() {
    const s = stageOf("ledger");
    s.pos.set(grid);
    s.size.fill(DOT);
    return s;
  }

  // Nodes: cells spread across the ledger, lifted and lit. Edges: each node to its two
  // nearest, drawn by particles borrowed from other cells. The rest stay, dimmed.
  let rngState = 11;
  const rnd = () => ((rngState = (rngState * 16807) % 2147483647) / 2147483647);
  function pickNodes(count, minDist) {
    const out = [];
    for (let tries = 0; out.length < count && tries < 2000; tries++) {
      const c = Math.floor(rnd() * CELLS);
      if (out.every((o) => Math.hypot(cellX(o) - cellX(c), cellZ(o) - cellZ(c)) > minDist)) out.push(c);
    }
    return out;
  }
  function graphStage() {
    const s = stageOf("ledger");
    s.pos.set(grid);
    s.size.fill(DOT);
    rngState = 11;
    const nodes = pickNodes(small ? 10 : 14, small ? 2.2 : 2.6);
    const isNode = new Map(nodes.map((c, k) => [c, k]));
    const edges = [];
    nodes.forEach((a) => {
      nodes.filter((b) => b !== a)
        .sort((p, q) => Math.hypot(cellX(p) - cellX(a), cellZ(p) - cellZ(a)) - Math.hypot(cellX(q) - cellX(a), cellZ(q) - cellZ(a)))
        .slice(0, 2).forEach((b) => {
          if (!edges.some((e) => (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a))) edges.push([a, b]);
        });
    });
    let e = 0;
    for (let i = 0; i < N; i++) {
      const c = cellOf[i];
      if (isNode.has(c)) {
        s.pos[i * 3 + 1] = LIFT + (seed[i] - 0.5) * 0.18;
        s.mix[i] = 1; s.glow[i] = 1; s.size[i] = DOT * 1.1;
      } else if (seed[i] < 0.36 && edges.length) {
        const [a, b] = edges[e++ % edges.length], t = (i % 97) / 97;
        s.pos[i * 3] = cellX(a) + (cellX(b) - cellX(a)) * t;
        s.pos[i * 3 + 1] = LIFT;
        s.pos[i * 3 + 2] = cellZ(a) + (cellZ(b) - cellZ(a)) * t;
        s.mix[i] = 0.85; s.glow[i] = 0.35; s.size[i] = DOT * 0.7;
      } else {
        s.alpha[i] = 0.32;
      }
    }
    return s;
  }

  // Shapes that face the camera: in the plane through the origin, perpendicular to the
  // view, measured in fractions of the visible half-height (hh) and half-width (hw).
  const view = { hw: 1, hh: 1, right: new THREE.Vector3(1, 0, 0), up: new THREE.Vector3(0, Math.cos(TILT), -Math.sin(TILT)) };
  function place(s, i, x, y) {   // x, y in world units on the view plane
    s.pos[i * 3] = view.right.x * x + view.up.x * y;
    s.pos[i * 3 + 1] = view.right.y * x + view.up.y * y;
    s.pos[i * 3 + 2] = view.right.z * x + view.up.z * y;
  }
  function planeBox(aspect, maxW, maxH, cy) {   // fit a box of this aspect, centred at cy (fraction of hh)
    let w = view.hw * 2 * maxW, h = w / aspect;
    if (h > view.hh * 2 * maxH) { h = view.hh * 2 * maxH; w = h * aspect; }
    return { w, h, cy: cy * view.hh };
  }
  const glyphCache = new Map();
  function glyphStage(g) {
    const s = stageOf(g.accent);
    const key = g.text + "|" + g.font;
    if (!glyphCache.has(key)) glyphCache.set(key, sampleText(g.text, g.font, N, g.outline));
    const smp = glyphCache.get(key);
    const box = planeBox(smp.aspect, small ? 0.86 : 0.62, g.maxH, small ? 0.34 : 0.2);
    const pointSize = Math.max(0.035, Math.min(0.07, box.h / 38));
    for (let i = 0; i < N; i++) {
      const u = smp.points[i * 2], v = smp.points[i * 2 + 1];
      place(s, i, (u - 0.5) * box.w, box.cy - (v - 0.5) * box.h);
      s.mix[i] = 1; s.glow[i] = 0.3; s.size[i] = pointSize;
    }
    s.sample = smp;
    s.text = g.text;
    return s;
  }
  function barsStage(iterations) {
    const s = stageOf("amber");
    const amps = grover(iterations);
    const box = planeBox(1.6, small ? 0.86 : 0.56, 0.42, small ? 0.34 : 0.2);
    const per = Math.floor(N / 16), bw = box.w / 16;
    const base = box.cy - box.h / 2;
    for (let i = 0; i < N; i++) {
      const b = Math.min(15, Math.floor(i / per)), k = i - b * per;
      const hgt = Math.max(0.02, Math.abs(amps[b])) * box.h;
      const cols = 4, rows = Math.ceil(per / cols);
      const x = -box.w / 2 + (b + 0.5) * bw + ((k % cols) / (cols - 1) - 0.5) * bw * 0.55;
      const y = base + (Math.floor(k / cols) / rows) * hgt;
      place(s, i, x, y);
      const marked = b === 7;
      s.mix[i] = marked ? 1 : 0.25; s.glow[i] = marked ? 0.9 : 0.1;
      s.size[i] = Math.max(0.03, Math.min(0.06, box.h / 50));
    }
    return s;
  }

  // Story stages come from the page: the chapter captions carry the numbers as text.
  function storyGlyphs() {
    const els = Array.prototype.slice.call(document.querySelectorAll("[data-glyph]"));
    return els.map((el) => ({ text: el.textContent.trim(), accent: el.getAttribute("data-glyph") || "ledger",
                              font: '500 {px}px "IBM Plex Mono", ui-monospace, monospace', maxH: 0.3 }));
  }
  const hasStory = !!document.getElementById("story");
  let stages = [];
  function build() {
    const list = [gridStage(), graphStage()];
    if (hasStory) {
      storyGlyphs().forEach((g) => list.push(glyphStage(g)));
      list.push(barsStage(0), barsStage(3));
      list.push(glyphStage({ text: "WK", accent: "ledger", font: '700 {px}px "IBM Plex Sans", system-ui, sans-serif',
                             maxH: 0.34, outline: true }));
    }
    stages = list;
  }

  // ---- camera: fit the ledger to the viewport (with the parallax envelope)
  let dist = 20;
  function layout() {
    const aspect = W / H;
    camera.aspect = aspect;
    camera.updateProjectionMatrix();
    const tanH = Math.tan((FOV / 2) * Math.PI / 180);
    // The ledger's projected footprint: width is what binds, except on short, wide screens.
    const needW = (halfW * 1.1) / (tanH * aspect * (aspect < 0.8 ? 1.45 : 1));
    const needH = (halfD * Math.sin(TILT) + LIFT * Math.cos(TILT) + 0.6) / tanH;
    dist = Math.max(needW, needH) * 1.08 + halfD * Math.cos(TILT) * 0.6;
    view.hh = dist * tanH;
    view.hw = view.hh * aspect;
    mat.uniforms.uPx.value = (H * DPR) / (2 * tanH);
    mat.uniforms.uFogNear.value = dist * 0.92;
    mat.uniforms.uFogFar.value = dist * 1.75;
    bgMat.uniforms.uAspect.value = aspect;
    build();
  }
  layout();
  // The numbers are drawn in IBM Plex Mono and the monogram in Plex Sans: sample again
  // once those faces have loaded, so the shapes are never a fallback font's.
  let fontsReady = false;
  if (document.fonts && document.fonts.load) {
    Promise.all([document.fonts.load('500 100px "IBM Plex Mono"', "0123456789%"),
                 document.fonts.load('700 100px "IBM Plex Sans"', "WK")])
      .then(() => { fontsReady = true; glyphCache.clear(); build(); }, () => { fontsReady = true; });
  } else fontsReady = true;

  // ---- input: pointer parallax, theme, resize, visibility
  let mx = 0, my = 0, rx = 0, ry = 0;
  if (!reduce) {
    window.addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse") return;
      mx = e.clientX / innerWidth - 0.5;
      my = e.clientY / innerHeight - 0.5;
    }, { passive: true });
  }
  document.addEventListener("themechange", () => { applyTheme(); if (reduce || !running) draw(performance.now()); });
  window.addEventListener("resize", () => {
    const w = stage.clientWidth, h = stage.clientHeight;
    if (!w || !h || (w === W && Math.abs(h - H) < 80 && small)) return;   // ignore mobile toolbar resizes
    W = w; H = h;
    renderer.setSize(W, H);
    composer.setSize(W, H);
    bloom.resolution.set(W / 2, H / 2);
    layout();
    if (reduce || !running) draw(performance.now());
  });

  // ---- per frame
  const ambient = new Float32Array(CELLS);   // the hero's gentle lift, on a few cells at a time
  let ambientCycle = -1, ambientCells = [];
  const smooth = (x) => x * x * (3 - 2 * x);
  let shown = 0;   // eased stage value actually drawn
  const accent = new THREE.Color();
  function draw(now) {
    const t = now / 1000;
    const target = Math.max(0, Math.min(stages.length - 1, (window.__story && window.__story.stage) || 0));
    shown = reduce ? target : shown + (target - shown) * 0.12;
    if (Math.abs(target - shown) < 0.0005) shown = target;
    const s0 = Math.min(stages.length - 1, Math.floor(shown)), s1 = Math.min(stages.length - 1, s0 + 1);
    const f = shown - s0, A = stages[s0], B = stages[s1];

    // Ambient lift in the hero: every 8 s a few cells rise and glow, then settle.
    const CYCLE = 8, cyc = Math.floor(t / CYCLE), p = (t % CYCLE) / CYCLE;
    if (cyc !== ambientCycle) {
      ambientCycle = cyc;
      rngState = 101 + cyc;
      ambientCells = pickNodes(small ? 5 : 8, 2.2);
    }
    const lift = reduce ? 1 : smooth(p < 0.45 ? 0 : p < 0.6 ? (p - 0.45) / 0.15 : p < 0.85 ? 1 : Math.max(0, 1 - (p - 0.85) / 0.15));
    ambient.fill(0);
    const heroness = Math.max(0, 1 - shown);   // fades out as the story moves on
    ambientCells.forEach((c) => { ambient[c] = lift * heroness; });

    for (let i = 0; i < N; i++) {
      // Stagger per particle so shapes dissolve and re-form rather than slide.
      const local = smooth(Math.max(0, Math.min(1, f * 1.5 - seed[i] * 0.5)));
      const i3 = i * 3, amb = ambient[cellOf[i]];
      const wave = Math.sin(t * 1.2 + (cellOf[i] % COLS) * 0.35 + Math.floor(cellOf[i] / COLS) * 0.55) * 0.05 * heroness;
      pos[i3] = A.pos[i3] + (B.pos[i3] - A.pos[i3]) * local;
      pos[i3 + 1] = A.pos[i3 + 1] + (B.pos[i3 + 1] - A.pos[i3 + 1]) * local + wave + amb * 0.9;
      pos[i3 + 2] = A.pos[i3 + 2] + (B.pos[i3 + 2] - A.pos[i3 + 2]) * local;
      aAlpha[i] = A.alpha[i] + (B.alpha[i] - A.alpha[i]) * local;
      aMix[i] = Math.max(A.mix[i] + (B.mix[i] - A.mix[i]) * local, amb);
      aGlow[i] = Math.max(A.glow[i] + (B.glow[i] - A.glow[i]) * local, amb);
      aSize[i] = A.size[i] + (B.size[i] - A.size[i]) * local;
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.aAlpha.needsUpdate = true;
    geo.attributes.aMix.needsUpdate = true;
    geo.attributes.aGlow.needsUpdate = true;
    geo.attributes.aSize.needsUpdate = true;
    accent.copy(accentOf[A.accent]).lerp(accentOf[B.accent], smooth(f));
    mat.uniforms.uAccent.value.copy(accent);

    // The ledger sits beside the hero copy on wide screens, and centres for the story.
    const wide = W / H > 1.3;
    const aside = wide ? 1.6 * heroness : 0;
    mat.uniforms.uScrim.value = wide ? heroness : 0;
    mat.uniforms.uDim.value = wide ? 0 : 0.45 * heroness;
    group.position.x += (aside - group.position.x) * (reduce ? 1 : 0.08);
    ry += (mx * 0.3 - ry) * 0.05;
    rx += (my * 0.14 - rx) * 0.05;
    group.rotation.y = ry;
    group.rotation.x = rx;
    // Slow drift, a few percent of the distance, so the frame is never quite still.
    const drift = reduce ? 0 : 1;
    camera.position.set(Math.sin(t * 0.07) * dist * 0.03 * drift,
                        Math.sin(TILT) * dist + Math.sin(t * 0.05) * dist * 0.015 * drift,
                        Math.cos(TILT) * dist);
    camera.lookAt(0, 0, 0);
    composer.render();
  }

  // ---- run only while it can be seen
  let running = false, visible = true, raf = 0;
  function loop(now) { if (!running) return; draw(now); raf = requestAnimationFrame(loop); }
  function update() {
    const want = !reduce && visible && !document.hidden;
    if (want && !running) { running = true; raf = requestAnimationFrame(loop); }
    if (!want && running) { running = false; cancelAnimationFrame(raf); }
  }
  new IntersectionObserver((es) => { visible = es[es.length - 1].isIntersecting; update(); }).observe(stage);
  document.addEventListener("visibilitychange", update);

  // Read-only hooks for the checks: the stage list and the points each number was drawn with.
  window.__hero = {
    count: N,
    fontsReady: () => fontsReady,
    stages: () => stages.map((s) => s.text || null),
    shown: () => shown,
    running: () => running,
    glyphs: () => stages.filter((s) => s.sample && s.text !== "WK")
      .map((s) => ({ text: s.text, points: Array.from(s.sample.points), aspect: s.sample.aspect }))
  };

  if (reduce) draw(performance.now()); else update();
  stage.classList.add("ready");   // fades the canvas in over the CSS gradient
  document.dispatchEvent(new CustomEvent("hero:ready"));
}
