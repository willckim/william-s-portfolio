// williamckim.com · motion layer
// GSAP (ScrollTrigger, SplitText) and Lenis arrive as pinned CDN scripts before this
// one. Everything here is enhancement: the pages are complete without it, and under
// prefers-reduced-motion none of it runs. gsap.matchMedia reverts every tween and
// ScrollTrigger made inside it if the setting changes mid-visit.
(function () {
  "use strict";
  var M = window.__motion = { on: false, lenis: null };
  if (!window.gsap || !window.ScrollTrigger) return;   // a CDN miss leaves the calm site
  gsap.registerPlugin(ScrollTrigger);
  if (window.SplitText) gsap.registerPlugin(SplitText);

  var undo = [];   // teardown for what gsap.matchMedia cannot revert itself (DOM, listeners)
  function listen(el, type, fn, opts) {
    el.addEventListener(type, fn, opts);
    undo.push(function () { el.removeEventListener(type, fn, opts); });
  }
  var finePointer = matchMedia("(hover: hover) and (pointer: fine)");
  var mm = gsap.matchMedia();
  mm.add("(prefers-reduced-motion: no-preference)", function () {
    M.on = true;
    document.documentElement.classList.add("motion");

    // Smooth wheel scrolling only. Touch keeps native scrolling (syncTouch off), and
    // anchor links stay native so a jump also moves keyboard focus.
    var lenis = null, tick = null;
    if (window.Lenis) {
      lenis = new Lenis({ autoRaf: false, anchors: false });
      lenis.on("scroll", ScrollTrigger.update);
      tick = function (time) { lenis.raf(time * 1000); };
      gsap.ticker.add(tick);
      gsap.ticker.lagSmoothing(0);
    }
    M.lenis = lenis;
    if (lenis) anchors(lenis);

    heroReveal();
    story();
    titles();
    diagrams();
    sections();
    cursor();
    magnetic();
    transitions();

    return function () {
      while (undo.length) undo.pop()();
      M.on = false;
      document.documentElement.classList.remove("motion");
      if (tick) gsap.ticker.remove(tick);
      if (lenis) lenis.destroy();
      M.lenis = null;
    };
  });

  // In-page links (Skip to content, the Lab's jump links, Skip the story) glide there
  // with Lenis. The page's own CSS smooth scrolling is off while Lenis drives, because
  // two smoothers fight over any programmatic scroll (the tour's, the palette's). Like
  // a native jump, keyboard focus moves on to the target, so the next Tab starts there.
  function anchors(lenis) {
    function click(e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var a = e.target.closest && e.target.closest('a[href^="#"]');
      var id = a && decodeURIComponent(a.getAttribute("href").slice(1));
      var t = id && document.getElementById(id);
      if (!t) return;
      e.preventDefault();
      history.pushState(null, "", "#" + id);
      // Measured from layout, net of any reveal transform the target is still carrying.
      var margin = parseFloat(getComputedStyle(t).scrollMarginTop) || 0;
      var y = t.getBoundingClientRect().top + window.scrollY - (parseFloat(gsap.getProperty(t, "y")) || 0) - margin;
      lenis.scrollTo(Math.max(0, y), { duration: 0.9 });
      if (!t.hasAttribute("tabindex") && !t.matches("a[href], button, input, select, textarea")) {
        t.setAttribute("tabindex", "-1");
        t.setAttribute("data-anchor-target", "");
      }
      t.focus({ preventScroll: true });
    }
    document.addEventListener("click", click);
    undo.push(function () { document.removeEventListener("click", click); });
  }

  // Home headline: split into lines and revealed line by line from under a mask, when
  // the intro wipes away, or at once on a later visit. The headline is real text that
  // painted first, so a reveal only ever runs where the words are already covered: under
  // the intro, or held back by html.hl-pending (whose CSS failsafe shows them at 1.2 s;
  // after that the reveal is skipped rather than hiding text a person can already see).
  function heroReveal() {
    var d = document.documentElement;
    var copy = document.querySelector(".hero .copy"), h1 = copy && copy.querySelector("h1");
    var intro = d.classList.contains("intro-on"), pending = d.classList.contains("hl-pending");
    if (!h1 || !window.SplitText || !(intro || pending) || (pending && performance.now() > 1100)) {
      d.classList.remove("hl-pending");
      return;
    }
    var rest = copy.querySelectorAll(".status, .lede, .btn-row");
    var started = false, lines = null;
    SplitText.create(h1, {
      type: "lines", mask: "lines", linesClass: "hl-line", autoSplit: true,
      onSplit: function (self) {
        lines = gsap.from(self.lines, { yPercent: 118, duration: 1.05, ease: "expo.out", stagger: 0.09, paused: !started });
        return lines;
      }
    });
    gsap.set(rest, { opacity: 0, y: 14 });   // opacity, not visibility: the buttons stay focusable
    d.classList.remove("hl-pending");
    var reveal = null;
    function go() {
      if (started) return;
      started = true;
      if (lines) lines.play();
      reveal = gsap.to(rest, { opacity: 1, y: 0, duration: 0.8, ease: "power3.out", stagger: 0.07, delay: 0.3,
                               clearProps: "opacity,visibility,transform" });
    }
    // Focus arriving before the reveal has played (a quick Tab after Skip) finishes it.
    listen(copy, "focusin", function () {
      go();
      if (lines) lines.progress(1);
      reveal.progress(1);
    }, { once: true });
    if (intro && !window.__introDone) document.addEventListener("intro:done", go, { once: true }); else go();
  }

  // Home story. The scroll scrubs one number, window.__story.stage, that the particle
  // scene reads: each chapter's data-stage is the shape it shows when centred on
  // screen, with a hold around each centre so a shape is readable before it moves on.
  // Nothing is pinned. The captions reveal once, as they arrive.
  function story() {
    var story = document.getElementById("story"), cine = document.getElementById("cine");
    if (!story || !cine) return;
    var S = window.__story = { stage: 0 };
    var anchors = [[0, 0]];
    // [scroll position, stage] for each shape a chapter shows, centred on screen.
    function centres(ch) {
      var st = ch.getAttribute("data-stage").split(" ").map(Number);
      var top = ch.getBoundingClientRect().top + window.scrollY, h = ch.offsetHeight, vh = window.innerHeight;
      return st.map(function (v, k) {
        return [top + h * (st.length === 1 ? 0.5 : (k + 0.5) / st.length) - vh / 2, v];
      });
    }
    function measure() {
      var list = [[0, 0]];
      story.querySelectorAll(".chapter").forEach(function (ch) { list = list.concat(centres(ch)); });
      anchors = list;
    }
    // Where a chapter's first shape is fully formed. The site tour lands here.
    S.anchorOf = function (ch) { return Math.max(0, centres(ch)[0][0]); };
    function stageAt(y) {
      for (var i = 1; i < anchors.length; i++) {
        var a = anchors[i - 1], b = anchors[i];
        if (y <= b[0]) {
          var u = Math.max(0, Math.min(1, (y - a[0]) / Math.max(1, b[0] - a[0])));
          u = u < 0.2 ? 0 : u > 0.8 ? 1 : (u - 0.2) / 0.6;
          return a[1] + (b[1] - a[1]) * u * u * (3 - 2 * u);
        }
      }
      return anchors[anchors.length - 1][1];
    }
    var proxy = { p: 0 };
    var tween = gsap.to(proxy, {
      p: 1, ease: "none",
      scrollTrigger: { trigger: cine, start: "top top", end: "bottom bottom", scrub: true, onRefresh: measure },
      onUpdate: function () {
        var st = tween.scrollTrigger;
        if (!st) return;   // mid-revert (reduced motion switched on): the trigger is already gone
        S.stage = stageAt(st.start + proxy.p * (st.end - st.start));
      }
    });
    measure();
    S.stage = stageAt(window.scrollY);

    story.querySelectorAll(".ch-card").forEach(function (card) {
      var title = card.querySelector(".ch-title");
      var parts = card.querySelectorAll(".ch-n, .ch-big, .ch-label, .ch-go, .ch-mark, .btn-row");
      var tl = gsap.timeline({ scrollTrigger: { trigger: card, start: "top 88%", once: true } });
      // Opacity only, never visibility: a hidden link could not take keyboard focus.
      // Focus arriving before the reveal finishes it at once.
      tl.from(card, { opacity: 0, y: 30, duration: 0.7, ease: "power3.out" }, 0);
      listen(card, "focusin", function () { finish(tl); });
      if (title && window.SplitText) {
        var split = SplitText.create(title, { type: "lines", mask: "lines", linesClass: "ch-line" });
        tl.from(split.lines, { yPercent: 115, duration: 0.9, ease: "expo.out", stagger: 0.08 }, 0.05);
        tl.eventCallback("onComplete", function () { split.revert(); });   // lines re-flow freely after
      }
      tl.from(parts, { opacity: 0, y: 16, duration: 0.6, ease: "power3.out", stagger: 0.06 }, 0.15);
    });
  }

  // Focus arriving before a reveal has played finishes it on the spot. The trigger is
  // retired first with allowAnimation set, or kill() would take the tween with it and
  // leave the section frozen invisible.
  function finish(anim) {
    if (anim.progress() === 1) return;
    if (anim.scrollTrigger) anim.scrollTrigger.kill(false, true);
    anim.progress(1);
  }

  // Is the element already on screen at load? Then it is left alone: a reveal only
  // plays on something arriving, never on words a person may already be reading.
  function inView(el) {
    var r = el.getBoundingClientRect();
    return r.top < window.innerHeight && r.bottom > 0;
  }

  // Section titles: split into lines and raised from under a mask as they arrive.
  function titles() {
    var TITLES = {
      case: ".ledger > aside h2",
      about: ".ledger > aside h2",
      lab: ".lab-head h2"
    };
    if (!window.SplitText) return;
    var page = document.body.getAttribute("data-page") || "";
    var sel = TITLES[page.indexOf("case-") === 0 ? "case" : page];
    if (!sel) return;
    document.querySelectorAll(sel).forEach(function (h) {
      if (inView(h)) return;
      var split = SplitText.create(h, { type: "lines", mask: "lines", linesClass: "t-line" });
      gsap.from(split.lines, {
        yPercent: 110, duration: 0.8, ease: "expo.out", stagger: 0.08,
        scrollTrigger: { trigger: h, start: "top 88%", once: true },
        onComplete: function () { split.revert(); }
      });
    });
  }

  // Case study diagrams draw themselves: outlines and arrows trace in, the colour bars
  // grow, the arrowheads land, stage by stage. The words are never faded or moved,
  // so the diagram reads at every moment, and afterwards every style is cleared back
  // to the stylesheet's.
  function diagrams() {
    document.querySelectorAll("svg.diagram").forEach(function (svg) {
      var strokes = Array.prototype.slice.call(svg.querySelectorAll(".dg-box, .dg-arrow"));
      var bars = svg.querySelectorAll(".dg-bar"), heads = svg.querySelectorAll(".dg-head, .dg-group");
      var tl = gsap.timeline({
        scrollTrigger: { trigger: svg, start: "top 82%", once: true },
        onComplete: function () {
          strokes.concat([].slice.call(bars), [].slice.call(heads)).forEach(function (el) {
            gsap.killTweensOf(el);
            el.removeAttribute("style");   // clearProps leaves an SVG transform-origin behind
          });
        }
      });
      strokes.forEach(function (el, i) {
        var len = el.getTotalLength ? Math.ceil(el.getTotalLength()) : 0;
        if (!len) return;
        tl.fromTo(el, { strokeDasharray: len, strokeDashoffset: len },
                  { strokeDashoffset: 0, duration: 0.55, ease: "power2.inOut" }, i * 0.12);
      });
      tl.from(bars, { scaleY: 0, transformOrigin: "50% 0%", duration: 0.4, ease: "power2.out", stagger: 0.14 }, 0.1);
      tl.from(heads, { opacity: 0, duration: 0.3, stagger: 0.14 }, 0.3);
    });
  }

  // About and Lab: each section fades in from a soft blur as it arrives. Opacity, never
  // visibility, so everything stays focusable, and focus landing inside finishes it.
  function sections() {
    var page = document.body.getAttribute("data-page");
    var sel = { about: "main .ledger", lab: "main .lab-panel" }[page];
    if (!sel) return;
    document.querySelectorAll(sel).forEach(function (sec) {
      if (inView(sec)) return;
      // Fade and focus in place, never a move: the Lab's tools sit in these sections, and
      // content sliding between a pointer's down and up turns a click into a miss.
      var tw = gsap.from(sec, {
        opacity: 0, filter: "blur(8px)", duration: 0.8, ease: "power2.out", clearProps: "opacity,filter",
        scrollTrigger: { trigger: sec, start: "top 90%", once: true }
      });
      listen(sec, "focusin", function () { finish(tw); });
    });
  }

  // Custom cursor, for a mouse only: a small dot that grows over links and shows a
  // label ("View") over projects. It never takes pointer events, hides the moment a
  // key is pressed so it can never sit over a focus ring, and steps aside for form
  // controls, dialogs and the tour, where the system cursor comes back.
  function cursor() {
    if (!finePointer.matches) return;
    var d = document.documentElement, dot = document.createElement("div"), label = document.createElement("span");
    dot.className = "cursor is-hidden";
    dot.setAttribute("aria-hidden", "true");
    label.className = "cursor-label";
    dot.appendChild(label);
    document.body.appendChild(dot);
    d.classList.add("has-cursor");
    var xTo = gsap.quickTo(dot, "x", { duration: 0.14, ease: "power3" });
    var yTo = gsap.quickTo(dot, "y", { duration: 0.14, ease: "power3" });
    var LINKY = "a[href], button, [role=tab], summary, label[for]";
    var NATIVE = "input, select, textarea, dialog, [data-tour-ui]";
    function move(e) {
      if (e.pointerType && e.pointerType !== "mouse") return hide();   // a touch on a hybrid laptop
      if (dot.classList.contains("is-hidden")) gsap.set(dot, { x: e.clientX, y: e.clientY });
      xTo(e.clientX); yTo(e.clientY);
      var t = e.target && e.target.closest ? e.target : null;
      var native = t && t.closest(NATIVE), link = !native && t && t.closest(LINKY);
      var text = link && (link.getAttribute("data-cursor") || (link.closest(".proof") ? "View" : ""));
      dot.classList.toggle("is-hidden", !!native);
      dot.classList.toggle("is-link", !!link && !text);
      dot.classList.toggle("is-label", !!text);
      if (text) label.textContent = text;
    }
    function hide() { dot.classList.add("is-hidden"); }
    listen(window, "pointermove", move, { passive: true });
    listen(window, "pointerdown", move, { passive: true });
    listen(window, "keydown", hide);
    listen(d, "mouseleave", hide);
    undo.push(function () {
      d.classList.remove("has-cursor");
      dot.remove();
    });
  }

  // Primary buttons lean a little toward the pointer, and spring back when it leaves.
  function magnetic() {
    if (!finePointer.matches) return;
    document.querySelectorAll(".btn.primary").forEach(function (b) {
      var xTo = gsap.quickTo(b, "x", { duration: 0.4, ease: "power3" });
      var yTo = gsap.quickTo(b, "y", { duration: 0.4, ease: "power3" });
      function move(e) {
        var r = b.getBoundingClientRect(), x = gsap.getProperty(b, "x"), y = gsap.getProperty(b, "y");
        xTo((e.clientX - (r.left - x + r.width / 2)) * 0.3);
        yTo((e.clientY - (r.top - y + r.height / 2)) * 0.4);
      }
      function leave() { gsap.to(b, { x: 0, y: 0, duration: 0.7, ease: "elastic.out(1, 0.4)" }); }
      b.addEventListener("pointermove", move);
      b.addEventListener("pointerleave", leave);
      undo.push(function () {
        b.removeEventListener("pointermove", move);
        b.removeEventListener("pointerleave", leave);
        gsap.set(b, { clearProps: "transform" });
      });
    });
  }

  // Page transitions. Where the browser does cross-document View Transitions, the CSS
  // in style.css runs a ledger-line wipe and this does nothing. Elsewhere the same wipe
  // is played on an overlay before leaving: the page is covered left to right behind
  // a moving green line, then the next page loads.
  function transitions() {
    if ("onpagereveal" in window && !window.__noViewTransitions) return;
    var wipe = document.createElement("div"), line = document.createElement("div");
    wipe.className = "page-wipe";
    wipe.setAttribute("aria-hidden", "true");
    line.className = "page-wipe-line";
    wipe.appendChild(line);
    document.body.appendChild(wipe);
    function set(p) {
      wipe.style.clipPath = "inset(0 " + ((1 - p) * 100).toFixed(2) + "% 0 0)";
      line.style.transform = "translateX(" + (p * window.innerWidth).toFixed(1) + "px)";
      wipe.style.visibility = p > 0 ? "visible" : "hidden";
    }
    set(0);
    function click(e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var a = e.target.closest && e.target.closest("a[href]");
      if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download")) return;
      var url = new URL(a.href, location.href);
      if (url.origin !== location.origin || /\.pdf$/i.test(url.pathname) ||
          (url.pathname === location.pathname && url.search === location.search)) return;
      e.preventDefault();
      var st = { p: 0 };
      M.leaving = url.href;
      gsap.to(st, { p: 1, duration: 0.42, ease: "power3.inOut", onUpdate: function () { set(st.p); },
                    onComplete: function () { location.href = url.href; } });
    }
    function shown(e) { if (e.persisted) set(0); }   // back to a page from the cache: uncovered
    document.addEventListener("click", click);
    window.addEventListener("pageshow", shown);
    undo.push(function () {
      document.removeEventListener("click", click);
      window.removeEventListener("pageshow", shown);
      wipe.remove();
    });
  }
})();
