// Mosca's inequality calculator. Pure client-side arithmetic, no network calls.
// Inputs come from window.PQC_DATA (assets/lab/pqc-data.js), which tools/sitegen.py
// writes from the Post-Quantum Readiness Toolkit's own config. The status rules below
// are the toolkit's (mosca.py, Assessment.status):
//
//   x > z        EXPOSED NOW   exposed even if the migration finished today
//   x + y > z    EXPOSED       exposed at the planned migration speed
//   otherwise    safe          (x + y = z is safe: the inequality is strict)
//
// tests/check_mosca.py clicks every preset and compares the table with the
// toolkit's published report, and mutates the two comparisons to prove it can fail.
(function () {
  "use strict";
  var D = window.PQC_DATA;
  var root = document.getElementById("mosca");
  if (!D || !root) return;

  function assess(x, y, z) {
    var over = x + y - z;                    // years still sensitive after arrival
    if (x > z) return { status: "now", over: over };
    if (x + y > z) return { status: "exposed", over: over };
    return { status: "safe", over: over };
  }
  window.Mosca = { assess: assess };         // read-only hook for the checks

  var LABEL = { now: "Exposed now", exposed: "Exposed", safe: "Safe" };
  var SCALE = 40;                            // years across the timeline column

  var $ = function (id) { return document.getElementById(id); };
  var typeSel = $("m-type"), xIn = $("m-x"), yIn = $("m-y"), zIn = $("m-z");
  var tbody = root.querySelector("tbody");

  // State: the shelf life per type (defaults from the toolkit), y and z.
  var state = { x: {}, y: D.migration_years, z: 0 };
  function resetX() { D.data_types.forEach(function (t) { state.x[t.name] = t.shelf_life; }); }

  // --- build the static parts once -------------------------------------------------
  D.data_types.forEach(function (t, i) {
    var o = document.createElement("option");
    o.value = String(i);
    o.textContent = t.name;
    typeSel.appendChild(o);

    var tr = document.createElement("tr");
    tr.dataset.type = t.name;
    tr.innerHTML =
      '<th scope="row"></th><td class="x num"></td><td class="rules"></td>' +
      '<td class="status"><span class="pill"></span></td><td class="margin"></td>' +
      '<td class="tlcell" aria-hidden="true"><div class="tl"><span class="seg y"></span><span class="seg x"></span><span class="z"></span></div></td>';
    tr.querySelector("th").textContent = t.name + (t.basis_type === "assumption" ? " *" : "");
    var rules = tr.querySelector(".rules");
    t.rules.forEach(function (r) {
      var s = document.createElement("span");
      s.className = "rule";
      s.textContent = r;
      rules.appendChild(s);
    });
    tbody.appendChild(tr);
  });

  var presetRow = $("m-presets");
  D.scenarios.forEach(function (s) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "preset";
    b.dataset.preset = s.name;
    b.setAttribute("aria-pressed", "false");
    b.innerHTML = "<strong></strong><span></span>";
    b.querySelector("strong").textContent = s.name;
    b.querySelector("span").textContent = s.planning_year + " · window " + s.window[0] + " to " + s.window[1];
    b.addEventListener("click", function () { applyPreset(s); });
    presetRow.appendChild(b);
  });

  function applyPreset(s) {
    resetX();
    state.y = D.migration_years;
    state.z = s.planning_year - D.as_of_year;
    render();
  }

  // --- render ------------------------------------------------------------------------
  function years(n) { return n + (n === 1 ? " year" : " years"); }

  function render() {
    var t = D.data_types[+typeSel.value];
    xIn.value = state.x[t.name];
    yIn.value = state.y;
    zIn.value = state.z;
    $("m-x-out").textContent = years(state.x[t.name]);
    $("m-y-out").textContent = years(state.y);
    $("m-z-out").textContent = years(state.z) + ", " + (D.as_of_year + state.z);
    xIn.setAttribute("aria-valuetext", years(state.x[t.name]) + " for " + t.name);
    zIn.setAttribute("aria-valuetext", years(state.z) + ", the year " + (D.as_of_year + state.z));
    var edited = state.x[t.name] !== t.shelf_life;
    $("m-x-note").textContent = edited
      ? "Edited. The toolkit's value is " + years(t.shelf_life) + ": " + t.basis + "."
      : t.basis + ".";

    var exposed = 0, now = 0;
    D.data_types.forEach(function (d, i) {
      var x = state.x[d.name], a = assess(x, state.y, state.z);
      var tr = tbody.rows[i];
      if (a.status !== "safe") exposed++;
      if (a.status === "now") now++;
      tr.querySelector(".x").textContent = x + (x !== d.shelf_life ? " (edited)" : "");
      var cell = tr.querySelector(".status");
      cell.dataset.status = a.status;
      cell.querySelector(".pill").textContent = LABEL[a.status];
      var m = tr.querySelector(".margin");
      m.dataset.over = String(a.over);
      m.textContent = a.over > 0 ? years(a.over) + " over" : years(-a.over) + " to spare";
      tr.querySelector(".seg.y").style.width = Math.min(state.y, SCALE) / SCALE * 100 + "%";
      tr.querySelector(".seg.x").style.width = Math.min(x, Math.max(0, SCALE - state.y)) / SCALE * 100 + "%";
      tr.querySelector(".z").style.left = Math.min(state.z, SCALE) / SCALE * 100 + "%";
      tr.classList.toggle("is-current", i === +typeSel.value);
    });

    var arrival = D.as_of_year + state.z;
    $("m-summary").textContent = exposed + " of " + D.data_types.length +
      " record types exposed if a quantum computer arrives in " + arrival +
      " and migration takes " + years(state.y) + "." +
      (now ? " " + now + " would be exposed even if migration finished today." : "");

    presetRow.querySelectorAll(".preset").forEach(function (b) {
      var s = D.scenarios.filter(function (sc) { return sc.name === b.dataset.preset; })[0];
      var match = state.y === D.migration_years && state.z === s.planning_year - D.as_of_year &&
        D.data_types.every(function (d) { return state.x[d.name] === d.shelf_life; });
      b.setAttribute("aria-pressed", match ? "true" : "false");
    });
  }

  // --- inputs ------------------------------------------------------------------------
  typeSel.addEventListener("change", render);
  xIn.addEventListener("input", function () {
    state.x[D.data_types[+typeSel.value].name] = +xIn.value;
    render();
  });
  yIn.addEventListener("input", function () { state.y = +yIn.value; render(); });
  zIn.addEventListener("input", function () { state.z = +zIn.value; render(); });

  // Start on the toolkit's Base scenario, before anything optional can fail.
  resetX();
  var base = D.scenarios.filter(function (s) { return s.name === "Base"; })[0] || D.scenarios[0];
  applyPreset(base);

  var p = D.provenance || {};
  $("m-provenance").textContent = "Inputs from the toolkit's pqc_config.yaml, version " + p.toolkit_version +
    " (run " + String(p.toolkit_run || "").slice(0, 10) + ", commit " + p.commit +
    (p.uncommitted_changes ? " with uncommitted changes" : "") + "). As of " + D.as_of_year + ".";
})();
