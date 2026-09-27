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

    return function () {
      M.on = false;
      document.documentElement.classList.remove("motion");
      if (tick) gsap.ticker.remove(tick);
      if (lenis) lenis.destroy();
      M.lenis = null;
    };
  });
})();
