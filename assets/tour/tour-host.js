// williamckim.com · Tour Engine host adapter
//
// The engine knows nothing about this site. Everything it needs comes through
// window.TourHost, set here before the engine loads. The one idea: each PAGE is a
// "tab". tabs.current() names the page from <body data-page>, and tabs.button()
// names the link that opens a page. When a step lives on another page, the engine
// inserts its own "open this tab" step pointing at that link, saves its place in
// sessionStorage, and picks the tour up again on the next page. No engine change.
//
// Loaded on demand by site.js, only when a tour is started or already under way.
(function () {
  "use strict";

  // The link that opens each page, on the pages where it exists. A case study opens
  // from its row in the Work ledger, so that link only exists on /work.
  var LINKS = {
    home: '#nav a[href="/"]',
    work: '#nav a[href="/work"]',
    lab: '#nav a[href="/lab"]',
    contact: '#nav a[href="/contact"]',
    "case-concur": '#ortho a[href="/work/concur"]'
  };

  window.TourHost = {
    steps: [
      { tab: "home", kind: "region", advance: "next",
        target: [{ by: "id", value: "nav" }],
        title: "Five tabs, the whole site",
        body: "Home, Work, Lab, About and Contact. This tour visits the parts you can use, in about a minute.",
        targetName: "the site tabs", instruction: "Find the tabs at the top of the page" },
      { tab: "home", kind: "region", advance: "next",
        target: [{ by: "css", value: "section.proof" }],
        title: "Every number has a source",
        body: "Each figure links to the case study behind it. None of them is a number without its work shown.",
        targetName: "the row of results", instruction: "Find the four results under the header" },
      { tab: "work", kind: "region", advance: "next",
        target: [{ by: "css", value: "#ortho table.book" }],
        title: "Five systems, five case studies",
        body: "What runs in production at Ortho. Each name opens a one-page case study with a diagram of how it works.",
        targetName: "the Ortho ledger", instruction: "Find the At Ortho table" },
      { tab: "case-concur", kind: "region", advance: "next",
        target: [{ by: "css", value: "figure.diagram-wrap" }],
        title: "The model suggests, a person decides",
        body: "The Concur classifier's answer passes deterministic rules, then human review, and only a person posts.",
        targetName: "the architecture diagram", instruction: "Find the diagram under How it works" },
      { tab: "lab", advance: "click",
        target: [{ by: "css", value: 'button[data-preset="Optimistic"]' }],
        title: "Try the calculator",
        body: "Press Optimistic, the toolkit's latest arrival window for a quantum computer that can break RSA, and watch the table change.",
        targetName: "the Optimistic scenario button", instruction: "Press the Optimistic scenario" },
      { tab: "lab", kind: "region", advance: "next",
        target: [{ by: "id", value: "m-table" }],
        title: "Which records are exposed",
        body: "The table recomputes in your browser. Move the sliders above it to test your own migration plan.",
        targetName: "the exposure table", instruction: "Find the table of record types" },
      { tab: "contact", kind: "region", advance: "next",
        target: [{ by: "css", value: ".contact-list" }],
        title: "That is the tour",
        body: "Email is the fastest way to reach me. Thanks for taking the time.",
        targetName: "the contact details", instruction: "Find the email address" }
    ],
    isReady: function () { return document.readyState !== "loading"; },
    tabs: {
      current: function () { return document.body.getAttribute("data-page"); },
      button: function (name) {
        var sel = LINKS[name];
        return sel && document.querySelector(sel) ? sel : null;
      }
    },
    // On a phone the tabs fold behind Menu. The engine asks before pointing at
    // something folded away, and guides the person to open it rather than doing it.
    collapsedToggle: function (el) {
      var nav = document.getElementById("nav");
      if (!nav || !(nav === el || nav.contains(el))) return null;
      return getComputedStyle(nav).display === "none" ? ".menu-btn" : null;
    },
    timeouts: { firstTargetMs: 8000, targetMs: 4000 }
  };
})();
