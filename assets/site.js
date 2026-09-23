// williamckim.com · shared behavior (no dependencies)
(function () {
  // Mobile menu
  var btn = document.querySelector(".menu-btn");
  var tabs = document.querySelector(".tabs");
  if (btn && tabs) {
    btn.addEventListener("click", function () {
      var open = tabs.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Sub-tabs (Work page). Markup: .subtabs > button[data-panel], .panel[id]
  var subtabs = document.querySelector(".subtabs");
  if (subtabs) {
    var buttons = Array.prototype.slice.call(subtabs.querySelectorAll("button"));
    var panels = Array.prototype.slice.call(document.querySelectorAll(".panel"));
    function show(id, push) {
      buttons.forEach(function (b) { b.setAttribute("aria-selected", b.dataset.panel === id ? "true" : "false"); });
      panels.forEach(function (p) { p.hidden = p.id !== id; });
      if (push && history.replaceState) history.replaceState(null, "", "#" + id);
    }
    buttons.forEach(function (b) { b.addEventListener("click", function () { show(b.dataset.panel, true); }); });
    var initial = location.hash.replace("#", "");
    // The Experiments tab moved to the Lab. Old links still land somewhere real.
    if (initial === "experiments") { location.replace("/lab#experiments"); return; }
    show(panels.some(function (p) { return p.id === initial; }) ? initial : buttons[0].dataset.panel, false);
  }

  // Tour Engine: loaded only when asked for, or when a tour is already under way
  // (the engine keeps its place in sessionStorage across a page load).
  var tourQueue = null, launcher = null;
  function loadTour(then) {
    if (window.Tour) { if (then) then(); return; }
    if (tourQueue) { if (then) tourQueue.push(then); return; }
    tourQueue = then ? [then] : [];
    var host = document.createElement("script");
    host.src = "/assets/tour/tour-host.js";
    host.onload = function () {
      var engine = document.createElement("script");
      engine.src = "/assets/tour/tour.js";
      engine.setAttribute("data-tour-host", "");
      engine.onload = function () { tourQueue.forEach(function (f) { f(); }); watchTour(); };
      document.body.appendChild(engine);
    };
    document.body.appendChild(host);
  }
  // The engine hands focus back to its own trigger, which this site hides, so
  // focus goes back to the button that started the tour instead.
  function watchTour() {
    var wasActive = false;
    setInterval(function () {
      var on = window.Tour && Tour.state().active;
      if (wasActive && !on && launcher && document.activeElement === document.body) launcher.focus();
      wasActive = on;
    }, 400);
  }
  document.querySelectorAll("[data-tour-start]").forEach(function (b) {
    b.addEventListener("click", function () {
      launcher = b;
      loadTour(function () { Tour.start(); });
    });
  });
  try { if (sessionStorage.getItem("tour.resume")) loadTour(); } catch (e) { /* storage blocked: no resume */ }

  // Copy buttons. Markup: button.copy-btn[data-copy]
  document.querySelectorAll(".copy-btn").forEach(function (b) {
    b.addEventListener("click", function () {
      var text = b.dataset.copy;
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(text).then(function () {
        var was = b.textContent;
        b.textContent = "Copied";
        setTimeout(function () { b.textContent = was; }, 1400);
      });
    });
  });
})();
