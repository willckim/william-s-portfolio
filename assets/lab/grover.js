// Grover amplitude visualizer: the real algorithm on a 16-state vector, in the browser.
//
//   start      every amplitude 1/sqrt(N)
//   oracle     flip the sign of the marked state's amplitude
//   diffusion  reflect every amplitude about the mean:  a[i] = 2*mean - a[i]
//
// One iteration is oracle then diffusion. Nothing here uses the closed form: the
// probability shown is a[target]^2 after the operations actually applied, and
// tests/check_grover.py compares it with sin^2((2k+1)*theta), theta = asin(1/sqrt(N)).
(function () {
  "use strict";
  var root = document.getElementById("grover");
  if (!root) return;

  var N = 1 << +root.dataset.qubits;
  var repoIterations = +root.dataset.repoIterations;
  var bars = root.querySelector(".g-bars");
  var sel = root.querySelector("#g-target");
  var status = root.querySelector(".g-status");
  var meanLine = root.querySelector(".g-mean");
  var halfBtn = root.querySelector("[data-g=oracle]");
  var theta = Math.asin(1 / Math.sqrt(N));
  var optimal = Math.floor(Math.PI / (4 * theta));

  var s = { a: [], k: 0, half: false, target: +root.dataset.target };

  function reset() {
    s.a = [];
    for (var i = 0; i < N; i++) s.a.push(1 / Math.sqrt(N));
    s.k = 0;
    s.half = false;
  }
  function oracle() { s.a[s.target] = -s.a[s.target]; s.half = true; }
  function diffusion() {
    var mean = 0;
    for (var i = 0; i < N; i++) mean += s.a[i];
    mean /= N;
    for (var j = 0; j < N; j++) s.a[j] = 2 * mean - s.a[j];
    s.half = false;
    s.k++;
  }

  // Bars: one per basis state, drawn from a zero line so a negative amplitude hangs below it.
  for (var i = 0; i < N; i++) {
    var col = document.createElement("div");
    col.className = "g-col";
    col.innerHTML = '<span class="g-bar"></span><span class="g-label num"></span>';
    col.querySelector(".g-label").textContent = String(i);
    bars.appendChild(col);
    var o = document.createElement("option");
    o.value = String(i);
    o.textContent = i + " (" + i.toString(2).padStart(Math.log2(N), "0") + ")";
    sel.appendChild(o);
  }
  sel.value = String(s.target);

  function pct(p) { return (p * 100).toFixed(1) + "%"; }

  function render() {
    var cols = bars.children, mean = 0;
    for (var i = 0; i < N; i++) {
      var amp = s.a[i];
      mean += amp;
      var bar = cols[i].querySelector(".g-bar");
      // Amplitudes stay within [-1, 1]; the chart's half-height is one unit.
      bar.style.transform = "scaleY(" + Math.abs(amp).toFixed(4) + ")";
      bar.classList.toggle("neg", amp < 0);
      cols[i].classList.toggle("marked", i === s.target);
    }
    mean /= N;
    meanLine.style.top = (50 - mean * 50).toFixed(3) + "%";
    meanLine.hidden = !s.half;
    var p = s.a[s.target] * s.a[s.target];
    var theory = Math.pow(Math.sin((2 * s.k + 1) * theta), 2);
    root.dataset.k = String(s.k);
    root.dataset.p = String(p);
    halfBtn.textContent = s.half ? "Apply diffusion" : "Apply oracle";
    root.querySelector(".g-k").textContent = String(s.k);
    root.querySelector(".g-p").textContent = pct(p);
    var th = root.querySelector(".g-theory");
    th.textContent = s.half ? "after diffusion" : pct(theory);
    th.classList.toggle("num", !s.half);          // Plex Mono is for numbers only
    status.textContent = "After " + s.k + (s.k === 1 ? " iteration" : " iterations") +
      (s.half ? " and an oracle step" : "") + ", the marked state " + s.target +
      " has probability " + pct(p) + "." +
      (!s.half && s.k === optimal ? " That is the optimum for " + N + " states." : "") +
      (!s.half && s.k > optimal ? " Past the optimum, the amplitude rotates away again." : "");
  }

  root.querySelector(".g-optimal").textContent = String(optimal);
  root.querySelector(".g-repo-p").textContent =
    pct(Math.pow(Math.sin((2 * repoIterations + 1) * theta), 2));
  root.querySelector(".g-opt-p").textContent =
    pct(Math.pow(Math.sin((2 * optimal + 1) * theta), 2));

  halfBtn.addEventListener("click", function () {
    if (s.half) diffusion(); else oracle();
    render();
  });
  root.querySelector("[data-g=step]").addEventListener("click", function () {
    if (!s.half) oracle();
    diffusion();
    render();
  });
  root.querySelector("[data-g=reset]").addEventListener("click", function () { reset(); render(); });
  sel.addEventListener("change", function () { s.target = +sel.value; reset(); render(); });

  reset();
  render();
})();
