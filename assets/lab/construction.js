// Construction Forecast: Prairie Ridge Builders (fictional) scenario model.
// Scenario analysis, not a forecast. Pure client-side arithmetic, no network calls.
//
// Inputs come from window.CONSTRUCTION_DATA (assets/lab/construction-data.js), which
// tools/sitegen.py writes from the forecasting engine's committed results. The engine
// below is a line-for-line port of the engine's construction/scenario.py: same loops,
// same left-to-right sums, same mulberry32 random numbers in the same order.
// tests/check_construction.py runs every preset here and compares against the
// Python results, and mutates this file to prove the comparison can fail.
(function () {
  "use strict";
  var D = window.CONSTRUCTION_DATA;
  var root = document.getElementById("cf");
  if (!D || !root) return;
  var MODEL = D.model;
  var MAIN = MODEL.main_months || MODEL.months.length;    // the plan view, as simulate() defaults it

  // ---------------------------------------------------------------- engine -----
  var DRIVER_ORDER = ["weather", "tariff", "rate_bp", "funding_delay", "diesel"];
  var BRIDGE_LABELS = { weather: "Weather", tariff: "Materials and tariffs", rate_bp: "Rates",
                        funding_delay: "Public funding", diesel: "Fuel" };
  var BASE_SETTINGS = { weather: 0, tariff: 0, rate_bp: 0, funding_delay: 0, diesel: 0, tariff_episode: 0 };

  function assign(a, b) { var o = {}, k; for (k in a) o[k] = a[k]; for (k in b) o[k] = b[k]; return o; }

  function Mulberry32(seed) { this.state = seed | 0; }
  Mulberry32.prototype.next = function () {
    var a = this.state = (this.state + 0x6D2B79F5) | 0;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  Mulberry32.prototype.normal = function () {
    var u1 = this.next(), u2 = this.next();
    return Math.sqrt(-2.0 * Math.log(1.0 - u1)) * Math.cos(2.0 * Math.PI * u2);
  };
  Mulberry32.prototype.index = function (n) { return Math.min(Math.floor(this.next() * n), n - 1); };

  function drawNoise(model, rng) {
    var weather = model.weather;
    var year = weather.years[rng.index(weather.years.length)].lost;
    var path = model.macro_error_paths[rng.index(model.macro_error_paths.length)];
    var anomaly = [];
    for (var m = 0; m < year.length; m++) anomaly.push(year[m] - weather.mean[m]);
    var zPpi = rng.normal(), zRate = rng.normal(), zDiesel = rng.normal();
    return { weather_anomaly: anomaly, macro_log_error: path, z_ppi: zPpi, z_rate: zRate, z_diesel: zDiesel };
  }

  function lostDays(weather, setting, m) {
    var mean = weather.mean[m];
    if (setting >= 0) return mean + setting * (weather.p90[m] - mean);
    return mean + setting * (mean - weather.p10[m]);
  }

  function simulate(model, settings, noise) {
    var n = model.months.length, main = model.main_months || n;
    var w = model.weather, b = model.bookings, c = model.costs, backlog = model.backlog;
    var r = model.rates, f = model.fuel;
    var dieselLevel = settings.diesel * (settings.diesel >= 0 ? f.p90 : -f.p10);
    var rateScale = noise ? Math.max(0.0, 1.0 + model.monte_carlo.rate_uncertainty * noise.z_rate) : 1.0;
    var rateSensitivity = r.bookings_per_100bp * rateScale;
    var months = [], bookingsSoFar = [], carry = 0.0;
    for (var m = 0; m < n; m++) {
      var lost = lostDays(w, settings.weather, m);
      if (noise) lost = Math.max(0.0, lost + noise.weather_anomaly[m]);
      var excess = lost - w.mean[m];
      var capacity = 1.0 - w.exposure * excess / w.weekdays[m];

      var macroMult = noise ? Math.exp(noise.macro_log_error[m]) : 1.0;
      var lagged = m - r.lag_months;
      var rateGap = lagged >= r.scenario_starts ? settings.rate_bp / 100.0 : 0.0;
      var rateMult = 1.0 + rateSensitivity * rateGap;
      var delayed = m < model.funding.delay_months ? settings.funding_delay : 0.0;
      var fundingMult = 1.0 - b.public_share * model.funding.delayed_public_cut * delayed;
      var booked = b.bookings_base[m] * macroMult * rateMult * fundingMult;
      bookingsSoFar.push(booked);

      var newWork = 0.0;
      for (var k = 0; k < bookingsSoFar.length; k++) {
        var age = m - k;
        if (b.start_delay_months <= age && age < b.start_delay_months + b.duration_months) {
          newWork += bookingsSoFar[k] / b.duration_months;
        }
      }
      var planned = backlog.fixed[m] + backlog.escalation[m] + newWork;
      var fixedShare = (backlog.fixed[m] + newWork * b.fixed_price_share) / planned;
      var margin = (backlog.margin_dollars[m] + newWork * b.margin) / planned;

      var available = planned + carry;
      var done = available * Math.min(capacity, 1.0);
      carry = available - done;

      var episode = model.materials.episodes[settings.tariff_episode | 0];
      var ppiLog = settings.tariff * episode.ppi_path[m];
      if (noise) ppiLog += noise.z_ppi * model.materials.resid_sd * Math.sqrt(m + 1);
      var baseCost = done * (1.0 - margin);
      var materialCost = baseCost * c.material_share * (Math.exp(ppiLog) - 1.0);
      var escalationRevenue = materialCost * (1.0 - fixedShare) * c.escalation_pass_through;

      var dieselLog = dieselLevel * Math.min(1.0, (m + 1) / main);
      if (noise) dieselLog += noise.z_diesel * f.monthly_sd * Math.sqrt(m + 1);
      var fuelCost = baseCost * c.fuel_share * (Math.exp(dieselLog) - 1.0);

      var overhead = w.gc_per_lost_day * w.exposure * excess;
      var revenue = done + escalationRevenue;
      var grossProfit = done * margin + escalationRevenue - materialCost - fuelCost - overhead;
      months.push({ month: model.months[m], planned: planned, done: done, carry: carry, bookings: booked,
                    revenue: revenue, gross_profit: grossProfit, lost_days: lost, capacity: capacity,
                    material_cost: materialCost, escalation_revenue: escalationRevenue,
                    fuel_cost: fuelCost, overhead: overhead });
    }
    var byView = views(model, months);
    return { months: months, views: byView, totals: byView[String(main)] };
  }

  function totals(months) {
    var revenue = 0.0, grossProfit = 0.0, bookings = 0.0, i;
    for (i = 0; i < months.length; i++) revenue += months[i].revenue;
    for (i = 0; i < months.length; i++) grossProfit += months[i].gross_profit;
    for (i = 0; i < months.length; i++) bookings += months[i].bookings;
    return { revenue: revenue, gross_profit: grossProfit, gross_margin: revenue ? grossProfit / revenue : 0.0,
             bookings: bookings, deferred: months[months.length - 1].carry };
  }

  function viewLengths(model) {
    var n = model.months.length, main = model.main_months || n;
    return main === n ? [main] : [main, n];
  }

  function views(model, months) {
    var out = {};
    viewLengths(model).forEach(function (k) { out[String(k)] = totals(months.slice(0, k)); });
    return out;
  }

  function bridge(model, settings) {
    var current = assign(BASE_SETTINGS, { tariff_episode: settings.tariff_episode });
    var previous = simulate(model, current).views, steps = {}, k;
    for (k in previous) steps[k] = [{ step: "Base plan", revenue: previous[k].revenue, gross_profit: previous[k].gross_profit }];
    DRIVER_ORDER.forEach(function (driver) {
      current[driver] = settings[driver];
      var result = simulate(model, current).views;
      for (var v in steps) {
        steps[v].push({ step: BRIDGE_LABELS[driver], revenue: result[v].revenue - previous[v].revenue,
                        gross_profit: result[v].gross_profit - previous[v].gross_profit });
      }
      previous = result;
    });
    for (k in steps) steps[k].push({ step: "Scenario", revenue: previous[k].revenue, gross_profit: previous[k].gross_profit });
    return steps;
  }

  function percentile(sorted, q) {
    var position = (sorted.length - 1) * q / 100.0;
    var low = Math.floor(position), high = Math.min(low + 1, sorted.length - 1);
    return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
  }

  // P10, P50, P90 of a list of numbers. The comparator matters: without it
  // JavaScript sorts numbers as text, which puts 100 before 9.
  function quantiles(values, qs) {
    var sorted = values.slice().sort(function (a, b) { return a - b; }), out = {};
    qs.forEach(function (q) { out["p" + q] = percentile(sorted, q); });
    return out;
  }

  function monteCarlo(model, settings) {
    var mc = model.monte_carlo, rng = new Mulberry32(mc.seed);
    var keys = viewLengths(model).map(String), collected = {}, monthly = [], i, m;
    keys.forEach(function (k) { collected[k] = { revenue: [], gross_profit: [], gross_margin: [] }; });
    for (m = 0; m < model.months.length; m++) monthly.push([]);
    for (i = 0; i < mc.draws; i++) {
      var result = simulate(model, settings, drawNoise(model, rng));
      keys.forEach(function (k) {
        collected[k].revenue.push(result.views[k].revenue);
        collected[k].gross_profit.push(result.views[k].gross_profit);
        collected[k].gross_margin.push(result.views[k].gross_margin);
      });
      for (m = 0; m < result.months.length; m++) monthly[m].push(result.months[m].revenue);
    }
    function pick(values) { return quantiles(values, mc.quantiles); }
    var viewsOut = {};
    keys.forEach(function (k) {
      viewsOut[k] = { revenue: pick(collected[k].revenue), gross_profit: pick(collected[k].gross_profit),
                      gross_margin: pick(collected[k].gross_margin) };
    });
    return { views: viewsOut, monthly_revenue: monthly.map(pick) };
  }

  function runSettings(model, settings) {
    var result = simulate(model, settings);
    var base = simulate(model, assign(BASE_SETTINGS, { tariff_episode: settings.tariff_episode })).views;
    var change = {};
    for (var k in result.views) {
      change[k] = { revenue: result.views[k].revenue - base[k].revenue,
                    gross_profit: result.views[k].gross_profit - base[k].gross_profit,
                    gross_margin_pts: 100 * (result.views[k].gross_margin - base[k].gross_margin) };
    }
    return { settings: settings, views: result.views, months: result.months, change_from_base: change,
             bridge: bridge(model, settings), monte_carlo: monteCarlo(model, settings) };
  }

  // Read-only hook for the checks.
  window.Construction = { simulate: simulate, bridge: bridge, monteCarlo: monteCarlo, runSettings: runSettings,
                          Mulberry32: Mulberry32, percentile: percentile, quantiles: quantiles, model: MODEL };

  // ------------------------------------------------------------------ format -----
  var MINUS = "−";
  function money(k, digits) {                         // USD thousands in, "$260.0M" out
    var places = digits === undefined ? 1 : digits;
    var v = k / 1000, s = Math.abs(v).toFixed(places);
    if (+s === 0) v = 0;                                // never print a minus sign on zero
    return (v < 0 ? MINUS : "") + "$" + s.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "M";
  }
  function signedMoney(k) { return Math.abs(k) < 50 ? "$0.0M" : (k > 0 ? "+" : "") + money(k); }
  function pct(x) { return (100 * x).toFixed(2) + "%"; }
  function pts(x) { var s = Math.abs(x).toFixed(2); return (x > 0.005 ? "+" : x < -0.005 ? MINUS : "") + s + " pts"; }
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function monthLabel(ym) { var p = ym.split("-"); return MONTHS[+p[1] - 1] + " " + p[0]; }

  // ------------------------------------------------------------------- state -----
  var $ = function (id) { return document.getElementById(id); };
  // Start from whatever the radios show: a browser may restore them on reload.
  function checkedValue(name, fallback) {
    var c = root.querySelector("input[name=" + name + "]:checked");
    return c ? c.value : fallback;
  }
  var state = { settings: assign(BASE_SETTINGS, {}), view: checkedValue("cf-view", String(MAIN)),
                metric: checkedValue("cf-metric", "gross_profit") };
  var SLIDERS = [
    { key: "weather", id: "cf-weather", text: function (v) {
      return v === 0 ? "Normal year" : v > 0 ? (v === 1 ? "Harsh (P90 year)" : "Harsher, " + v.toFixed(2) + " of the way to P90")
        : (v === -1 ? "Mild (P10 year)" : "Milder, " + (-v).toFixed(2) + " of the way to P10"); } },
    { key: "tariff", id: "cf-tariff", text: function (v) {
      return v === 0 ? "Held at current levels" : v > 0 ? "Raised, " + v.toFixed(2) + " times the episode"
        : "Reduced, " + (-v).toFixed(2) + " of the episode given back"; } },
    { key: "rate_bp", id: "cf-rates", text: function (v) {
      return v === 0 ? "Fed " + MODEL.rates.projection_release + " projections" : (v > 0 ? "+" : MINUS) + Math.abs(v) + " bp on the Fed path"; } },
    { key: "funding_delay", id: "cf-funding", text: function (v) { return v ? "Bill delayed" : "Bill on time"; } },
    { key: "diesel", id: "cf-diesel", text: function (v) {
      return v === 0 ? "Held at latest price" : v > 0 ? "Higher, " + v.toFixed(2) + " of the way to P90" : "Lower, " + (-v).toFixed(2) + " of the way to P10"; } }
  ];

  // --------------------------------------------------------------- controls -----
  var presetRow = $("cf-presets");
  MODEL.presets.forEach(function (p) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "preset";
    b.dataset.preset = p.key;
    b.setAttribute("aria-pressed", "false");
    b.textContent = p.label;
    b.addEventListener("click", function () {
      state.settings = { weather: p.weather, tariff: p.tariff, rate_bp: p.rate_bp, funding_delay: p.funding_delay,
                         diesel: p.diesel, tariff_episode: p.tariff_episode };
      render();
    });
    presetRow.appendChild(b);
  });

  SLIDERS.forEach(function (s) {
    var input = $(s.id), bounds = MODEL.sliders[s.key];
    input.min = bounds.min; input.max = bounds.max; input.step = bounds.step;
    input.addEventListener("input", function () { state.settings[s.key] = +input.value; schedule(); });
  });
  var episodeSel = $("cf-episode");
  MODEL.materials.episodes.forEach(function (e, i) {
    var o = document.createElement("option");
    o.value = String(i);
    o.textContent = e.label + (i === 0 ? " (default)" : "");
    episodeSel.appendChild(o);
  });
  episodeSel.addEventListener("change", function () { state.settings.tariff_episode = +episodeSel.value; render(); });

  root.querySelectorAll("input[name=cf-view]").forEach(function (r) {
    r.addEventListener("change", function () { if (r.checked) { state.view = r.value; render(); } });
  });
  root.querySelectorAll("input[name=cf-metric]").forEach(function (r) {
    r.addEventListener("change", function () { if (r.checked) { state.metric = r.value; render(); } });
  });

  var pending = false;
  function schedule() {                               // coalesce rapid slider input into one render per frame
    if (pending) return;
    pending = true;
    (window.requestAnimationFrame || setTimeout)(function () { pending = false; render(); });
  }

  // ------------------------------------------------------------------ charts -----
  var SVGNS = "http://www.w3.org/2000/svg";
  function el(name, attrs, text) {
    var e = document.createElementNS(SVGNS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    return e;
  }
  // Charts are drawn at the width they are shown, so 13px labels stay 13px on a phone.
  function fitWidth(svg, H) {
    var w = Math.round((svg.parentNode && svg.parentNode.clientWidth) || 640);
    var W = Math.max(320, Math.min(640, w));
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    return W;
  }
  var SHORT = { "Base plan": "Base", "Weather": "Weather", "Materials and tariffs": "Tariffs", "Rates": "Rates",
                "Public funding": "Funding", "Fuel": "Fuel", "Scenario": "Scenario" };

  function niceStep(span) {
    var raw = span / 4, p = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), r = raw / p;
    return (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * p;
  }

  function revenueChart(svg, months, base, band, n) {
    var H = 300, W = fitWidth(svg, H), L = 64, R = 16, T = 16, B = 40;
    while (svg.lastChild && svg.lastChild.nodeName !== "title" && svg.lastChild.nodeName !== "desc") svg.removeChild(svg.lastChild);
    var lo = Infinity, hi = -Infinity, m;
    for (m = 0; m < n; m++) {
      lo = Math.min(lo, band[m].p10, months[m].revenue, base[m].revenue);
      hi = Math.max(hi, band[m].p90, months[m].revenue, base[m].revenue);
    }
    var step = niceStep((hi - lo) || 1), y0 = Math.floor(lo / step) * step, y1 = Math.ceil(hi / step) * step;
    var tickDigits = step < 1000 ? 1 : 0;                // keep tick labels distinct on a narrow range
    var x = function (i) { return L + (n === 1 ? 0 : i / (n - 1) * (W - L - R)); };
    var y = function (v) { return T + (y1 - v) / (y1 - y0) * (H - T - B); };
    var main = MAIN;
    if (n > main) {
      svg.appendChild(el("rect", { "class": "cf-ext", x: ((x(main - 1) + x(main)) / 2).toFixed(1), y: T,
        width: (W - R - (x(main - 1) + x(main)) / 2).toFixed(1), height: H - T - B }));
      svg.appendChild(el("text", { "class": "ch-tick", x: (W - R - 6), y: T + 14, "text-anchor": "end" }, W < 480 ? "Extension" : "Scenario extension"));
    }
    for (var v = y0; v <= y1 + step / 2; v += step) {
      svg.appendChild(el("line", { "class": "ch-grid", x1: L, x2: W - R, y1: y(v).toFixed(1), y2: y(v).toFixed(1) }));
      svg.appendChild(el("text", { "class": "ch-tick", x: L - 8, y: (y(v) + 4).toFixed(1), "text-anchor": "end" }, money(v, tickDigits)));
    }
    var every = W < 480 ? (n > 12 ? 6 : 3) : (n > 12 ? 3 : 2);
    for (m = 0; m < n; m += every) {
      svg.appendChild(el("text", { "class": "ch-tick", x: x(m).toFixed(1), y: H - B + 20, "text-anchor": "middle" },
        monthLabel(months[m].month).replace(" 20", " ")));
    }
    var upper = [], lower = [], line = [], baseLine = [];
    for (m = 0; m < n; m++) {
      upper.push(x(m).toFixed(1) + " " + y(band[m].p90).toFixed(1));
      lower.unshift(x(m).toFixed(1) + " " + y(band[m].p10).toFixed(1));
      line.push(x(m).toFixed(1) + " " + y(months[m].revenue).toFixed(1));
      baseLine.push(x(m).toFixed(1) + " " + y(base[m].revenue).toFixed(1));
    }
    svg.appendChild(el("path", { "class": "cf-band", d: "M" + upper.join(" L") + " L" + lower.join(" L") + " Z" }));
    svg.appendChild(el("path", { "class": "ch-line cf-base", d: "M" + baseLine.join(" L") }));
    svg.appendChild(el("path", { "class": "ch-line cf-scen", d: "M" + line.join(" L") }));
  }

  function bridgeChart(svg, steps, metric) {
    var H = 300, W = fitWidth(svg, H), L = 72, R = 16, T = 30, B = 56, narrow = W < 480;
    while (svg.lastChild && svg.lastChild.nodeName !== "title" && svg.lastChild.nodeName !== "desc") svg.removeChild(svg.lastChild);
    var running = 0, bars = [], values = [];
    steps.forEach(function (st, i) {
      var v = st[metric], total = i === 0 || i === steps.length - 1, from = total ? null : running;
      var to = total ? v : running + v;
      running = to;
      bars.push({ step: st.step, from: from, to: to, total: total, delta: v,
                  margin: total ? st.gross_profit / st.revenue : null });
      values.push(to);
      if (from !== null) values.push(from);
    });
    // The axis starts near the totals, not at zero, so steps of a few tenths of a
    // percent stay visible. The floor value is printed on the axis.
    var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    var pad = Math.max((hi - lo) * 0.35, Math.abs(hi) * 0.01);
    var v0 = lo - pad, v1 = hi + pad;
    if (narrow) return horizontalBridge(svg, bars, metric, W, v0, v1);
    var y = function (v) { return T + (v1 - v) / (v1 - v0) * (H - T - B); };
    var slot = (W - L - R) / bars.length, bw = slot * 0.62;
    svg.appendChild(el("line", { "class": "ch-grid", x1: L, x2: W - R, y1: y(v0).toFixed(1), y2: y(v0).toFixed(1) }));
    svg.appendChild(el("text", { "class": "ch-tick", x: L - 8, y: (y(v0) + 4).toFixed(1), "text-anchor": "end" }, money(v0, 1)));
    svg.appendChild(el("text", { "class": "ch-tick", x: L - 8, y: (y(hi) + 4).toFixed(1), "text-anchor": "end" }, money(hi, 1)));
    bars.forEach(function (b, i) {
      var cx = L + slot * i + slot / 2;
      var start = b.total ? v0 : b.from;
      var top = y(Math.max(start, b.to)), bottom = y(Math.min(start, b.to));
      svg.appendChild(el("rect", { "class": barClass(b), x: (cx - bw / 2).toFixed(1), y: top.toFixed(1), width: bw.toFixed(1),
                                   height: Math.max(1.5, bottom - top).toFixed(1) }));
      svg.appendChild(el("text", { "class": "ch-tick cf-val", x: cx.toFixed(1), y: (top - 7).toFixed(1), "text-anchor": "middle" },
        b.total ? money(b.to) : signedMoney(b.delta)));
      if (b.total && metric === "gross_profit") {
        svg.appendChild(el("text", { "class": "ch-tick", x: cx.toFixed(1), y: (top - 21).toFixed(1), "text-anchor": "middle" },
          pct(b.margin) + " margin"));
      }
      var words = b.step.split(" ");
      svg.appendChild(el("text", { "class": "ch-tick", x: cx.toFixed(1), y: H - B + 18, "text-anchor": "middle" }, words.slice(0, 2).join(" ")));
      if (words.length > 2) {
        svg.appendChild(el("text", { "class": "ch-tick", x: cx.toFixed(1), y: H - B + 34, "text-anchor": "middle" }, words.slice(2).join(" ")));
      }
    });
  }

  function barClass(b) { return b.total ? "cf-bar-total" : b.delta >= 0 ? "cf-bar-up" : "cf-bar-down"; }

  // On a phone the bridge runs down the page: one row per step, label on the
  // left, bar in the middle, value on the right, so nothing has to share a column.
  function horizontalBridge(svg, bars, metric, W, v0, v1) {
    var rowH = 38, T = 8, H = T + rowH * bars.length + 24, labelW = 74, valueW = 92;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("height", H);
    var x = function (v) { return labelW + (v - v0) / (v1 - v0) * (W - labelW - valueW); };
    bars.forEach(function (b, i) {
      var y = T + rowH * i, start = b.total ? v0 : b.from;
      var left = x(Math.min(start, b.to)), right = x(Math.max(start, b.to));
      svg.appendChild(el("text", { "class": "ch-tick", x: 0, y: y + 21 }, SHORT[b.step] || b.step));
      svg.appendChild(el("rect", { "class": barClass(b), x: left.toFixed(1), y: y + 8, width: Math.max(1.5, right - left).toFixed(1), height: 18 }));
      var value = b.total ? money(b.to) : signedMoney(b.delta);
      svg.appendChild(el("text", { "class": "ch-tick cf-val", x: W, y: y + (b.total && metric === "gross_profit" ? 15 : 21), "text-anchor": "end" }, value));
      if (b.total && metric === "gross_profit") {
        svg.appendChild(el("text", { "class": "ch-tick", x: W, y: y + 31, "text-anchor": "end" }, pct(b.margin) + " margin"));
      }
    });
    svg.appendChild(el("line", { "class": "ch-grid", x1: labelW, x2: labelW, y1: T, y2: H - 22 }));
    svg.appendChild(el("text", { "class": "ch-tick", x: labelW, y: H - 6 }, "Axis starts at " + money(v0, 1)));
  }

  function cell(tag, text, cls, scope) {
    var c = document.createElement(tag);
    c.textContent = text;
    if (cls) c.className = cls;
    if (scope) c.setAttribute("scope", scope);
    return c;
  }
  function fillTable(table, rows) {
    var body = table.querySelector("tbody");
    while (body.firstChild) body.removeChild(body.firstChild);
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.appendChild(cell("th", r[0], null, "row"));
      for (var i = 1; i < r.length; i++) tr.appendChild(cell("td", r[i], "num"));
      body.appendChild(tr);
    });
  }

  // ------------------------------------------------------------------ render -----
  function render() {
    var s = state.settings, view = state.view, n = +view;
    SLIDERS.forEach(function (sl) {
      var input = $(sl.id), v = s[sl.key], text = sl.text(v);
      input.value = v;
      $(sl.id + "-out").textContent = text;
      input.setAttribute("aria-valuetext", text);
    });
    episodeSel.value = String(s.tariff_episode);

    var out = runSettings(MODEL, s), base = simulate(MODEL, assign(BASE_SETTINGS, { tariff_episode: s.tariff_episode }));
    state.last = out;
    var t = out.views[view], c = out.change_from_base[view], mc = out.monte_carlo.views[view];
    $("cf-rev").textContent = money(t.revenue);
    $("cf-gp").textContent = money(t.gross_profit);
    $("cf-gm").textContent = pct(t.gross_margin);
    $("cf-d-rev").textContent = signedMoney(c.revenue);
    $("cf-d-gp").textContent = signedMoney(c.gross_profit);
    $("cf-d-gm").textContent = pts(c.gross_margin_pts);
    $("cf-spread").textContent = money(mc.revenue.p10) + " to " + money(mc.revenue.p90);
    $("cf-deferred").textContent = money(t.deferred);
    var span = view === String(MAIN) ? "the " + MAIN + "-month plan"
      : "the " + view + "-month view (months " + (MAIN + 1) + " to " + view + " are a scenario extension)";
    var summary = "Over " + span + ": revenue " + money(t.revenue) + ", gross profit " + money(t.gross_profit) +
      " at a " + pct(t.gross_margin) + " margin. Change from the base plan: " + signedMoney(c.revenue) + " revenue, " +
      signedMoney(c.gross_profit) + " gross profit, " + pts(c.gross_margin_pts) + ".";
    // Only touch the live region when the words change, so it is announced once.
    if ($("cf-summary").textContent !== summary) $("cf-summary").textContent = summary;

    var months = out.months.slice(0, n), baseMonths = base.months.slice(0, n), band = out.monte_carlo.monthly_revenue.slice(0, n);
    var rs = $("cf-rev-chart");
    revenueChart(rs, months, baseMonths, band, n);
    $("cf-rev-d").textContent = "Monthly revenue for Prairie Ridge Builders (fictional), " + monthLabel(months[0].month) + " to " +
      monthLabel(months[n - 1].month) + ". Scenario " + money(months[0].revenue) + " in the first month and " +
      money(months[n - 1].revenue) + " in the last. The shaded band is the 10th to 90th percentile spread of " +
      MODEL.monte_carlo.draws.toLocaleString("en-US") + " redrawn scenario outcomes, " +
      "not a probability. Every month is in the table below the chart.";
    var steps = out.bridge[view];
    bridgeChart($("cf-bridge-chart"), steps, state.metric);
    var label = state.metric === "revenue" ? "revenue" : "gross profit";
    $("cf-bridge-d").textContent = "Bridge of " + label + " from the base plan, " + money(steps[0][state.metric]) +
      ", through " + steps.slice(1, -1).map(function (st) { return st.step.toLowerCase() + " " + signedMoney(st[state.metric]); }).join(", ") +
      ", to the scenario, " + money(steps[steps.length - 1][state.metric]) + ". Base margin " +
      pct(steps[0].gross_profit / steps[0].revenue) + ", scenario margin " + pct(t.gross_margin) + ".";

    fillTable($("cf-bridge-table"), steps.map(function (st, i) {
      var total = i === 0 || i === steps.length - 1;
      return [st.step, total ? money(st.revenue) : signedMoney(st.revenue),
              total ? money(st.gross_profit) : signedMoney(st.gross_profit),
              total ? pct(st.gross_profit / st.revenue) : ""];
    }));
    fillTable($("cf-month-table"), months.map(function (mo, i) {
      return [monthLabel(mo.month) + (i >= MAIN ? " (extension)" : ""), money(mo.revenue), money(mo.gross_profit),
              pct(mo.gross_profit / mo.revenue), money(band[i].p10) + " to " + money(band[i].p90), money(baseMonths[i].revenue)];
    }));

    presetRow.querySelectorAll(".preset").forEach(function (b) {
      var p = MODEL.presets.filter(function (x) { return x.key === b.dataset.preset; })[0];
      var match = DRIVER_ORDER.every(function (k) { return p[k] === s[k]; }) && p.tariff_episode === s.tariff_episode;
      b.setAttribute("aria-pressed", match ? "true" : "false");
    });
  }

  // Redraw only when the panel's width changes. A phone's address bar changes the
  // height on scroll, and redrawing then would re-announce the summary for nothing.
  var resizeTimer = null, lastWidth = root.clientWidth;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (root.clientWidth !== lastWidth) { lastWidth = root.clientWidth; render(); }
    }, 150);
  });

  render();
})();
