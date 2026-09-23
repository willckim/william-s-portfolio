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
      buttons.forEach(function (b) {
        var on = b.dataset.panel === id;
        b.setAttribute("aria-selected", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;             // roving tabindex: Tab reaches the selected tab only
      });
      panels.forEach(function (p) { p.hidden = p.id !== id; });
      if (push && history.replaceState) history.replaceState(null, "", "#" + id);
    }
    buttons.forEach(function (b, i) {
      b.addEventListener("click", function () { show(b.dataset.panel, true); });
      // Arrow keys, Home and End move between tabs, as the ARIA tabs pattern expects.
      b.addEventListener("keydown", function (e) {
        var to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: buttons.length - 1 }[e.key];
        if (to === undefined) return;
        e.preventDefault();
        var next = buttons[(to + buttons.length) % buttons.length];
        show(next.dataset.panel, true);
        next.focus();
      });
    });
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

  // Theme. The head script already applied a stored choice before paint. This keeps
  // the toggle, the browser's theme-color and the hero in step with it, and follows
  // the system setting live for anyone who has not chosen.
  var docEl = document.documentElement;
  var darkMq = window.matchMedia("(prefers-color-scheme: dark)");
  function resolvedTheme() { return docEl.getAttribute("data-theme") || (darkMq.matches ? "dark" : "light"); }
  function syncTheme() {
    var t = resolvedTheme();
    docEl.setAttribute("data-theme-resolved", t);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", getComputedStyle(docEl).getPropertyValue("--bone").trim());
    var btn = document.querySelector("[data-theme-toggle]");
    if (btn) btn.setAttribute("aria-pressed", t === "dark" ? "true" : "false");
    document.dispatchEvent(new CustomEvent("themechange", { detail: t }));
  }
  var themeBtn = document.querySelector("[data-theme-toggle]");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = resolvedTheme() === "dark" ? "light" : "dark";
      docEl.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) { /* not remembered, still applied */ }
      syncTheme();
    });
  }
  darkMq.addEventListener("change", function () { if (!docEl.getAttribute("data-theme")) syncTheme(); });
  syncTheme();

  // Command palette: Cmd/Ctrl+K anywhere, or the header's Search button. The script
  // loads on first use, so pages that never search never pay for it.
  var paletteLoading = false;
  function openPalette(from) {
    if (window.Palette) return Palette.open(from);
    if (paletteLoading) return;
    paletteLoading = true;
    var s = document.createElement("script");
    s.src = "/assets/palette.js";
    s.onload = function () { Palette.open(from); };
    document.head.appendChild(s);
  }
  var searchBtn = document.querySelector("[data-palette-open]");
  if (searchBtn) {
    if (/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)) {
      searchBtn.querySelector("kbd").textContent = "⌘K";
    }
    searchBtn.addEventListener("click", function () { openPalette(searchBtn); });
  }
  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      openPalette(document.activeElement);
    }
  });

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
