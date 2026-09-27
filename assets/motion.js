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

    heroReveal();
    story();

    return function () {
      M.on = false;
      document.documentElement.classList.remove("motion");
      if (tick) gsap.ticker.remove(tick);
      if (lenis) lenis.destroy();
      M.lenis = null;
    };
  });

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
    gsap.set(rest, { autoAlpha: 0, y: 14 });
    d.classList.remove("hl-pending");
    function go() {
      started = true;
      if (lines) lines.play();
      gsap.to(rest, { autoAlpha: 1, y: 0, duration: 0.8, ease: "power3.out", stagger: 0.07, delay: 0.3,
                      clearProps: "opacity,visibility,transform" });
    }
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
    function measure() {
      var vh = window.innerHeight, list = [[0, 0]];
      story.querySelectorAll(".chapter").forEach(function (ch) {
        var st = ch.getAttribute("data-stage").split(" ").map(Number);
        var top = ch.getBoundingClientRect().top + window.scrollY, h = ch.offsetHeight;
        st.forEach(function (v, k) {
          list.push([top + h * (st.length === 1 ? 0.5 : (k + 0.5) / st.length) - vh / 2, v]);
        });
      });
      anchors = list;
    }
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
        S.stage = stageAt(st.start + proxy.p * (st.end - st.start));
      }
    });
    measure();
    S.stage = stageAt(window.scrollY);

    story.querySelectorAll(".ch-card").forEach(function (card) {
      var title = card.querySelector(".ch-title");
      var parts = card.querySelectorAll(".ch-n, .ch-big, .ch-label, .ch-go, .ch-mark, .btn-row");
      var tl = gsap.timeline({ scrollTrigger: { trigger: card, start: "top 88%", once: true } });
      tl.from(card, { autoAlpha: 0, y: 30, duration: 0.7, ease: "power3.out" }, 0);
      if (title && window.SplitText) {
        var split = SplitText.create(title, { type: "lines", mask: "lines", linesClass: "ch-line" });
        tl.from(split.lines, { yPercent: 115, duration: 0.9, ease: "expo.out", stagger: 0.08 }, 0.05);
        tl.eventCallback("onComplete", function () { split.revert(); });   // lines re-flow freely after
      }
      tl.from(parts, { autoAlpha: 0, y: 16, duration: 0.6, ease: "power3.out", stagger: 0.06 }, 0.15);
    });
  }
})();
