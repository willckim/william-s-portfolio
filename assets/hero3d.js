// williamckim.com · Home hero
// A grid of ledger cells sitting behind the hero copy as a full-bleed layer. Every few seconds
// a handful lift into nodes, take on that cycle's accent, and connect into a graph, then settle.
// The camera fits the whole grid to the viewport, so no cell is ever clipped at any width.
// Mouse adds slight parallax. Reduced motion renders one frame and never starts the loop.
// Colours follow the site theme and change live on the themechange event from site.js.
// Requires three.js (r128) loaded before this file.
(function () {
  var stage = document.getElementById("stage");
  if (!stage || typeof THREE === "undefined") { if (stage) stage.classList.add("static"); return; }

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var W = stage.clientWidth, H = stage.clientHeight;

  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  } catch (e) { stage.classList.add("static"); return; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(W, H);
  renderer.setClearColor(0x000000, 0);   // transparent over the CSS gradient
  stage.appendChild(renderer.domElement);

  var scene = new THREE.Scene();
  // Far plane must comfortably exceed any distance the fit search can reach, otherwise
  // the fit test fails on far-plane clipping and the search runs away to its ceiling.
  var CAM_FAR = 500, FIT_MAX = 320;
  var camera = new THREE.PerspectiveCamera(32, W / H, 0.1, CAM_FAR);

  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  var key = new THREE.DirectionalLight(0xffffff, 0.7);   // intensity set per theme below
  key.position.set(4, 8, 6);
  scene.add(key);

  // Palette per theme (matches the CSS tokens). Light: pale cells on the bone
  // gradient. Dark: cells a step above the near-black page, so the grid reads as a
  // surface rather than holes, and the brighter dark-theme accents with more glow.
  var PALETTES = {
    light: { cell: 0xdfe2dc, alt: 0xd3d7d0, accents: [0x1e6b47, 0xd98e04, 0xd1495b], glow: 0.25, key: 0.7 },
    dark:  { cell: 0x2c3136, alt: 0x252a2e, accents: [0x5cc28c, 0xe3a83d, 0xf28593], glow: 0.3, key: 0.55 }
  };
  function themeName() {
    return document.documentElement.getAttribute("data-theme-resolved") === "dark" ? "dark" : "light";
  }
  var P = PALETTES[themeName()];
  var C_CELL = new THREE.Color(P.cell);
  var C_CELL_ALT = new THREE.Color(P.alt);
  // One accent per cycle: ledger green, amber, coral.
  var ACCENTS = P.accents.slice();
  key.intensity = P.key;

  var COLS = 18, ROWS = 12, GAP = 0.78, CELL = 0.62, THICK = 0.12;
  var NODE_COUNT = 12, LIFT = 1.6;
  var TILT = 38 * Math.PI / 180;   // camera elevation, so the grid reads as a receding plane
  var count = COLS * ROWS;

  var geo = new THREE.BoxGeometry(CELL, THICK, CELL);
  // Slight transparency gives the cells a soft, shadowed feel against the gradient.
  var matBase = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.0, transparent: true, opacity: 0.9 });
  var matNode = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.0, transparent: true, opacity: 0.9 });

  // Two meshes: the flat ledger, and the lifted nodes. Nodes get their own material so the
  // emissive glow lands only on them (emissive is per material, not per instance).
  var mesh = new THREE.InstancedMesh(geo, matBase, count);
  var nodeMesh = new THREE.InstancedMesh(geo, matNode, NODE_COUNT);
  var group = new THREE.Group();
  group.add(mesh);
  group.add(nodeMesh);
  scene.add(group);

  var dummy = new THREE.Object3D();
  var base = [], colorTarget = [];
  var color = new THREE.Color();
  var accent = new THREE.Color(ACCENTS[0]);
  for (var r = 0; r < ROWS; r++) {
    for (var c = 0; c < COLS; c++) {
      var i = r * COLS + c;
      base.push({ x: (c - (COLS - 1) / 2) * GAP, z: (r - (ROWS - 1) / 2) * GAP, phase: (c * 0.35 + r * 0.55) });
      colorTarget[i] = (r % 2 === 0) ? C_CELL : C_CELL_ALT;
      mesh.setColorAt(i, colorTarget[i]);
    }
  }
  mesh.instanceColor.needsUpdate = true;
  for (var k = 0; k < NODE_COUNT; k++) nodeMesh.setColorAt(k, C_CELL);
  nodeMesh.instanceColor.needsUpdate = true;

  // Graph edges (rebuilt each cycle)
  var lineGeo = new THREE.BufferGeometry();
  var lineMat = new THREE.LineBasicMaterial({ color: ACCENTS[0], transparent: true, opacity: 0 });
  var lines = new THREE.LineSegments(lineGeo, lineMat);
  group.add(lines);

  var nodes = [], edges = [];
  function pickGraph(cycle) {
    accent.setHex(ACCENTS[((cycle % ACCENTS.length) + ACCENTS.length) % ACCENTS.length]);
    lineMat.color.copy(accent);
    matNode.emissive.copy(accent);
    nodes = [];
    var tries = 0;
    while (nodes.length < NODE_COUNT && tries < 400) {
      tries++;
      var i = Math.floor(Math.random() * count);
      if (nodes.indexOf(i) !== -1) continue;
      var ok = nodes.every(function (n) {
        var dx = base[n].x - base[i].x, dz = base[n].z - base[i].z;
        return Math.sqrt(dx * dx + dz * dz) > 1.5;
      });
      if (ok) nodes.push(i);
    }
    // Connect each node to its two nearest neighbors
    edges = [];
    nodes.forEach(function (a) {
      var others = nodes.filter(function (b) { return b !== a; }).map(function (b) {
        var dx = base[a].x - base[b].x, dz = base[a].z - base[b].z;
        return { b: b, d: dx * dx + dz * dz };
      }).sort(function (p, q) { return p.d - q.d; }).slice(0, 2);
      others.forEach(function (o) {
        var ek = a < o.b ? a + "-" + o.b : o.b + "-" + a;
        if (!edges.some(function (e) { return e.key === ek; })) edges.push({ key: ek, a: a, b: o.b });
      });
    });
    lineGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(edges.length * 6), 3));
  }

  // ---- Fit the whole grid into the frustum, at any aspect ratio ----
  // Extremes include the lift height and the full mouse-parallax rotation envelope, so the
  // corner cells stay inside the frame even while the group is tilted by the cursor.
  var MAX_RY = 0.5 * 0.35, MAX_RX = 0.5 * 0.18;   // mouse range is -0.5..0.5
  var halfW = ((COLS - 1) / 2) * GAP + CELL / 2;
  var halfD = ((ROWS - 1) / 2) * GAP + CELL / 2;

  function extremePoints() {
    var pts = [], e = new THREE.Euler(), m = new THREE.Matrix4(), v;
    var rxs = [-MAX_RX, 0, MAX_RX], rys = [-MAX_RY, 0, MAX_RY];
    for (var a = 0; a < rxs.length; a++) {
      for (var b = 0; b < rys.length; b++) {
        e.set(rxs[a], rys[b], 0);
        m.makeRotationFromEuler(e);
        for (var sx = -1; sx <= 1; sx += 2) {
          for (var sz = -1; sz <= 1; sz += 2) {
            for (var yy = 0; yy <= 1; yy++) {
              v = new THREE.Vector3(sx * halfW, yy * (LIFT + THICK * 3), sz * halfD);
              v.applyMatrix4(m).add(group.position);
              pts.push(v);
            }
          }
        }
      }
    }
    return pts;
  }

  function fitCamera() {
    var dir = new THREE.Vector3(0, Math.sin(TILT), Math.cos(TILT));
    var pts = extremePoints();
    function fitsAt(d) {
      camera.position.copy(dir).multiplyScalar(d);
      camera.lookAt(0, 0, 0);
      camera.updateMatrixWorld(true);
      camera.updateProjectionMatrix();
      for (var i = 0; i < pts.length; i++) {
        var p = pts[i].clone().project(camera);
        if (!(Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1 && p.z < 1)) return false;
      }
      return true;
    }
    // Grow the upper bound until the grid genuinely fits, so the search starts from a
    // bracket where lo does not fit and hi does.
    var lo = 1, hi = 20;
    while (hi < FIT_MAX && !fitsAt(hi)) { lo = hi; hi *= 1.6; }
    for (var it = 0; it < 44; it++) {
      var mid = (lo + hi) / 2;
      if (fitsAt(mid)) hi = mid; else lo = mid;
    }
    fitsAt(hi * 1.12);   // 12% padding around the fitted grid
  }

  function layout() {
    var aspect = W / H;
    // On wide screens nudge the grid right so it sits beside the hero copy, not under it.
    group.position.x = aspect > 1.3 ? 1.5 : 0;
    camera.aspect = aspect;
    fitCamera();
  }

  pickGraph(0);
  layout();

  var mouseX = 0, mouseY = 0, targetRX = 0, targetRY = 0;
  function onMove(e) {
    var rect = stage.getBoundingClientRect();
    mouseX = (e.clientX - rect.left) / rect.width - 0.5;
    mouseY = (e.clientY - rect.top) / rect.height - 0.5;
  }
  if (!reduce) {
    stage.addEventListener("mousemove", onMove);
    stage.addEventListener("mouseleave", function () { mouseX = 0; mouseY = 0; });
  }

  // Cycle: ledger (rest) -> lift -> hold -> settle. Period ~8s.
  var t0 = performance.now(), CYCLE = 8000;
  function phaseAt(ms) {
    var p = (ms % CYCLE) / CYCLE;           // 0..1
    if (p < 0.50) return 0;                 // rest
    if (p < 0.62) return (p - 0.50) / 0.12; // lifting
    if (p < 0.86) return 1;                 // hold
    return 1 - (p - 0.86) / 0.14;           // settling
  }
  function ease(x) { return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2; }

  var lastCycle = 0;
  function frame(now) {
    var ms = now - t0;
    var cycle = Math.floor(ms / CYCLE);
    if (cycle !== lastCycle) { lastCycle = cycle; pickGraph(cycle); }
    var ph = ease(phaseAt(ms));
    var tsec = ms / 1000;

    // Flat ledger. Node cells are collapsed here and drawn by nodeMesh instead.
    for (var i = 0; i < count; i++) {
      var b = base[i];
      var isNode = nodes.indexOf(i) !== -1;
      var wave = Math.sin(tsec * 1.2 + b.phase) * 0.05;
      dummy.position.set(b.x, wave, b.z);
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(isNode ? 0 : 1, isNode ? 0 : 1, isNode ? 0 : 1);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;

    // Lifted nodes, with this cycle's accent.
    for (var n = 0; n < NODE_COUNT; n++) {
      var idx = nodes[n];
      if (idx === undefined) {
        dummy.position.set(0, 0, 0); dummy.rotation.set(0, 0, 0); dummy.scale.set(0, 0, 0);
        dummy.updateMatrix(); nodeMesh.setMatrixAt(n, dummy.matrix);
        continue;
      }
      var nb = base[idx];
      var nwave = Math.sin(tsec * 1.2 + nb.phase) * 0.05;
      var s = 1 - ph * 0.35;
      dummy.position.set(nb.x, nwave + ph * LIFT, nb.z);
      dummy.rotation.set(0, ph * Math.PI * 0.5, 0);
      dummy.scale.set(s, 1 + ph * 2.2, s);
      dummy.updateMatrix();
      nodeMesh.setMatrixAt(n, dummy.matrix);
      color.copy(colorTarget[idx]).lerp(accent, ph);
      nodeMesh.setColorAt(n, color);
    }
    nodeMesh.instanceMatrix.needsUpdate = true;
    if (nodeMesh.instanceColor) nodeMesh.instanceColor.needsUpdate = true;
    matNode.emissiveIntensity = P.glow * ph;   // faint glow, lifted nodes only

    // Edges follow the nodes
    var pos = lineGeo.getAttribute("position");
    if (pos) {
      for (var e = 0; e < edges.length; e++) {
        var A = base[edges[e].a], B = base[edges[e].b];
        var y = ph * LIFT + 0.15;
        pos.setXYZ(e * 2, A.x, y, A.z);
        pos.setXYZ(e * 2 + 1, B.x, y, B.z);
      }
      pos.needsUpdate = true;
      lineMat.opacity = ph * 0.9;
    }

    targetRY += ((mouseX * 0.35) - targetRY) * 0.06;
    targetRX += ((mouseY * 0.18) - targetRX) * 0.06;
    group.rotation.y = targetRY;
    group.rotation.x = targetRX;

    renderer.render(scene, camera);
    if (!reduce) requestAnimationFrame(frame);
  }

  // The toggle, or the system setting changing, recolours the scene in place.
  document.addEventListener("themechange", function () {
    P = PALETTES[themeName()];
    C_CELL.setHex(P.cell);
    C_CELL_ALT.setHex(P.alt);
    ACCENTS = P.accents.slice();
    key.intensity = P.key;
    for (var i = 0; i < count; i++) mesh.setColorAt(i, colorTarget[i]);
    mesh.instanceColor.needsUpdate = true;
    pickGraph(lastCycle);
    if (reduce) frame(t0 + CYCLE * 0.7);
  });

  function resize() {
    W = stage.clientWidth; H = stage.clientHeight;
    if (!W || !H) return;
    renderer.setSize(W, H);
    layout();
    if (reduce) frame(t0 + CYCLE * 0.7);
  }
  window.addEventListener("resize", resize);

  // Small read-only hook so the corner-cell clipping check can be verified in a real browser.
  window.__hero = {
    cols: COLS, rows: ROWS,
    cornerScreen: function () {
      var rect = renderer.domElement.getBoundingClientRect();
      var corners = [0, COLS - 1, (ROWS - 1) * COLS, count - 1];
      return corners.map(function (idx) {
        var b = base[idx];
        var v = new THREE.Vector3(b.x, 0, b.z);
        group.updateMatrixWorld(true);
        v.applyMatrix4(group.matrixWorld).project(camera);
        return {
          index: idx,
          x: (v.x + 1) / 2 * rect.width,
          y: (1 - v.y) / 2 * rect.height,
          ndcX: v.x, ndcY: v.y
        };
      });
    },
    canvasSize: function () {
      var rect = renderer.domElement.getBoundingClientRect();
      return { w: rect.width, h: rect.height };
    },
    camDistance: function () { return camera.position.length(); }
  };

  if (reduce) { frame(t0 + CYCLE * 0.7); } else { requestAnimationFrame(frame); }
})();
