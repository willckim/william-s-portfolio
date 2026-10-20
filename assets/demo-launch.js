// Click-to-launch for the 3D demos on /work/quote-engine and /work/apartment-studio.
// Until "Launch the demo" is pressed the page loads nothing from /demos/, so it stays
// fast: no three.js, no jsPDF, no frame. tests/check_demos.py holds the page to that.
(function () {
  "use strict";
  var section = document.querySelector("[data-demo]");
  if (!section) return;
  var button = section.querySelector("[data-demo-launch]");
  var stage = section.querySelector(".demo-stage");
  var status = document.createElement("p");
  status.className = "demo-status";
  status.setAttribute("role", "status");
  section.insertBefore(status, stage.nextSibling);

  // A failed load puts the poster and the button back, so the visitor can try again.
  function restore(live, message) {
    live.replaceWith(stage);
    status.textContent = message;
    button.focus();
  }

  function holder(className, label) {
    var live = document.createElement("div");
    live.className = "demo-live " + className;
    live.setAttribute("role", "region");
    live.setAttribute("aria-label", label);
    live.tabIndex = -1;
    return live;
  }

  // The Quote Engine starts the way a contractor's site would: its 2-line embed snippet.
  function quoteEngine() {
    var live = holder("demo-widget", "3D Quote Engine demo");
    var el = document.createElement("custom-quote-builder");
    el.setAttribute("demo-mode", "");
    live.appendChild(el);
    var script = document.createElement("script");
    script.src = "/demos/quote-engine/quote-builder-embed.js";
    script.onload = function () { status.textContent = "The demo is ready."; };
    script.onerror = function () {
      script.remove();
      restore(live, "The demo could not load. Check your connection and try again.");
    };
    stage.replaceWith(live);
    live.focus();
    document.body.appendChild(script);
  }

  // The apartment studio runs in a frame. Phones get the lighter quality setting.
  function apartment() {
    var phone = matchMedia("(pointer: coarse)").matches || Math.min(screen.width, screen.height) < 700;
    var src = "/demos/lakeview" + (phone ? "?quality=low" : "");
    var bar = document.createElement("div");
    bar.className = "demo-bar";
    var live = holder("demo-frame", "Apartment Walkthrough Studio demo");
    if (document.fullscreenEnabled && live.requestFullscreen) {
      var full = document.createElement("button");
      full.type = "button";
      full.className = "btn";
      full.textContent = "Full screen";
      full.addEventListener("click", function () {
        live.requestFullscreen().catch(function () { status.textContent = "Full screen is not available here."; });
      });
      bar.appendChild(full);
    }
    var tab = document.createElement("a");
    tab.className = "btn";
    tab.href = src;
    tab.target = "_blank";
    tab.rel = "noopener";
    tab.textContent = "Open in its own tab";
    bar.appendChild(tab);
    var frame = document.createElement("iframe");
    frame.src = src;
    frame.title = "Apartment Walkthrough Studio, The Lakeview One-Bedroom";
    frame.allow = "fullscreen";
    frame.setAttribute("allowfullscreen", "");
    frame.addEventListener("load", function () { status.textContent = "The demo is loading its 3D assets."; });
    live.appendChild(frame);
    // The controls come before the frame, so a keyboard user reaches them without tabbing through the studio.
    stage.replaceWith(bar);
    bar.after(live);
    frame.focus();
  }

  button.addEventListener("click", function () {
    status.textContent = "Loading the demo.";
    if (section.getAttribute("data-demo") === "quote-engine") quoteEngine();
    else apartment();
  });
})();
