// williamckim.com · Home hero
// A grid of ledger cells. Every few seconds a handful lift into nodes and connect into a graph,
// then settle back into the ledger. Mouse adds slight parallax. Reduced motion renders one frame.
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
  stage.appendChild(renderer.domElement);

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(32, W / H, 0.1, 100);
  camera.position.set(0, 9.5, 13);
  camera.lookAt(0, 0, 0);

  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  var key = new THREE.DirectionalLight(0xffffff, 0.7);
  key.position.set(4, 8, 6);
  scene.add(key);

  // Palette (matches CSS tokens)
  var C_CELL = new THREE.Color(0xdfe2dc);
  var C_CELL_ALT = new THREE.Color(0xd3d7d0);
  var C_NODE = new THREE.Color(0x1e6b47);
  var C_LINE = 0x2a4a78;

  var COLS = 14, ROWS = 10, GAP = 0.78, CELL = 0.62, THICK = 0.12;
  var count = COLS * ROWS;
  var geo = new THREE.BoxGeometry(CELL, THICK, CELL);
  var mat = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.0 });
  var mesh = new THREE.InstancedMesh(geo, mat, count);
  var group = new THREE.Group();
  group.add(mesh);
  scene.add(group);

  var dummy = new THREE.Object3D();
  var base = [], colorTarget = [], lift = new Float32Array(count), liftTarget = new Float32Array(count);
  var color = new THREE.Color();
  for (var r = 0; r < ROWS; r++) {
    for (var c = 0; c < COLS; c++) {
      var i = r * COLS + c;
      base.push({ x: (c - (COLS - 1) / 2) * GAP, z: (r - (ROWS - 1) / 2) * GAP, phase: (c * 0.35 + r * 0.55) });
      colorTarget[i] = (r % 2 === 0) ? C_CELL : C_CELL_ALT;
      mesh.setColorAt(i, colorTarget[i]);
    }
  }
  mesh.instanceColor.needsUpdate = true;

  // Graph edges (rebuilt each cycle)
  var lineGeo = new THREE.BufferGeometry();
  var lineMat = new THREE.LineBasicMaterial({ color: C_LINE, transparent: true, opacity: 0 });
  var lines = new THREE.LineSegments(lineGeo, lineMat);
  group.add(lines);

  var nodes = [], edges = [];
  function pickGraph() {
    nodes = [];
    var want = 9;
    var tries = 0;
    while (nodes.length < want && tries < 200) {
      tries++;
      var i = Math.floor(Math.random() * count);
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
        var key = a < o.b ? a + "-" + o.b : o.b + "-" + a;
        if (!edges.some(function (e) { return e.key === key; })) edges.push({ key: key, a: a, b: o.b });
      });
    });
    var pos = new Float32Array(edges.length * 6);
    lineGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  }
  pickGraph();

  var mouseX = 0, mouseY = 0, targetRX = 0, targetRY = 0;
  function onMove(e) {
    var rect = stage.getBoundingClientRect();
    var px = (e.clientX - rect.left) / rect.width - 0.5;
    var py = (e.clientY - rect.top) / rect.height - 0.5;
    mouseX = px; mouseY = py;
  }
  if (!reduce) {
    stage.addEventListener("mousemove", onMove);
    stage.addEventListener("mouseleave", function () { mouseX = 0; mouseY = 0; });
  }

  // Cycle: ledger (rest) -> lift -> hold -> settle. Period ~8s.
  var t0 = performance.now(), CYCLE = 8000;
  function phaseAt(ms) {
    var p = (ms % CYCLE) / CYCLE;          // 0..1
    if (p < 0.50) return 0;                // rest
    if (p < 0.62) return (p - 0.50) / 0.12; // lifting
    if (p < 0.86) return 1;                // hold
    return 1 - (p - 0.86) / 0.14;          // settling
  }
  function ease(x) { return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2; }

  var lastCycle = 0;
  function frame(now) {
    var ms = now - t0;
    var cycle = Math.floor(ms / CYCLE);
    if (cycle !== lastCycle) { lastCycle = cycle; pickGraph(); }
    var ph = ease(phaseAt(ms));
    var tsec = ms / 1000;

    for (var i = 0; i < count; i++) {
      var b = base[i];
      var isNode = nodes.indexOf(i) !== -1;
      var wave = Math.sin(tsec * 1.2 + b.phase) * 0.05;
      var y = wave + (isNode ? ph * 1.6 : 0);
      dummy.position.set(b.x, y, b.z);
      dummy.rotation.set(0, isNode ? ph * Math.PI * 0.5 : 0, 0);
      var s = isNode ? 1 - ph * 0.35 : 1;
      dummy.scale.set(s, isNode ? 1 + ph * 2.2 : 1, s);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      color.copy(colorTarget[i]).lerp(C_NODE, isNode ? ph : 0);
      mesh.setColorAt(i, color);
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;

    // Edges follow nodes
    var pos = lineGeo.getAttribute("position");
    if (pos) {
      for (var e = 0; e < edges.length; e++) {
        var A = base[edges[e].a], B = base[edges[e].b];
        var ya = ph * 1.6 + 0.15, yb = ph * 1.6 + 0.15;
        pos.setXYZ(e * 2, A.x, ya, A.z);
        pos.setXYZ(e * 2 + 1, B.x, yb, B.z);
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

  function resize() {
    W = stage.clientWidth; H = stage.clientHeight;
    if (!W || !H) return;
    renderer.setSize(W, H);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    if (reduce) frame(t0 + CYCLE * 0.7);
  }
  window.addEventListener("resize", resize);

  if (reduce) { frame(t0 + CYCLE * 0.7); } else { requestAnimationFrame(frame); }
})();
