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
    show(panels.some(function (p) { return p.id === initial; }) ? initial : buttons[0].dataset.panel, false);
  }

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
