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
})();
