// williamckim.com · Tour Engine host adapter
//
// The engine knows nothing about this site. Everything it needs comes through
// window.TourHost, set here before the engine loads. The one idea: each PAGE is a
// "tab". tabs.current() names the page from <body data-page>, and tabs.button()
// names the link that opens a page. When a step lives on another page, the engine
// inserts its own "open this tab" step pointing at that link, saves its place in
// sessionStorage, and picks the tour up again on the next page. No engine change.
//
// The rest of this file fits the engine to the motion layer (assets/motion.js):
// the preloader, Lenis, the scroll story, the page wipe and the custom cursor.
// With reduced motion none of those run, and the tour uses plain scrolling.
//
// Loaded on demand by site.js, only when a tour is started or already under way.
(function () {
  "use strict";

  var root = document.documentElement;

  // The link that opens each page, on the pages where it exists. A case study opens
  // from its name in the Work index, so that link only exists on /work. Names, not
  // rows: a row's hover preview is never something a step depends on.
  var LINKS = {
    home: '#nav a[href="/"]',
    work: '#nav a[href="/work"]',
    lab: '#nav a[href="/lab"]',
    contact: '#nav a[href="/contact"]',
    "case-concur": '#ortho .ix-link[href="/work/concur"] .ix-name'
  };

  function running() { return !!(window.Tour && Tour.state().active); }
  function motion() { return window.__motion || {}; }

  // ── Readiness ───────────────────────────────────────────────────────────────
  // Not ready while the preloader is up, or while a ledger-line view transition is
  // still wiping the page in, so the first target is looked for on the settled page.
  // Neither can begin mid-tour: both happen only as a page arrives, before any
  // resume, so this never ends a running tour (the engine ends one that turns
  // unready).
  function wiping() {
    if (!document.getAnimations) return false;
    return document.getAnimations().some(function (a) {
      var p = a.effect && a.effect.pseudoElement;
      return !!p && p.indexOf("::view-transition") === 0 && a.playState === "running";
    });
  }
  // A transition's animations only exist once the new page's first frame has begun,
  // so a readiness check made before that frame sees nothing wiping and passes too
  // early. Measured: the engine resumed at 328 ms, a millisecond after the page was
  // revealed, and its card rode in on a wipe that ran until 844 ms. Two frames in,
  // the wipe (if there is one) can be seen. A tour started by a click loads this
  // file long after the page has loaded, and needs no wait.
  var framed = document.readyState === "complete";
  requestAnimationFrame(function () { requestAnimationFrame(function () { framed = true; }); });
  function isReady() {
    return framed && document.readyState !== "loading" && !root.classList.contains("intro-on") && !wiping();
  }

  // ── Leaving the page ────────────────────────────────────────────────────────
  // A step that advances on a link click has already done its job when the page
  // starts to go. The engine then saves its place and draws the next card on the
  // page that is leaving. That card is hidden, so the wipe carries the old page
  // away clean and the next card is only ever drawn on the page it belongs to.
  function leaving(e) {
    if (!running() || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download")) return;
    var url = new URL(a.href, location.href);
    // The same test motion.js uses to decide a link leaves the page.
    if (url.origin !== location.origin || /\.pdf$/i.test(url.pathname) ||
        (url.pathname === location.pathname && url.search === location.search)) return;
    root.classList.add("tour-leaving");
    setTimeout(function () { root.classList.remove("tour-leaving"); }, 4000);   // a navigation that never happened
  }
  document.addEventListener("click", leaving, true);
  window.addEventListener("pageshow", function (e) { if (e.persisted) root.classList.remove("tour-leaving"); });

  // ── Scrolling ───────────────────────────────────────────────────────────────
  // The engine brings each target into view with the element's own scrollIntoView,
  // its one scroll call. While a tour runs and Lenis drives the page, that call is
  // answered by Lenis instead, so the two smoothers never fight over the page:
  //   - A target inside a story chapter lands on the chapter's own anchor, where its
  //     shape is fully formed, not merely centred.
  //   - lock: true pauses wheel and touch scrolling while the step animates, and
  //     Lenis lifts it the moment the scroll arrives.
  // Anything else (no tour, reduced motion, no Lenis) keeps the browser's own, and so
  // does anything inside [data-lenis-prevent], which scrolls itself: the command
  // palette's list, opened mid-tour, scrolled the page instead and locked it.
  var nativeScrollIntoView = Element.prototype.scrollIntoView;
  function landing(el) {
    var story = window.__story, ch = el.closest("#story .chapter");
    if (ch && story && story.anchorOf) return story.anchorOf(ch);
    var r = el.getBoundingClientRect();
    return Math.max(0, r.top + window.scrollY - (window.innerHeight - r.height) / 2);
  }
  Element.prototype.scrollIntoView = function () {
    var lenis = motion().on && motion().lenis;
    if (!lenis || !running() || this.closest("[data-tour-ui], [data-lenis-prevent]")) {
      return nativeScrollIntoView.apply(this, arguments);
    }
    lenis.scrollTo(landing(this), { lock: true, force: true, duration: 0.8 });
  };

  // The spotlight follows its target on every Lenis frame and on every ScrollTrigger
  // refresh (a resize, a font landing), not only at the engine's own quarter-second
  // tick. The engine listens for scroll on the document, so that is what it is told.
  function nudge() { if (running()) document.dispatchEvent(new Event("scroll")); }
  if (motion().lenis) motion().lenis.on("scroll", nudge);
  if (window.ScrollTrigger) ScrollTrigger.addEventListener("refresh", nudge);

  // ── While a tour runs ───────────────────────────────────────────────────────
  // html.tour-running hides the site's cursor dot, which would compete with the
  // tour's own ghost cursor, and gives the system cursor back. It is kept in step
  // with the engine's spotlight, which exists exactly while a tour does, so it is
  // undone however the tour ends: Done, Skip, Escape. Ending mid-scroll also lets
  // Lenis go at once rather than when the scroll would have arrived.
  function sync() {
    var on = !!document.querySelector('body > [data-tour-ui="spotlight"]');
    if (on === root.classList.contains("tour-running")) return;
    root.classList.toggle("tour-running", on);
    var lenis = motion().lenis;
    if (!on && lenis && lenis.isLocked) lenis.reset();
  }
  new MutationObserver(sync).observe(document.body, { childList: true });

  window.TourHost = {
    steps: [
      { tab: "home", kind: "region", advance: "next",
        target: [{ by: "css", value: ".hero .copy h1" }],
        title: "Who I am, in one line",
        body: "I close the books, then build the systems that close them faster.",
        targetName: "the headline", instruction: "Find the headline at the top of Home" },
      { tab: "home", kind: "region", advance: "next",
        target: [{ by: "css", value: '#story .chapter[data-stage="2"] .ch-card' }],
        title: "36h → 10m",
        body: "Monthly expense review, after a C#/.NET classifier on Azure Functions calling the OpenAI API with rule guardrails.",
        targetName: "the first number in the story", instruction: "Scroll to the first number in the story" },
      { tab: "home", kind: "region", advance: "next",
        target: [{ by: "css", value: ".site-header .quick-link" }],
        title: "Quick view",
        body: "Short on time? Here is the one-page version.",
        targetName: "the Quick view link", instruction: "Find Quick view in the header" },
      { tab: "home", advance: "click",
        target: [{ by: "css", value: '#nav a[href="/work"]' }],
        title: "See the work",
        body: "Open Work for the projects behind these numbers.",
        targetName: "the Work link", instruction: "Click Work" },
      { tab: "work", advance: "click",
        target: [{ by: "css", value: '#ortho .ix-link[href="/work/concur"] .ix-name' }],
        title: "Start with Concur",
        body: "The classifier behind 36h → 10m. Click its name to open the case study.",
        targetName: "the Concur project name", instruction: "Click Concur Automation" },
      { tab: "case-concur", kind: "region", advance: "next",
        target: [{ by: "css", value: "figure.diagram-wrap" }],
        title: "The guardrails",
        body: "The model never posts anything. Rules and a person check every result.",
        targetName: "the architecture diagram", instruction: "Find the diagram under How it works" },
      { tab: "lab", kind: "region", advance: "next",
        target: [{ by: "id", value: "mosca" }],
        title: "The Mosca calculator",
        body: "Try the calculator yourself.",
        targetName: "the Mosca calculator", instruction: "Find the calculator in the Lab" }
    ],
    isReady: isReady,
    tabs: {
      current: function () { return document.body.getAttribute("data-page"); },
      button: function (name) {
        var sel = LINKS[name];
        return sel && document.querySelector(sel) ? sel : null;
      }
    },
    // Folded away: on a phone the tabs fold behind Menu, and on /work a project can
    // sit in the tab panel that is not showing. The engine asks before pointing at
    // either, and guides the person to open it rather than doing it for them.
    collapsedToggle: function (el) {
      var nav = document.getElementById("nav");
      if (nav && (nav === el || nav.contains(el))) return getComputedStyle(nav).display === "none" ? ".menu-btn" : null;
      var panel = el.closest('[role="tabpanel"]');
      if (panel && panel.hidden && panel.getAttribute("aria-labelledby")) return "#" + panel.getAttribute("aria-labelledby");
      return null;
    },
    timeouts: { firstTargetMs: 8000, targetMs: 4000 }
  };
})();
