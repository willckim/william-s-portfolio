// williamckim.com · Home hero loader
// The hero scene is an ES module on three.js 0.186.1, resolved through the import map
// in index.html (pinned versions, each file integrity-checked). three.js is not on the
// critical path: the headline is HTML and paints first, over the CSS gradient the
// canvas fades in on top of.
//
// When it loads: on a desktop-class device (fine pointer, wide screen) straight away,
// so the preloader can count it. Elsewhere on the first sign of a person (pointer,
// touch, key, scroll) or 2.5 s after load, whichever comes first, because on a phone
// parsing three.js costs a few hundred ms that the words above it should not wait on.
(function () {
  var stage = document.getElementById("stage");
  if (!stage) return;
  var started = false, SIGNALS = ["pointermove", "pointerdown", "touchstart", "keydown", "scroll"];
  function fail() { stage.classList.add("static"); document.dispatchEvent(new CustomEvent("hero:failed")); }
  function start() {
    if (started) return;
    started = true;
    SIGNALS.forEach(function (e) { window.removeEventListener(e, start); });
    import("/assets/hero/scene.js").then(function (m) {
      try { m.init(stage); } catch (e) { fail(); }
    }, fail);
  }
  var desktop = matchMedia("(pointer: fine) and (min-width: 900px)").matches;
  if (desktop) { start(); return; }
  SIGNALS.forEach(function (e) { window.addEventListener(e, start, { passive: true }); });
  var idle = window.requestIdleCallback || function (f) { setTimeout(f, 200); };
  function soon() { setTimeout(function () { idle(start); }, 2500); }
  if (document.readyState === "complete") soon(); else window.addEventListener("load", soon);
})();
