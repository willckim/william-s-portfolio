// williamckim.com · Work index previews
// Each Ortho project gets a short procedural loop drawn on a 2D canvas, not a video:
//   concur         transactions stream in, pass a rules gate, sort into buckets, a person checks
//   royalty        rates flow down a pipeline and land as totals, each ticked
//   fast-close     a column of red flags turning green one by one
//   time-tracker   hours filling a weekly grid, then an approval stamp
//   consolidation  three platforms sliding together into one
// Decoration only (aria-hidden), with no figures in them, so nothing reads as a metric.
// Desktop (hover and a fine pointer): one preview card follows the cursor over a name,
// and sits beside a name that has keyboard focus. Touch: the canvases in each row are
// shown inline as thumbnails, animated while on screen. Reduced motion: no card, and
// thumbnails hold a still frame.
(function () {
  "use strict";
  var rows = Array.prototype.slice.call(document.querySelectorAll(".ix-row[data-preview]"));
  if (!rows.length) return;
  var reduce = matchMedia("(prefers-reduced-motion: reduce)");
  var desk = matchMedia("(hover: hover) and (pointer: fine)");
  var DPR = Math.min(window.devicePixelRatio || 1, 2);

  // Theme colours, read live so a theme switch repaints in the new palette.
  var C = {};
  function colours() {
    var s = getComputedStyle(document.documentElement);
    ["bone", "surface", "ink", "ink-2", "ink-3", "rule", "ledger", "ledger-2", "coral", "coral-2",
     "amber", "amber-2", "blueprint", "blueprint-2", "violet", "violet-2"].forEach(function (k) {
      C[k] = s.getPropertyValue("--" + k).trim();
    });
  }
  colours();
  document.addEventListener("themechange", function () { colours(); stillFrames(); });

  function ease(x) { return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; }
  function clamp(x) { return Math.max(0, Math.min(1, x)); }
  function rr(g, x, y, w, h, r) { g.beginPath(); g.roundRect(x, y, w, h, r); }
  function check(g, x, y, s, col) {
    g.strokeStyle = col; g.lineWidth = Math.max(1.5, s * 0.22); g.lineCap = "round"; g.lineJoin = "round";
    g.beginPath(); g.moveTo(x - s * 0.5, y); g.lineTo(x - s * 0.1, y + s * 0.4); g.lineTo(x + s * 0.55, y - s * 0.45); g.stroke();
  }

  var DRAW = {
    concur: function (g, t, w, h) {
      var gateX = w * 0.44, bx = w * 0.7, by = [h * 0.28, h * 0.5, h * 0.72], cols = [C.ledger, C.blueprint, C.violet];
      // buckets
      g.strokeStyle = C.rule; g.lineWidth = 1.5;
      by.forEach(function (y) { g.beginPath(); g.moveTo(bx - 14, y - 9); g.lineTo(bx - 14, y + 9); g.lineTo(bx + 30, y + 9); g.lineTo(bx + 30, y - 9); g.stroke(); });
      // the rules gate
      rr(g, gateX - 7, h * 0.16, 14, h * 0.68, 7); g.fillStyle = C["amber-2"]; g.fill();
      g.strokeStyle = C.amber; g.lineWidth = 1.5; g.stroke();
      g.save(); g.translate(gateX, h * 0.5); g.rotate(-Math.PI / 2); g.fillStyle = C.amber;
      g.font = "600 10px system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("rules", 0, 0); g.restore();
      // transactions
      for (var k = 0; k < 26; k++) {
        var ph = (t * 0.32 + k / 26) % 1, b = k % 3, x, y, col = C["ink-3"];
        var lane = h * (0.22 + ((k * 5) % 7) / 12 + (((k * 7919) % 11) - 5) / 400);   // seven lanes, not in step with the phase
        if (ph < 0.5) { x = (ph / 0.5) * (gateX - 12); y = lane; }
        else {
          var u = ease(clamp((ph - 0.5) / 0.4));
          x = gateX + 10 + (bx + 8 - gateX - 10) * u; y = lane + (by[b] - lane) * u; col = cols[b];
        }
        g.beginPath(); g.arc(x, y, 3, 0, Math.PI * 2); g.fillStyle = col; g.fill();
      }
      // a person checks the output
      var px = w * 0.9, py = h * 0.46;
      g.fillStyle = C["ink-2"]; g.beginPath(); g.arc(px, py - 13, 7, 0, Math.PI * 2); g.fill();
      g.beginPath(); g.arc(px, py + 12, 13, Math.PI, 0); g.fill();
      if ((t % 2.4) > 1.2) check(g, px, py + 30, 12, C.ledger);
    },

    royalty: function (g, t, w, h) {
      var y0 = h * 0.3, x0 = w * 0.08, x1 = w * 0.6;
      g.strokeStyle = C.rule; g.lineWidth = 3; g.lineCap = "round";
      g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y0); g.lineTo(x1, h * 0.52); g.stroke();
      [0.3, 0.55, 0.8].forEach(function (f) {
        g.beginPath(); g.arc(x0 + (x1 - x0) * f, y0, 6, 0, Math.PI * 2); g.fillStyle = C.surface; g.fill();
        g.strokeStyle = C.blueprint; g.lineWidth = 2; g.stroke();
      });
      // rates flowing down the pipeline
      g.font = "600 11px system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
      for (var k = 0; k < 5; k++) {
        var ph = (t * 0.3 + k / 5) % 1, x, y;
        if (ph < 0.7) { x = x0 + (x1 - x0) * (ph / 0.7); y = y0; } else { x = x1; y = y0 + (h * 0.22) * ((ph - 0.7) / 0.3); }
        rr(g, x - 13, y - 9, 26, 18, 9); g.fillStyle = C["blueprint-2"]; g.fill();
        g.fillStyle = C.blueprint; g.fillText("%", x, y + 1);
      }
      // totals, each ticked once it lands
      var n = Math.floor((t * 1.2) % 7);
      for (var r = 0; r < 4; r++) {
        var ty = h * 0.6 + r * 17, on = r < n;
        rr(g, w * 0.46, ty, w * 0.3 * (0.6 + ((r * 7) % 5) / 10), 10, 5); g.fillStyle = on ? C.ledger : C.rule; g.fill();
        if (on) check(g, w * 0.86, ty + 5, 10, C.ledger);
      }
    },

    "fast-close": function (g, t, w, h) {
      var n = 7, top = h * 0.12, step = (h * 0.76) / n, green = Math.floor((t * 1.6) % (n + 3));
      for (var r = 0; r < n; r++) {
        var y = top + r * step + step / 2, ok = r < green;
        g.fillStyle = C.rule; rr(g, w * 0.34, y - 3, w * (0.3 + ((r * 5) % 4) / 12), 6, 3); g.fill();
        // the flag
        var fx = w * 0.2, col = ok ? C.ledger : C.coral;
        g.strokeStyle = C["ink-3"]; g.lineWidth = 1.5; g.beginPath(); g.moveTo(fx, y - 8); g.lineTo(fx, y + 9); g.stroke();
        g.fillStyle = col; g.beginPath(); g.moveTo(fx, y - 8); g.lineTo(fx + 15, y - 4); g.lineTo(fx, y); g.closePath(); g.fill();
        if (ok) check(g, w * 0.86, y, 9, C.ledger);
      }
    },

    "time-tracker": function (g, t, w, h) {
      var cols = 5, rowsN = 4, gx = w * 0.12, gy = h * 0.2, cw = (w * 0.62) / cols, ch = (h * 0.62) / rowsN;
      var p = (t * 0.45) % 1.6, filled = clamp(p / 1.1) * cols * rowsN;
      g.font = "600 10px system-ui, sans-serif"; g.textAlign = "center"; g.fillStyle = C["ink-3"];
      ["M", "T", "W", "T", "F"].forEach(function (d, i) { g.fillText(d, gx + cw * (i + 0.5), gy - 8); });
      for (var c = 0; c < cols; c++) {
        for (var r = 0; r < rowsN; r++) {
          var i = c * rowsN + r, x = gx + c * cw + 3, y = gy + r * ch + 3, ww = cw - 6, hh = ch - 6;
          rr(g, x, y, ww, hh, 4); g.fillStyle = C.surface; g.fill(); g.strokeStyle = C.rule; g.lineWidth = 1; g.stroke();
          var f = clamp(filled - i);
          if (f > 0) { rr(g, x, y + hh * (1 - f), ww, hh * f, 4); g.fillStyle = C["blueprint-2"]; g.fill(); }
        }
      }
      // approval stamp
      var s = clamp((p - 1.15) / 0.12);
      if (s > 0) {
        g.save(); g.translate(w * 0.8, h * 0.5); g.rotate(-0.22); g.scale(1.6 - 0.6 * s, 1.6 - 0.6 * s); g.globalAlpha = s;
        g.strokeStyle = C.ledger; g.lineWidth = 2.5; rr(g, -40, -15, 80, 30, 6); g.stroke();
        g.fillStyle = C.ledger; g.font = "700 12px system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
        g.fillText("APPROVED", 0, 1); g.restore();
      }
    },

    consolidation: function (g, t, w, h) {
      var p = (t * 0.35) % 1, m = ease(clamp((p - 0.15) / 0.4)) * (1 - ease(clamp((p - 0.85) / 0.15)));
      var cx = w * 0.5, cy = h * 0.5, bw = w * 0.22, bh = h * 0.28;
      var from = [[w * 0.2, h * 0.3], [w * 0.8, h * 0.3], [w * 0.5, h * 0.74]], cols = [C.blueprint, C.amber, C.violet];
      // the one platform they become
      g.globalAlpha = m;
      rr(g, cx - bw * 0.9, cy - bh * 0.9, bw * 1.8, bh * 1.8, 12); g.fillStyle = C["ledger-2"]; g.fill();
      g.strokeStyle = C.ledger; g.lineWidth = 2.5; g.stroke();
      g.globalAlpha = 1;
      from.forEach(function (f, i) {
        var x = f[0] + (cx - f[0]) * m, y = f[1] + (cy - f[1]) * m, s = 1 - 0.35 * m;
        g.globalAlpha = 1 - 0.75 * m;
        rr(g, x - bw * s / 2, y - bh * s / 2, bw * s, bh * s, 8); g.fillStyle = C.surface; g.fill();
        g.strokeStyle = cols[i]; g.lineWidth = 2; g.stroke();
        g.fillStyle = cols[i]; rr(g, x - bw * s / 2 + 8, y - bh * s / 2 + 8, bw * s * 0.5, 5, 2.5); g.fill();
        g.globalAlpha = 1;
      });
    }
  };

  function paint(canvas, name, t) {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    if (canvas.width !== Math.round(w * DPR)) { canvas.width = Math.round(w * DPR); canvas.height = Math.round(h * DPR); }
    var g = canvas.getContext("2d");
    g.setTransform(DPR, 0, 0, DPR, 0, 0);
    g.clearRect(0, 0, w, h);
    (DRAW[name] || function () {})(g, t, w, h);
  }

  // ---- touch: inline thumbnails, animated while on screen
  var thumbs = rows.map(function (r) { return { el: r.querySelector(".ix-thumb"), name: r.dataset.preview, on: false }; })
    .filter(function (x) { return x.el; });
  function stillFrames() { thumbs.forEach(function (x) { paint(x.el, x.name, 1.3); }); if (card) paint(cardCanvas, active, 1.3); }
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) { thumbs.forEach(function (x) { if (x.el === e.target) x.on = e.isIntersecting; }); });
    kick();
  });
  thumbs.forEach(function (x) { io.observe(x.el); });

  // ---- desktop: one card that follows the cursor
  var card = null, cardCanvas = null, active = null, tx = 0, ty = 0, cx = 0, cy = 0;
  function makeCard() {
    card = document.createElement("div");
    card.className = "ix-preview";
    card.setAttribute("aria-hidden", "true");
    card.innerHTML = '<div class="ix-preview-card"><canvas></canvas></div>';
    document.body.appendChild(card);
    cardCanvas = card.querySelector("canvas");
  }
  function show(name, x, y, jump) {
    if (!desk.matches || reduce.matches) return;
    if (!card) makeCard();
    active = name; tx = x; ty = y;
    if (jump) { cx = x; cy = y; }
    card.classList.add("on");
    kick();
  }
  function hide() { active = null; if (card) card.classList.remove("on"); }
  rows.forEach(function (r) {
    var link = r.querySelector(".ix-link");
    link.addEventListener("pointerenter", function (e) {
      if (e.pointerType === "mouse") show(r.dataset.preview, e.clientX + 28, e.clientY - 95, !active);
    });
    link.addEventListener("pointermove", function (e) { if (active) { tx = e.clientX + 28; ty = e.clientY - 95; } });
    link.addEventListener("pointerleave", hide);
    // Keyboard: the preview sits to the right of the focused name.
    link.addEventListener("focus", function () {
      if (!link.matches(":focus-visible")) return;
      var b = link.querySelector(".ix-name").getBoundingClientRect();
      show(r.dataset.preview, Math.min(b.right + 32, innerWidth - 320), b.top + b.height / 2 - 95, true);
    });
    link.addEventListener("blur", hide);
  });

  // ---- one loop for whatever is showing
  var raf = 0;
  function kick() { if (!raf && !reduce.matches) raf = requestAnimationFrame(loop); }
  function loop(now) {
    raf = 0;
    var t = now / 1000, busy = false;
    if (active && card) {
      cx += (tx - cx) * 0.2; cy += (ty - cy) * 0.2;
      card.style.transform = "translate3d(" + cx.toFixed(1) + "px," + cy.toFixed(1) + "px,0)";
      paint(cardCanvas, active, t);
      busy = true;
    }
    thumbs.forEach(function (x) {
      if (x.on && x.el.offsetParent) { paint(x.el, x.name, t); busy = true; }
    });
    if (busy && !document.hidden) raf = requestAnimationFrame(loop);
  }
  document.addEventListener("visibilitychange", kick);
  if (reduce.matches) stillFrames(); else kick();
  reduce.addEventListener("change", function () { hide(); stillFrames(); kick(); });
  window.__previews = { names: Object.keys(DRAW), active: function () { return active; } };
})();
