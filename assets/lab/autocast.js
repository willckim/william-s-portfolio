// Forecast your own data: the second tab of the Construction Forecast panel.
// A visitor's CSV is read and forecast entirely in this browser tab. Nothing is
// uploaded, sent or stored: there is no network code in this file at all.
//
// The engine below ports the forecasting engine's src/autoforecast.py and the
// three models it uses from src/models.py, line for line: same parameter grid,
// same left-to-right sums, same rules for frequency, scale, backtest, winner and
// band. tests/check_construction.py runs the three sample datasets here and
// compares every number with the Python results.
(function () {
  "use strict";
  var D = window.CONSTRUCTION_DATA;
  var root = document.getElementById("ac");
  if (!D || !root) return;

  // ------------------------------------------------------------- the models -----
  var SEASON = { monthly: 12, quarterly: 4 }, STEP = { monthly: 1, quarterly: 3 };
  var MIN_POINTS = { monthly: 24, quarterly: 8 }, MAX_POINTS = { monthly: 240, quarterly: 80 };
  var ORIGINS = { monthly: 36, quarterly: 12 }, TIE = 0.001, QS = [10, 50, 90];
  var NEAR_ZERO_SHARE = 0.01;
  var MAX_BYTES = 5 * 1024 * 1024, MAX_ROWS = 10000, MAX_COLUMNS = 20, MIN_FOLDS = 6;
  var UNIT = { monthly: ["month", "months"], quarterly: ["quarter", "quarters"] };

  function sum(values) { var t = 0.0; for (var i = 0; i < values.length; i++) t += values[i]; return t; }

  function seasonalNaive(y, m, h) {
    if (y.length < m) throw new Error("seasonal naive needs a full season");
    var last = y.slice(y.length - m), out = [];
    for (var i = 0; i < h; i++) out.push(last[i % m]);
    return out;
  }

  // Least squares on [1, t, season dummies] over the last 5 seasons, solved from
  // the normal equations as numpy.linalg.solve does (Gaussian elimination, partial pivoting).
  function linearTrend(y, m, h) {
    var window = Math.min(y.length, 5 * m);
    if (window < 2 * m) throw new Error("linear trend needs two seasons");
    var phase0 = (y.length - window) % m, k = 1 + m, recent = y.slice(y.length - window);
    function row(t) {
      var x = new Array(k).fill(0);
      x[0] = 1.0; x[1] = t;
      var s = (t + phase0) % m;
      if (s > 0) x[1 + s] = 1.0;
      return x;
    }
    var A = [], b = new Array(k).fill(0), i, j, r;
    for (i = 0; i < k; i++) A.push(new Array(k).fill(0));
    for (var t = 0; t < window; t++) {
      var x = row(t);
      for (i = 0; i < k; i++) {
        b[i] += x[i] * recent[t];
        for (j = 0; j < k; j++) A[i][j] += x[i] * x[j];
      }
    }
    for (i = 0; i < k; i++) {                                  // elimination with partial pivoting
      var p = i;
      for (r = i + 1; r < k; r++) if (Math.abs(A[r][i]) > Math.abs(A[p][i])) p = r;
      var tmp = A[i]; A[i] = A[p]; A[p] = tmp;
      var tb = b[i]; b[i] = b[p]; b[p] = tb;
      for (r = i + 1; r < k; r++) {
        var f = A[r][i] / A[i][i];
        for (j = i; j < k; j++) A[r][j] -= f * A[i][j];
        b[r] -= f * b[i];
      }
    }
    var coef = new Array(k).fill(0);
    for (i = k - 1; i >= 0; i--) {
      var acc = b[i];
      for (j = i + 1; j < k; j++) acc -= A[i][j] * coef[j];
      coef[i] = acc / A[i][i];
    }
    var out = [];
    for (i = 0; i < h; i++) {
      var xr = row(window + i), v = 0.0;
      for (j = 0; j < k; j++) v += xr[j] * coef[j];
      out.push(v);
    }
    return out;
  }

  var ALPHAS = [], BETAS = [0.01, 0.05, 0.1, 0.2, 0.3], GAMMAS = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5],
      PHIS = [0.8, 0.85, 0.9, 0.95, 0.98];
  for (var a = 1; a < 20; a++) ALPHAS.push(Math.round(0.05 * a * 100) / 100);

  // Damped additive Holt-Winters, parameters from the engine's fixed grid by the
  // smallest one-step squared error after the first season. Ties keep the first.
  function holtWinters(y, m, h) {
    if (y.length < 2 * m + 1) throw new Error("Holt-Winters needs two seasons and one more point");
    var first = sum(y.slice(0, m)) / m, second = sum(y.slice(m, 2 * m)) / m;
    var trend0 = (second - first) / m, centre = (m - 1) / 2, s0 = [];
    for (var i = 0; i < m; i++) s0.push(y[i] - (first + (i - centre) * trend0));
    var level0 = first - (centre + 1) * trend0;
    var best = null;
    for (var ai = 0; ai < ALPHAS.length; ai++) for (var bi = 0; bi < BETAS.length; bi++)
    for (var gi = 0; gi < GAMMAS.length; gi++) for (var pi = 0; pi < PHIS.length; pi++) {
      var alpha = ALPHAS[ai], beta = BETAS[bi], gamma = GAMMAS[gi], phi = PHIS[pi];
      var level = level0, trend = trend0, seas = s0.slice(), sse = 0.0;
      for (var t = 0; t < y.length; t++) {
        var slot = t % m, season = seas[slot], damped = phi * trend;
        if (t >= m) { var err = y[t] - (level + damped + season); sse = sse + err * err; }
        var newLevel = alpha * (y[t] - season) + (1 - alpha) * (level + damped);
        trend = beta * (newLevel - level) + (1 - beta) * damped;
        seas[slot] = gamma * (y[t] - level - damped) + (1 - gamma) * season;
        level = newLevel;
      }
      if (best === null || sse < best.sse) best = { sse: sse, level: level, trend: trend, seas: seas, phi: phi };
    }
    var out = [], dampSum = 0.0, power = 1.0;
    for (var step = 1; step <= h; step++) {
      power *= best.phi;
      dampSum += power;
      out.push(best.level + dampSum * best.trend + best.seas[(y.length - 1 + step) % m]);
    }
    return out;
  }

  var MODELS = [
    { key: "seasonal_naive", name: "Seasonal naive", fn: seasonalNaive },
    { key: "linear_trend", name: "Linear trend + seasonality", fn: linearTrend },
    { key: "holt_winters_damped", name: "Holt-Winters (ETS), damped", fn: holtWinters }
  ];

  function allPositive(v) { for (var i = 0; i < v.length; i++) if (!(v[i] > 0)) return false; return true; }

  function fitPredict(key, train, m, h) {
    var model = MODELS.filter(function (x) { return x.key === key; })[0];
    var useLog = allPositive(train);
    var y = useLog ? train.map(Math.log) : train;
    var out = model.fn(y, m, h);
    return useLog ? out.map(Math.exp) : out;
  }

  function monthIndex(year, month) { return year * 12 + (month - 1); }

  function percentile(sorted, q) {
    var position = (sorted.length - 1) * q / 100.0;
    var low = Math.floor(position), high = Math.min(low + 1, sorted.length - 1);
    return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
  }

  function mapeNote(values) {
    for (var i = 0; i < values.length; i++) {
      if (values[i] <= 0) return "MAPE not shown: the series has zero or negative values, so percentage error is undefined or misleading.";
    }
    var abs = values.map(Math.abs).sort(function (x, y) { return x - y; }), n = abs.length;
    var median = n % 2 ? abs[(n - 1) / 2] : (abs[n / 2 - 1] + abs[n / 2]) / 2;
    for (i = 0; i < n; i++) {
      if (abs[i] < NEAR_ZERO_SHARE * median) return "MAPE not shown: some values are near zero, where one month's percentage error would swamp the average.";
    }
    return null;
  }

  function seasonalStrength(values, m) {
    var x = allPositive(values) ? values.map(Math.log) : values.slice(), d = [];
    for (var i = 1; i < x.length; i++) d.push(x[i] - x[i - 1]);
    if (d.length <= m + 1) return null;
    var mean = sum(d) / d.length, c = d.map(function (v) { return v - mean; });
    var denom = sum(c.map(function (v) { return v * v; }));
    if (denom === 0) return 0.0;
    var num = 0.0;
    for (var t = m; t < c.length; t++) num += c[t] * c[t - m];
    return num / denom;
  }

  function detectFrequency(periods) {
    var steps = {};
    for (var i = 1; i < periods.length; i++) steps[monthIndex(periods[i][0], periods[i][1]) - monthIndex(periods[i - 1][0], periods[i - 1][1])] = true;
    var keys = Object.keys(steps);
    if (keys.length === 1 && keys[0] === "1") return "monthly";
    if (keys.length === 1 && keys[0] === "3") return "quarterly";
    return null;
  }

  // settings (optional) mirror autoforecast.run: first_origin [year, month],
  // publication_lag, max_points (null for the whole series). A visitor's own file
  // gets the defaults, because the page cannot know when it is published.
  function run(periods, values, settings) {
    settings = settings || {};
    var frequency = detectFrequency(periods);
    if (!frequency) throw new Error("The dates are not evenly monthly or quarterly.");
    var m = SEASON[frequency], h = m, lag = settings.publication_lag ? +settings.publication_lag : 0;
    if (values.length < MIN_POINTS[frequency]) {
      throw new Error("Only " + values.length + " " + frequency + " points. At least " + MIN_POINTS[frequency] + " are needed to see a seasonal pattern.");
    }
    var cap = settings.max_points === undefined ? MAX_POINTS[frequency] : settings.max_points;
    var total = values.length, kept = cap === null ? total : Math.min(total, cap);
    periods = periods.slice(total - kept); values = values.slice(total - kept);
    var n = values.length, testable = 2 * m + lag + h + MIN_FOLDS;
    if (n < testable) {
      throw new Error(n + " " + frequency + " points are enough to see a seasonal pattern, but testing a forecast " + h + " " +
        UNIT[frequency][1] + " ahead needs at least " + testable + ": " + (2 * m + 1) + " to fit the models and enough after that " +
        "to check every " + UNIT[frequency][0] + " ahead at least " + MIN_FOLDS + " times.");
    }
    var firstOrigin, origins = [];
    if (settings.first_origin) {
      firstOrigin = -1;
      for (var fi = 0; fi < periods.length; fi++) {
        if (periods[fi][0] === settings.first_origin[0] && periods[fi][1] === settings.first_origin[1]) { firstOrigin = fi; break; }
      }
      if (firstOrigin < 0) throw new Error("The first backtest origin is not in the series.");
      if (firstOrigin < 2 * m + lag || n - firstOrigin - h < MIN_FOLDS) throw new Error("The first backtest origin leaves too little to fit or to test.");
    } else {
      firstOrigin = Math.max(2 * m + lag, n - 1 - ORIGINS[frequency]);
    }
    for (var o = firstOrigin; o < n - 1; o++) origins.push(o);
    var note = mapeNote(values), positive = allPositive(values), table = [], errors = {};
    MODELS.forEach(function (model) {
      var byH = {}, hh;
      for (hh = 1; hh <= h; hh++) byH[hh] = [];
      origins.forEach(function (origin) {
        var known = origin - lag;                                // the last period published at the origin
        var f = fitPredict(model.key, values.slice(0, known + 1), m, h + lag).slice(lag);
        for (var k = 1; k <= h; k++) if (origin + k < n) byH[k].push([values[origin + k], f[k - 1]]);
      });
      errors[model.key] = byH;
      var rows = [];
      for (hh = 1; hh <= h; hh++) {
        var pairs = byH[hh];
        if (!pairs.length) continue;
        var mae = sum(pairs.map(function (p) { return Math.abs(p[0] - p[1]); })) / pairs.length;
        var mape = note ? null : 100.0 * sum(pairs.map(function (p) { return Math.abs(p[0] - p[1]) / Math.abs(p[0]); })) / pairs.length;
        rows.push({ h: hh, folds: pairs.length, mae: mae, mape: mape });
      }
      if (!rows.length) throw new Error("Not enough history to test any model.");
      table.push({ key: model.key, name: model.name, by_horizon: rows,
                   mean_mae: sum(rows.map(function (r) { return r.mae; })) / rows.length,
                   mean_mape: note ? null : sum(rows.map(function (r) { return r.mape; })) / rows.length });
    });
    var metric = note ? "mean_mae" : "mean_mape";
    var best = Infinity;
    table.forEach(function (r) { if (r[metric] < best) best = r[metric]; });
    var winner = table.filter(function (r) { return r[metric] <= best * (1 + TIE); })[0].key;
    var bands = {};
    Object.keys(errors[winner]).forEach(function (k) {
      var pairs = errors[winner][k];
      if (!pairs.length) return;
      var errs = pairs.map(function (p) { return positive ? Math.log(p[0] / p[1]) : p[0] - p[1]; }).sort(function (x, y) { return x - y; });
      bands[k] = {};
      QS.forEach(function (q) { bands[k]["p" + q] = percentile(errs, q); });
    });
    var final = fitPredict(winner, values, m, h + lag).slice(lag), last = monthIndex(periods[periods.length - 1][0], periods[periods.length - 1][1]);
    var forecast = final.map(function (point, i) {
      var idx = last + (lag + i + 1) * STEP[frequency], row = { year: Math.floor(idx / 12), month: idx % 12 + 1, point: point };
      if (bands[i + 1]) QS.forEach(function (q) { var e = bands[i + 1]["p" + q]; row["p" + q] = positive ? point * Math.exp(e) : point + e; });
      return row;
    });
    return { frequency: frequency, season: m, horizon: h, points_used: n, points_dropped: total - kept,
             seasonal_strength: seasonalStrength(values, m), origins: origins.length,
             first_origin: periods[firstOrigin].slice(), publication_lag: lag,
             metric: note ? "MAE" : "MAPE", mape_note: note, band_scale: positive ? "ratio" : "difference",
             table: table, winner: winner, forecast: forecast, periods: periods, values: values };
  }

  // ------------------------------------------------------------- the parser -----
  var MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

  // RFC 4180 style: quoted fields may hold the delimiter, quotes ("") and line breaks.
  // The delimiter is whichever of comma, semicolon or tab appears most in the first
  // line outside quotes. Each row keeps the line number it started on, so messages
  // point at the line a person sees in their editor, blank lines included.
  function delimiterOf(text) {
    var counts = { ",": 0, ";": 0, "\t": 0 }, quoted = false;
    for (var i = 0; i < text.length && text[i] !== "\n" && text[i] !== "\r"; i++) {
      if (text[i] === '"') quoted = !quoted;
      else if (!quoted && counts.hasOwnProperty(text[i])) counts[text[i]]++;
    }
    return counts[";"] > counts[","] && counts[";"] >= counts["\t"] ? ";" : counts["\t"] > counts[","] ? "\t" : ",";
  }

  function splitRows(text) {
    var delimiter = delimiterOf(text);
    var rows = [], row = [], field = "", quoted = false, line = 1, start = 1;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (ch === "\n" || (ch === "\r" && text[i + 1] !== "\n")) line++;
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (ch === '"') quoted = false;
        else field += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === delimiter) {
        row.push(field); field = "";
        if (row.length > MAX_COLUMNS) throw new Error("The file has more than " + MAX_COLUMNS + " columns. Keep only the date column and one value column.");
      } else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") { i++; line++; }
        row.push(field); row.line = start; rows.push(row); row = []; field = ""; start = line;
        if (rows.length > MAX_ROWS + 1) throw new Error("The file has more than " + MAX_ROWS.toLocaleString("en-US") + " rows. A monthly series needs far fewer.");
      } else field += ch;
    }
    if (field !== "" || row.length) { row.push(field); row.line = start; rows.push(row); }
    var out = [];
    rows.forEach(function (r) {
      var cells = r.map(function (c) { return c.trim(); });
      cells.line = r.line;
      if (cells.some(function (c) { return c !== ""; })) out.push(cells);
    });
    return out;
  }

  function parseDate(s) {
    var t = s.trim(), m;
    if ((m = /^(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?(?:[T ].*)?$/.exec(t))) return ok(+m[1], +m[2]);
    if ((m = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/.exec(t))) return ok(+m[3], +m[1]);            // month first: 3/15/2024
    if ((m = /^(\d{1,2})[/-](\d{4})$/.exec(t))) return ok(+m[2], +m[1]);                           // MM/YYYY
    if ((m = /^(\d{4})\s*-?\s*Q([1-4])$/i.exec(t)) || (m = /^Q([1-4])\s*-?\s*(\d{4})$/i.exec(t))) {
      var year = m[1].length === 4 ? +m[1] : +m[2], q = m[1].length === 4 ? +m[2] : +m[1];
      return ok(year, (q - 1) * 3 + 1);
    }
    if ((m = /^([A-Za-z]{3,9})\.?\s+(\d{4})$/.exec(t)) || (m = /^([A-Za-z]{3,9})-(\d{2}|\d{4})$/.exec(t))) {
      var idx = MONTH_NAMES.indexOf(m[1].slice(0, 3).toLowerCase());
      // Two-digit years pivot at 30, as Excel does: 29 is 2029, 30 is 1930.
      var yr = m[2].length === 2 ? (+m[2] < 30 ? 2000 : 1900) + +m[2] : +m[2];
      return idx >= 0 ? ok(yr, idx + 1) : null;
    }
    return null;
    function ok(year, month) { return month >= 1 && month <= 12 && year >= 1800 && year <= 2200 ? [year, month] : null; }
  }

  // Reads 1234, 1,234.50, $1,234, (1,234) as a negative, and a minus sign. Commas are
  // thousands separators only. Anything it is not sure of is refused, never guessed.
  function parseNumber(s) {
    var t = s.trim().replace(/\u2212/g, "-"), negative = false;
    if (/^\(.*\)$/.test(t)) {
      negative = true;
      t = t.slice(1, -1).trim();
      if (/^[-+]/.test(t)) return null;                     // "(-5)" has two signs: refuse rather than guess
    }
    t = t.replace(/^([-+]?)\s*[$\u20ac\u00a3]/, "$1").replace(/[$\u20ac\u00a3]/g, "");
    t = t.replace(/\s/g, "");
    if (/^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$/.test(t)) t = t.replace(/,/g, "");
    if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t)) return null;
    var v = parseFloat(t);
    return negative ? -v : v;
  }

  function label(p) { return MONTH_NAMES[p[1] - 1].replace(/^./, function (c) { return c.toUpperCase(); }) + " " + p[0]; }

  function parse(text) {
    if (!text || !text.trim()) throw new Error("The file is empty.");
    var rows = splitRows(text.replace(/^\uFEFF/, ""));
    if (!rows.length) throw new Error("The file has no rows.");
    var width = 0, c, i;
    for (i = 0; i < rows.length; i++) if (rows[i].length > width) width = rows[i].length;
    var used = [];
    for (c = 0; c < width; c++) {
      for (i = 1; i < rows.length; i++) if ((rows[i][c] || "") !== "") { used.push(c); break; }
    }
    if (used.length < 2) throw new Error("The file needs two columns: a date and a value.");
    if (used.length > 2) throw new Error("The file has " + used.length + " columns with data. Keep only the date column and one value column.");
    // The first row is a header only if none of its cells is a number. A first data
    // row with a typo in its date is reported, not quietly dropped as a header.
    var header = parseNumber(rows[0][used[0]] || "") === null && parseNumber(rows[0][used[1]] || "") === null &&
                 parseDate(rows[0][used[0]] || "") === null && parseDate(rows[0][used[1]] || "") === null;
    var body = header ? rows.slice(1) : rows;
    var dated = function (col) { var k = 0; body.forEach(function (r) { if (parseDate(r[col] || "")) k++; }); return k; };
    var dateCol = dated(used[0]) >= dated(used[1]) ? used[0] : used[1];
    var valueCol = dateCol === used[0] ? used[1] : used[0];
    body.forEach(function (r) {                              // refuse dates whose order cannot be known
      var d = r[dateCol] || "", m;
      if (/^\d{1,2}\.\d{1,2}\.\d{4}$/.test(d) || ((m = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/.exec(d)) && +m[1] > 12)) {
        throw new Error("Row " + r.line + " has the date \u201c" + d + "\u201d, which reads as day first. Write dates as year and month, like 2024-03, so the order cannot be misread.");
      }
    });
    var points = [];
    body.forEach(function (r) {
      var line = r.line, ds = r[dateCol] || "", vs = r[valueCol] || "";
      if (ds === "") throw new Error("Row " + line + " has no date.");
      var p = parseDate(ds);
      if (!p) throw new Error("Row " + line + " has a date that could not be read: \u201c" + ds + "\u201d.");
      if (vs === "") throw new Error("Row " + line + " (" + label(p) + ") has no value.");
      var v = parseNumber(vs);
      if (v === null || !isFinite(v)) throw new Error("Row " + line + " has a value that is not a number: \u201c" + vs + "\u201d.");
      points.push({ p: p, v: v, line: line });
    });
    points.sort(function (x, y) { return monthIndex(x.p[0], x.p[1]) - monthIndex(y.p[0], y.p[1]) || x.line - y.line; });
    for (i = 1; i < points.length; i++) {
      if (monthIndex(points[i].p[0], points[i].p[1]) === monthIndex(points[i - 1].p[0], points[i - 1].p[1])) {
        throw new Error(label(points[i].p) + " appears twice, in rows " + points[i - 1].line + " and " + points[i].line +
          ". If this is daily or weekly data, total it by month first.");
      }
    }
    var periods = points.map(function (x) { return x.p; }), values = points.map(function (x) { return x.v; });
    if (periods.length < 2) throw new Error("Only " + periods.length + " row of data.");
    var step = Infinity;
    for (i = 1; i < periods.length; i++) {
      var gap = monthIndex(periods[i][0], periods[i][1]) - monthIndex(periods[i - 1][0], periods[i - 1][1]);
      if (gap < step) step = gap;
    }
    if (step !== 1 && step !== 3) throw new Error("The dates are not monthly or quarterly.");
    var missing = [];
    for (i = 1; i < periods.length; i++) {
      var from = monthIndex(periods[i - 1][0], periods[i - 1][1]), to = monthIndex(periods[i][0], periods[i][1]);
      if ((to - from) % step) throw new Error("The dates are not evenly spaced around " + label(periods[i]) + ".");
      for (var k = from + step; k < to && missing.length < 5; k += step) missing.push([Math.floor(k / 12), k % 12 + 1]);
    }
    if (missing.length) {
      throw new Error("The series has gaps: " + missing.slice(0, 4).map(label).join(", ") +
        (missing.length > 4 ? " and more" : "") + " missing. Fill or remove them first.");
    }
    var frequency = step === 1 ? "monthly" : "quarterly";
    if (values.length < MIN_POINTS[frequency]) {
      throw new Error("Only " + values.length + " " + frequency + " points. At least " + MIN_POINTS[frequency] + " are needed to see a seasonal pattern.");
    }
    return { periods: periods, values: values, frequency: frequency, header: header };
  }

  window.Autocast = { parse: parse, run: run, parseDate: parseDate, parseNumber: parseNumber,
                      analyse: function (name, text) { analyse(name, text); },
                      seasonalStrength: seasonalStrength, models: { seasonalNaive: seasonalNaive, linearTrend: linearTrend, holtWinters: holtWinters } };

  // ------------------------------------------------------------------- the UI -----
  var $ = function (id) { return document.getElementById(id); };
  var status = $("ac-status"), alertBox = $("ac-error"), results = $("ac-results"), current = null, latest = 0;

  function fmt(v) {
    if (typeof v !== "number" || !isFinite(v)) return "n/a";
    var a = Math.abs(v), d = a >= 1000 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : 4;
    return (v < 0 ? "\u2212" : "") + a.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  // Two fixed regions: progress and results in a polite status, problems in an
  // alert. Changing one element's role on the fly is not announced reliably.
  function setStatus(text, isError) {
    if (isError) {
      status.textContent = "";
      alertBox.textContent = text;
      alertBox.hidden = false;
    } else {
      alertBox.hidden = true;
      alertBox.textContent = "";
      status.textContent = text;
    }
  }
  function fail(message) { results.hidden = true; setStatus(message, true); }

  // Each analysis gets a number when its input is chosen. A slower, older one
  // never overwrites a newer result or error: a big file still being read, or a
  // sample clicked just before a bad file is dropped, must not replace the newer
  // file's message with the older forecast.
  function analyse(name, text, token, settings) {
    var mine = token === undefined ? ++latest : token, parsed;
    if (mine !== latest) return;
    try { parsed = parse(text); } catch (e) { fail(e.message); return; }
    setStatus("Read " + parsed.values.length + " " + parsed.frequency + " points from " + name + ". Testing the models\u2026", false);
    setTimeout(function () {                                    // let the status paint before the work
      if (mine !== latest) return;
      var result;
      try { result = run(parsed.periods, parsed.values, settings); } catch (e) { if (mine === latest) fail(e.message); return; }
      if (mine !== latest) return;
      current = { name: name, result: result, matchesMain: !!(settings && settings.first_origin) };
      show(current);
    }, 20);
  }

  function show(c) {
    var r = c.result, winner = r.table.filter(function (t) { return t.key === r.winner; })[0];
    var strength = r.seasonal_strength === null ? "too short to measure" :
      (r.seasonal_strength >= 0.5 ? "strong" : r.seasonal_strength >= 0.2 ? "moderate" : "weak") + " (" + r.seasonal_strength.toFixed(2) + ")";
    setStatus(c.name + ": " + r.frequency + ", " + r.points_used + " points" + (r.points_dropped ? " (the oldest " + r.points_dropped + " left out)" : "") +
      ". Winner by backtest: " + winner.name + "." +
      (c.matchesMain ? " Tested with the main forecast's settings, so it matches the Contractor scenarios tab." : ""), false);
    $("ac-freq").textContent = r.frequency.charAt(0).toUpperCase() + r.frequency.slice(1);
    $("ac-points").textContent = String(r.points_used);
    $("ac-seasonal").textContent = strength;
    $("ac-winner").textContent = winner.name;
    $("ac-origins").textContent = r.origins + " origins from " + label(r.first_origin) + ", " + r.horizon + " " +
      (r.frequency === "monthly" ? "months" : "quarters") + " ahead" +
      (r.publication_lag ? ", data known " + r.publication_lag + " " + (r.frequency === "monthly" ? "month" : "quarter") + " late" : "");
    var body = $("ac-table").querySelector("tbody");
    while (body.firstChild) body.removeChild(body.firstChild);
    r.table.forEach(function (t) {
      var tr = document.createElement("tr"), last = t.by_horizon[t.by_horizon.length - 1];
      [t.name + (t.key === r.winner ? " (winner)" : ""), t.mean_mape === null ? "not shown" : t.mean_mape.toFixed(2) + "%",
       fmt(t.mean_mae), t.by_horizon[0].folds + " to " + last.folds].forEach(function (text, i) {
        var cell = document.createElement(i ? "td" : "th");
        if (i) cell.className = "num"; else cell.setAttribute("scope", "row");
        if (t.key === r.winner) cell.classList.add("cf-win");
        cell.textContent = text;
        tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
    $("ac-mape-note").textContent = r.mape_note ? r.mape_note + " The winner is picked by MAE instead." : "";
    var fbody = $("ac-forecast").querySelector("tbody");
    while (fbody.firstChild) fbody.removeChild(fbody.firstChild);
    r.forecast.forEach(function (f) {
      var tr = document.createElement("tr");
      [label([f.year, f.month]), fmt(f.p10), fmt(f.point), fmt(f.p90)].forEach(function (text, i) {
        var cell = document.createElement(i ? "td" : "th");
        if (i) cell.className = "num"; else cell.setAttribute("scope", "row");
        cell.textContent = text;
        tr.appendChild(cell);
      });
      fbody.appendChild(tr);
    });
    results.hidden = false;                                   // visible first, so the chart can measure its width
    chart(r);
  }

  var SVGNS = "http://www.w3.org/2000/svg";
  function el(name, attrs, text) {
    var e = document.createElementNS(SVGNS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function chart(r) {
    var svg = $("ac-chart"), H = 280, W = Math.max(320, Math.min(640, Math.round(svg.parentNode.clientWidth || 640)));
    svg.setAttribute("viewBox", "0 0 " + W + " " + H); svg.setAttribute("width", W); svg.setAttribute("height", H);
    while (svg.lastChild && svg.lastChild.nodeName !== "title" && svg.lastChild.nodeName !== "desc") svg.removeChild(svg.lastChild);
    var L = 70, R = 12, T = 12, B = 34, hist = Math.min(r.values.length, 3 * r.season);
    var past = r.values.slice(r.values.length - hist), n = hist + r.forecast.length;
    var all = past.concat(r.forecast.map(function (f) { return f.p10; }), r.forecast.map(function (f) { return f.p90; }));
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), pad = (hi - lo) * 0.08 || 1;
    var y0 = lo - pad, y1 = hi + pad;
    var x = function (i) { return L + i / (n - 1) * (W - L - R); }, y = function (v) { return T + (y1 - v) / (y1 - y0) * (H - T - B); };
    for (var g = 0; g <= 4; g++) {
      var v = y0 + (y1 - y0) * g / 4;
      svg.appendChild(el("line", { "class": "ch-grid", x1: L, x2: W - R, y1: y(v).toFixed(1), y2: y(v).toFixed(1) }));
      svg.appendChild(el("text", { "class": "ch-tick", x: L - 6, y: (y(v) + 4).toFixed(1), "text-anchor": "end" }, fmt(v)));
    }
    var periods = r.periods.slice(r.periods.length - hist);
    // The last data month is labeled only when it has room between the two ends.
    var marks = x(n - 1) - x(hist - 1) > 80 && x(hist - 1) - x(0) > 80 ? [0, hist - 1, n - 1] : [0, n - 1];
    marks.forEach(function (i) {
      var p = i < hist ? periods[i] : [r.forecast[i - hist].year, r.forecast[i - hist].month];
      svg.appendChild(el("text", { "class": "ch-tick", x: x(i).toFixed(1), y: H - 10, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle" }, label(p)));
    });
    var up = [], down = [], line = [], hl = [];
    r.forecast.forEach(function (f, j) {
      var i = hist + j;
      up.push(x(i).toFixed(1) + " " + y(f.p90).toFixed(1));
      down.unshift(x(i).toFixed(1) + " " + y(f.p10).toFixed(1));
      line.push(x(i).toFixed(1) + " " + y(f.point).toFixed(1));
    });
    past.forEach(function (v, i) { hl.push(x(i).toFixed(1) + " " + y(v).toFixed(1)); });
    svg.appendChild(el("path", { "class": "cf-band", d: "M" + up.join(" L") + " L" + down.join(" L") + " Z" }));
    svg.appendChild(el("path", { "class": "ch-line cf-actual", d: "M" + hl.join(" L") }));
    svg.appendChild(el("path", { "class": "ch-line cf-scen", d: "M" + hl[hl.length - 1] + " L" + line.join(" L") }));
    var first = r.forecast[0], lastF = r.forecast[r.forecast.length - 1];
    $("ac-chart-d").textContent = "The last " + hist + " points of your data and a " + r.forecast.length + "-step forecast from " +
      label([first.year, first.month]) + " to " + label([lastF.year, lastF.month]) + ": " + fmt(first.point) + " first, " +
      fmt(lastF.point) + " last, with a P10 to P90 range of past misses from " + fmt(lastF.p10) + " to " + fmt(lastF.p90) +
      " in the last step. The numbers are in the table below.";
  }

  function download() {
    if (!current) return;
    var r = current.result, lines = ["date,forecast,p10,p50,p90,model"];
    var name = r.table.filter(function (t) { return t.key === r.winner; })[0].name;
    r.forecast.forEach(function (f) {
      lines.push(f.year + "-" + (f.month < 10 ? "0" : "") + f.month + "," + [f.point, f.p10, f.p50, f.p90].map(function (v) { return String(v); }).join(",") +
        ",\"" + name + "\"");
    });
    var url = URL.createObjectURL(new Blob([lines.join("\r\n") + "\r\n"], { type: "text/csv" }));
    var a = document.createElement("a");
    a.href = url; a.download = "forecast.csv";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function readFile(file) {
    if (!file) return;
    var mine = ++latest;
    if (file.size > MAX_BYTES) { fail("The file is larger than 5 MB. A monthly series fits in far less."); return; }
    var reader = new FileReader();
    reader.onload = function () { analyse(file.name, String(reader.result), mine); };
    reader.onerror = function () { if (mine === latest) fail("The file could not be read."); };
    reader.readAsText(file);
  }

  // Redraw at the new width when the panel's width changes (a rotated phone, a resized window).
  var lastWidth = root.clientWidth, resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      if (current && !results.hidden && root.clientWidth !== lastWidth) { lastWidth = root.clientWidth; chart(current.result); }
    }, 150);
  });

  $("ac-file").addEventListener("change", function (e) {
    var file = e.target.files[0];
    e.target.value = "";                                       // so choosing the same file again, once fixed, reads it again
    readFile(file);
  });
  var zone = $("ac-drop");
  ["dragenter", "dragover"].forEach(function (t) { zone.addEventListener(t, function (e) { e.preventDefault(); zone.classList.add("is-over"); }); });
  ["dragleave", "drop"].forEach(function (t) { zone.addEventListener(t, function (e) { e.preventDefault(); zone.classList.remove("is-over"); }); });
  zone.addEventListener("drop", function (e) { readFile(e.dataTransfer && e.dataTransfer.files[0]); });
  $("ac-download").addEventListener("click", download);

  var sampleRow = $("ac-samples");
  (D.samples || []).forEach(function (s) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "preset"; b.dataset.sample = s.key;
    b.textContent = s.label;
    b.addEventListener("click", function () {
      var csv = ["date,value"].concat(s.dates.map(function (d, i) { return d + "," + s.values[i]; })).join("\n");
      analyse(s.label + " (FRED " + s.series_id + ")", csv, undefined, s.settings || undefined);
    });
    sampleRow.appendChild(b);
  });

  // ------------------------------------------------------------------- tabs -----
  var tabs = Array.prototype.slice.call(document.querySelectorAll("#cf-tabs [role=tab]"));
  function select(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
    // A chart drawn while its tab was hidden measured no width. Redraw on showing it.
    if (tab.getAttribute("aria-controls") === "ac" && current && !results.hidden) chart(current.result);
    if (focus) tab.focus();
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { select(t, false); });
    t.addEventListener("keydown", function (e) {
      var k = e.key, next = k === "ArrowRight" ? i + 1 : k === "ArrowLeft" ? i - 1 : k === "Home" ? 0 : k === "End" ? tabs.length - 1 : null;
      if (next === null) return;
      e.preventDefault();
      select(tabs[(next + tabs.length) % tabs.length], true);
    });
  });
  var bar = document.getElementById("cf-tabs");
  if (bar) bar.hidden = false;                                 // tabs only make sense with this script running
})();
