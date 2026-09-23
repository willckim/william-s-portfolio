// Command palette: Cmd/Ctrl+K, or the Search button in the header.
// Loaded by site.js on first use. A modal <dialog> keeps the rest of the page inert,
// Tab is held on the search field, Escape closes, and focus returns to the opener.
// The input is a combobox over a listbox, so the highlighted result is announced.
(function () {
  "use strict";

  // Every page, case study, Lab tool and the résumé. tests/check_palette.py fails if
  // a deployed page is missing here or an entry does not resolve.
  var INDEX = [
    ["Pages", "Home", "/", "start overview proof results now"],
    ["Pages", "Work", "/work", "ledger ortho products production systems"],
    ["Pages", "Lab", "/lab", "tools interactive experiments"],
    ["Pages", "About", "/about", "profile timeline skills certifications how i work principles"],
    ["Pages", "Contact", "/contact", "email linkedin github hire open to roles"],
    ["Case studies", "Concur Automation", "/work/concur", "llm openai classifier guardrails expense card transactions"],
    ["Case studies", "Royalty Calculation Pipeline", "/work/royalty", "rate logic validation excel pivot"],
    ["Case studies", "Fast Close Report Fix", "/work/fast-close", "sql bi report defect close"],
    ["Case studies", "Accounting Time Tracker", "/work/time-tracker", "timekeeping approval audit trail azure function"],
    ["Case studies", "Practitioner Website Consolidation", "/work/consolidation", "platform specification prototype tax w-9 tin erp"],
    ["Lab tools", "Tour Engine: tour this site", "/lab#tour", "walkthrough guided spotlight host adapter mutation testing"],
    ["Lab tools", "Mosca's inequality calculator", "/lab#pqc", "post-quantum pqc readiness harvest now decrypt later retention exposure"],
    ["Lab tools", "Grover search visualizer", "/lab#grover", "quantum amplitude iterations qiskit"],
    ["Lab tools", "Quantum finance results", "/lab#quantum", "qaoa portfolio monte carlo amplitude estimation forecaster"],
    ["Lab tools", "More experiments", "/lab#experiments", "fp&a dashboard snowflake power bi"],
    ["Lab tools", "Prompting Copilot for accounting", "/copilot", "microsoft 365 copilot guide guardrail card"],
    ["Résumé", "Résumé (PDF)", "/resume.pdf", "resume cv pdf download"]
  ].map(function (r, i) { return { group: r[0], title: r[1], url: r[2], hay: (r[1] + " " + r[3]).toLowerCase(), id: "pal-" + i }; });

  var dlg, input, list, opener = null, shown = [], active = 0;

  function build() {
    dlg = document.createElement("dialog");
    dlg.className = "palette";
    dlg.setAttribute("aria-label", "Search the site");
    dlg.innerHTML =
      '<div class="pal-field"><label class="sr-only" for="pal-q">Search pages, case studies and Lab tools</label>' +
      '<input id="pal-q" type="text" role="combobox" aria-expanded="true" aria-controls="pal-list" ' +
      'aria-autocomplete="list" autocomplete="off" spellcheck="false" placeholder="Search pages, case studies, Lab tools">' +
      '<kbd>Esc</kbd></div><ul id="pal-list" role="listbox" aria-label="Results"></ul>' +
      '<p class="pal-empty" hidden>No match. Try "quantum", "concur" or "résumé".</p>';
    document.body.appendChild(dlg);
    input = dlg.querySelector("input");
    list = dlg.querySelector("ul");
    input.addEventListener("input", function () { active = 0; render(); });
    input.addEventListener("keydown", onKey);
    dlg.addEventListener("keydown", function (e) {
      if (e.key === "Tab") { e.preventDefault(); input.focus(); }   // the only stop in the trap
    });
    dlg.addEventListener("close", function () { if (opener) opener.focus(); });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });  // backdrop
    list.addEventListener("click", function (e) {
      var li = e.target.closest("[role=option]");
      if (li) go(shown[+li.dataset.i]);
    });
    list.addEventListener("mousemove", function (e) {
      var li = e.target.closest("[role=option]");
      if (li && +li.dataset.i !== active) { active = +li.dataset.i; mark(); }
    });
  }

  function score(item, words) {
    var s = 0;
    for (var i = 0; i < words.length; i++) {
      var at = item.hay.indexOf(words[i]);
      if (at < 0) return -1;
      s += at === 0 ? 3 : item.title.toLowerCase().indexOf(words[i]) >= 0 ? 2 : 1;
    }
    return s;
  }

  function render() {
    var words = input.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
    shown = INDEX.map(function (it, i) { return { it: it, s: words.length ? score(it, words) : 0, i: i }; })
      .filter(function (r) { return r.s >= 0; })
      .sort(function (a, b) { return b.s - a.s || a.i - b.i; })
      .map(function (r) { return r.it; });
    list.textContent = "";
    var lastGroup = null;
    shown.forEach(function (it, i) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      li.id = it.id;
      li.dataset.i = String(i);
      li.dataset.url = it.url;
      var t = document.createElement("span");
      t.className = "pal-title";
      t.textContent = it.title;
      var g = document.createElement("span");
      g.className = "pal-group";
      g.textContent = it.group;
      li.appendChild(t);
      if (it.group !== lastGroup || words.length) li.appendChild(g);
      lastGroup = it.group;
      list.appendChild(li);
    });
    dlg.querySelector(".pal-empty").hidden = shown.length > 0;
    input.setAttribute("aria-expanded", shown.length ? "true" : "false");
    mark();
  }

  function mark() {
    var items = list.children;
    for (var i = 0; i < items.length; i++) items[i].setAttribute("aria-selected", i === active ? "true" : "false");
    if (items[active]) {
      input.setAttribute("aria-activedescendant", items[active].id);
      items[active].scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function onKey(e) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!shown.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length;
      mark();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (shown[active]) go(shown[active]);
    }
  }

  function go(it) {
    var here = location.pathname + location.hash;
    dlg.close();
    if (it.url === here) return;
    location.href = it.url;
  }

  window.Palette = {
    open: function (from) {
      if (!dlg) build();
      if (dlg.open) return;
      opener = from || document.activeElement;
      input.value = "";
      active = 0;
      render();
      dlg.showModal();
      input.focus();
    }
  };
})();
