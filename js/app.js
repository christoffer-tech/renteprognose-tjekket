/* Renteprognose-tjekket – dashboard. Henter data/dataset.json og tegner grafer. */
(function () {
  "use strict";

  var MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun",
                "jul", "aug", "sep", "okt", "nov", "dec"];

  function parseDate(s) {
    var p = s.split("-");
    return new Date(+p[0], +p[1] - 1, +p[2]).getTime();
  }
  function fmtDate(ms) {
    var d = new Date(ms);
    return MONTHS[d.getMonth()] + " " + d.getFullYear();
  }
  function fmtDateFull(ms) {
    var d = new Date(ms);
    return d.getDate() + ". " + MONTHS[d.getMonth()] + " " + d.getFullYear();
  }
  function fmtPct(v, digits) {
    if (v === null || v === undefined) return "–";
    return v.toFixed(digits === undefined ? 2 : digits).replace(".", ",") + " %";
  }
  function fmtSigned(v, digits) {
    if (v === null || v === undefined) return "–";
    var s = v.toFixed(digits === undefined ? 2 : digits).replace(".", ",");
    return (v > 0 ? "+" : "") + s + " pp";
  }
  function fmtShare(v) {
    if (v === null || v === undefined) return "–";
    return Math.round(v * 100) + " %";
  }

  var todayLine = {
    id: "todayLine",
    afterDraw: function (chart) {
      var x = chart.scales.x;
      var now = Date.now();
      if (now < x.min || now > x.max) return;
      var px = x.getPixelForValue(now);
      var area = chart.chartArea;
      var ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = "rgba(74,82,92,.6)";
      ctx.setLineDash([5, 4]);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(px, area.top);
      ctx.lineTo(px, area.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(74,82,92,.95)";
      ctx.font = "11px sans-serif";
      ctx.fillText("i dag", px + 5, area.top + 12);
      ctx.restore();
    }
  };

  /* På smalle skærme overlapper datoetiketterne, så vi viser færre. */
  function tickLimit() {
    var w = (typeof window !== "undefined" && window.innerWidth) || 1200;
    return w <= 620 ? 4 : w <= 900 ? 6 : 9;
  }

  function xScale(extra) {
    return Object.assign({
      type: "linear",
      ticks: {
        maxTicksLimit: tickLimit(),
        callback: function (v) { return fmtDate(v); }
      },
      grid: { color: "rgba(18,22,27,.08)" }
    }, extra || {});
  }

  var state = { data: null, product: null, showAll: true, charts: {}, bank: "nykredit",
                period: "all", overlapStart: null };

  /* ---------- periode-filter ---------- */
  function isoDate(d) {
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }
  function windowStart() {
    if (state.period === "all") return null;
    if (state.period === "overlap") return state.overlapStart;
    var d = new Date();
    d.setFullYear(d.getFullYear() - (state.period === "1y" ? 1 : 3));
    return isoDate(d);
  }
  function inWin(pub) {
    var s = windowStart();
    return !s || pub >= s;
  }
  function jsSummarize(errors) {
    var n = errors.length;
    if (!n) return { n: 0, bias: null, mae: null, rmse: null, opt_share: null, pess_share: null };
    function r3(v) { return Math.round(v * 1000) / 1000; }
    var sum = 0, ae = 0, se = 0, opt = 0, pess = 0;
    errors.forEach(function (e) {
      sum += e; ae += Math.abs(e); se += e * e;
      if (e > 0) opt++; else if (e < 0) pess++;
    });
    return { n: n, bias: r3(sum / n), mae: r3(ae / n), rmse: r3(Math.sqrt(se / n)),
             opt_share: r3(opt / n), pess_share: r3(pess / n) };
  }
  function setEmpty(key, empty) {
    var c = document.getElementById("chart-" + key);
    var e = document.getElementById("empty-" + key);
    if (c) c.style.display = empty ? "none" : "";
    if (e) e.hidden = !empty;
    if (empty) destroyChart(key);
  }

  function destroyChart(key) {
    if (state.charts[key]) { state.charts[key].destroy(); delete state.charts[key]; }
  }

  /* ---------- hero ---------- */
  function heroPoints() {
    return state.data.points.filter(function (p) {
      return p.err !== null && inWin(p.pub);
    });
  }
  function renderHero() {
    var d = state.data;
    var pts = heroPoints();
    var o = jsSummarize(pts.map(function (p) { return p.err; }));
    var biasEl = document.getElementById("stat-bias");
    biasEl.textContent = fmtSigned(o.bias);
    biasEl.className = "stat-value " + (o.bias > 0 ? "pos" : "neg");
    document.getElementById("stat-opt").textContent = fmtShare(o.opt_share);
    document.getElementById("stat-pess").textContent = fmtShare(o.pess_share);
    document.getElementById("stat-n").textContent = o.n || "–";
    var pubs = pts.map(function (p) { return p.pub; });
    var pubMs = pubs.map(parseDate);
    document.getElementById("stat-period").textContent = pubs.length
      ? "prognoser fra " + fmtDate(Math.min.apply(null, pubMs)) +
        " til " + fmtDate(Math.max.apply(null, pubMs))
      : "ingen prognoser i perioden";

    var worst = null;
    pts.forEach(function (p) {
      if (!worst || Math.abs(p.err) > Math.abs(worst.err)) worst = p;
    });
    if (worst) {
      document.getElementById("stat-worst").textContent = fmtSigned(worst.err);
      document.getElementById("stat-worst-sub").textContent =
        d.labels[worst.p] + ", " + fmtDate(parseDate(worst.pub)) +
        " → " + fmtDate(parseDate(worst.target)) +
        " (spået " + fmtPct(worst.fc) + ", facit " + fmtPct(worst.act) + ")";
    }

    var clamped = Math.max(-1, Math.min(1, o.bias || 0));
    document.getElementById("meter-marker").style.left = ((clamped + 1) / 2 * 100) + "%";

    var g = new Date(d.meta.generated);
    function pad2(n) { return (n < 10 ? "0" : "") + n; }
    document.getElementById("last-updated").textContent =
      g.getDate() + ". " + MONTHS[g.getMonth()] + " " + g.getFullYear() +
      " kl. " + pad2(g.getHours()) + ":" + pad2(g.getMinutes());
  }

  /* ---------- produktfaner ---------- */
  function renderTabs(d) {
    var box = document.getElementById("product-tabs");
    box.innerHTML = "";
    d.order.forEach(function (p) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = d.labels[p];
      b.setAttribute("role", "tab");
      if (p === state.product) b.className = "active";
      b.addEventListener("click", function () {
        state.product = p;
        var btns = box.querySelectorAll("button");
        for (var i = 0; i < btns.length; i++) btns[i].className = "";
        b.className = "active";
        renderProduct();
      });
      box.appendChild(b);
    });
  }

  function vintagesFor(d, p) {
    var map = {};
    d.points.forEach(function (pt) {
      if (pt.p !== p) return;
      (map[pt.pub] = map[pt.pub] || []).push(pt);
    });
    var pubs = Object.keys(map).sort();
    pubs.forEach(function (k) {
      map[k].sort(function (a, b) { return a.target < b.target ? -1 : 1; });
    });
    return pubs.map(function (k) { return { pub: k, pts: map[k] }; });
  }

  function anchorFor(d, p, pub) {
    var s = d.anchors[p] || d.actuals[p] || [];
    for (var i = 0; i < s.length; i++) {
      if (s[i][0] === pub) return s[i][1];
    }
    return null;
  }

  /* ---------- hovedgraf ---------- */
  function renderMain(d, p) {
    destroyChart("main");
    var vints = vintagesFor(d, p).filter(function (v) { return inWin(v.pub); });
    if (!state.showAll) vints = vints.slice(-6);
    if (!vints.length) {
      setEmpty("main", true);
      document.getElementById("chart-title").textContent =
        d.labels[p] + " – alle prognoser mod facit (%)";
      return;
    }
    setEmpty("main", false);

    var datasets = vints.map(function (v) {
      var anchor = anchorFor(d, p, v.pub);
      var pts = [];
      if (anchor !== null) pts.push({ x: parseDate(v.pub), y: anchor });
      v.pts.forEach(function (pt) { pts.push({ x: parseDate(pt.target), y: pt.fc }); });
      return {
        label: "Prognose " + fmtDate(parseDate(v.pub)),
        data: pts,
        borderColor: "rgba(18,58,99,.30)",
        backgroundColor: "rgba(18,58,99,.30)",
        borderWidth: 1.2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0
      };
    });

    var actual = (d.actuals[p] || []).map(function (a) {
      return { x: parseDate(a[0]), y: a[1] };
    });
    datasets.push({
      label: "Facit (faktisk rente)",
      data: actual,
      borderColor: "#12161B",
      backgroundColor: "#12161B",
      borderWidth: 2.6,
      pointRadius: 3,
      pointHoverRadius: 5,
      tension: 0.15
    });

    document.getElementById("chart-title").textContent =
      d.labels[p] + " – alle prognoser mod facit (%)";

    var allX = [];
    datasets.forEach(function (ds) {
      ds.data.forEach(function (pt) { allX.push(pt.x); });
    });
    var DAY = 86400000;
    var ws = windowStart();
    var xMin = ws ? parseDate(ws) : Math.min.apply(null, allX) - 20 * DAY;
    var xMax = Math.max.apply(null, allX.concat([Date.now()])) + 40 * DAY;

    var ctx = document.getElementById("chart-main");
    state.charts.main = new Chart(ctx, {
      type: "line",
      data: { datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) { return items[0].dataset.label; },
              label: function (item) {
                return fmtDateFull(item.parsed.x) + ": " + fmtPct(item.parsed.y);
              }
            }
          }
        },
        scales: {
          x: xScale({ min: xMin, max: xMax }),
          y: {
            title: { display: true, text: "% p.a." },
            ticks: { callback: function (v) {
              return (Math.round(v * 100) / 100).toString().replace(".", ",");
            } },
            grid: { color: "rgba(18,22,27,.08)" }
          }
        }
      },
      plugins: [todayLine]
    });
  }

  /* ---------- fejlgraf ---------- */
  function renderError(d, p) {
    destroyChart("error");
    var colors = [], pts = [];
    d.points.forEach(function (pt) {
      if (pt.p !== p || pt.err === null || !inWin(pt.pub)) return;
      pts.push({ x: parseDate(pt.target), y: pt.err, pub: pt.pub, fc: pt.fc, act: pt.act });
      colors.push(pt.err > 0 ? "rgba(192,57,43,.78)" : pt.err < 0 ? "rgba(30,125,70,.78)" : "rgba(122,131,142,.75)");
    });
    if (!pts.length) { setEmpty("error", true); return; }
    setEmpty("error", false);
    var ys = pts.map(function (q) { return q.y; });
    function niceFloor(v) { return Math.floor(v * 2) / 2; }
    function niceCeil(v) { return Math.ceil(v * 2) / 2; }
    var yMin = niceFloor(Math.min.apply(null, ys.concat([0])) - 0.25);
    var yMax = niceCeil(Math.max.apply(null, ys.concat([0])) + 0.25);
    function fmtTick(v) {
      var s = (Math.round(v * 100) / 100).toString().replace(".", ",");
      return (v > 0 ? "+" : "") + s;
    }
    var exMin = Math.min.apply(null, pts.map(function (q) { return q.x; }));
    var exMax = Math.max.apply(null, pts.map(function (q) { return q.x; }));
    var DAY = 86400000;
    var zero = {
      label: "nul",
      data: [{ x: exMin, y: 0 }, { x: exMax, y: 0 }],
      borderColor: "rgba(18,22,27,.55)", borderWidth: 1.4, pointRadius: 0,
      borderDash: [6, 4]
    };
    var ctx = document.getElementById("chart-error");
    state.charts.error = new Chart(ctx, {
      type: "scatter",
      data: { datasets: [zero, {
        label: "Prognosefejl",
        data: pts,
        backgroundColor: colors,
        borderColor: colors,
        pointRadius: 5,
        pointHoverRadius: 7
      }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) {
                var q = items[0].raw;
                return "Mål: " + fmtDateFull(q.x) + " (spået " + fmtDate(parseDate(q.pub)) + ")";
              },
              label: function (item) {
                var q = item.raw;
                return ["Prognose: " + fmtPct(q.fc), "Facit: " + fmtPct(q.act),
                        "Fejl: " + fmtSigned(q.y)];
              }
            }
          }
        },
        scales: {
          x: xScale({ min: exMin - 20 * DAY, max: exMax + 20 * DAY }),
          y: {
            min: yMin,
            max: yMax,
            title: { display: true, text: "Fejl i procentpoint" },
            ticks: { callback: fmtTick },
            grid: { color: "rgba(18,22,27,.08)" }
          }
        }
      }
    });
  }

  /* ---------- horisontgraf ---------- */
  function renderHorizon(d, p) {
    destroyChart("horizon");
    var hs = ["3M", "6M", "9M", "12M"];
    var names = { "3M": "3 mdr", "6M": "6 mdr", "9M": "9 mdr", "12M": "12 mdr" };
    var m = {};
    hs.forEach(function (h) {
      var errs = d.points
        .filter(function (pt) { return pt.p === p && pt.h === h && pt.err !== null && inWin(pt.pub); })
        .map(function (pt) { return pt.err; });
      m[h] = jsSummarize(errs);
    });
    var hasData = hs.some(function (h) { return m[h].n > 0; });
    if (!hasData) { setEmpty("horizon", true); return; }
    setEmpty("horizon", false);
    var vals = hs.map(function (h) { return m[h].n ? m[h].bias : 0; });
    var ctx = document.getElementById("chart-horizon");
    state.charts.horizon = new Chart(ctx, {
      type: "bar",
      data: {
        labels: hs.map(function (h) { return names[h]; }),
        datasets: [{
          label: "Gns. fejl (pp)",
          data: vals,
          backgroundColor: vals.map(function (v) {
            return v >= 0 ? "rgba(192,57,43,.85)" : "rgba(30,125,70,.85)";
          })
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (item) {
                var h = hs[item.dataIndex];
                return "Bias: " + fmtSigned(item.parsed.y) + " (n=" + m[h].n + ")";
              }
            }
          }
        },
        scales: {
          y: {
            title: { display: true, text: "Gns. fejl i procentpoint" },
            ticks: { callback: function (v) {
              var s = (Math.round(v * 100) / 100).toString().replace(".", ",");
              return (v > 0 ? "+" : "") + s;
            } },
            grid: { color: "rgba(18,22,27,.08)" }
          },
          x: { grid: { display: false } }
        }
      }
    });
  }

  function renderProduct() {
    if (!state.data || !state.product) return;
    renderMain(state.data, state.product);
    renderError(state.data, state.product);
    renderHorizon(state.data, state.product);
  }

  /* ---------- scoreboard ---------- */
  function renderScore() {
    var d = state.data;
    var h = document.getElementById("horizon-select").value;
    var tb = document.querySelector("#score-table tbody");
    tb.innerHTML = "";
    var hName = { alle: "alle horisonter", "3M": "3 mdr", "6M": "6 mdr",
                  "9M": "9 mdr", "12M": "12 mdr" }[h];
    d.order.forEach(function (p) {
      var m = jsSummarize(d.points
        .filter(function (pt) {
          return pt.p === p && pt.err !== null && inWin(pt.pub) &&
                 (h === "alle" || pt.h === h);
        })
        .map(function (pt) { return pt.err; }));
      var tr = document.createElement("tr");
      var biasCls = m.bias === null || m.bias === undefined ? "" :
                    (m.bias > 0 ? "bias-pos" : m.bias < 0 ? "bias-neg" : "");
      tr.innerHTML =
        "<td></td><td></td><td></td><td></td><td></td><td></td>";
      var cells = tr.querySelectorAll("td");
      cells[0].textContent = d.labels[p];
      cells[1].textContent = m.n || "–";
      cells[2].textContent = fmtSigned(m.bias);
      cells[2].className = biasCls;
      cells[3].textContent = m.mae === null || m.mae === undefined ? "–" : fmtPct(m.mae).replace(" %", "");
      cells[4].textContent = fmtShare(m.opt_share);
      cells[5].textContent = fmtShare(m.pess_share);
      tb.appendChild(tr);
    });
    document.getElementById("score-note").textContent =
      "Horisont: " + hName + ". Positiv gns. fejl (rød) = renten endte i snit højere end spået, " +
      "altså for optimistiske prognoser. Negativ (grøn) = for pessimistiske.";
  }

  /* ---------- CSV-download (alle banker) ---------- */
  function downloadCSV() {
    var rows = [["bank", "produkt", "prognosedato", "maldato", "horisont",
                 "prognose_pct", "prognose_min", "prognose_maks",
                 "facit_pct", "facit_dato", "fejl_pp", "ramt_interval"]];
    function num(v) { return v === null || v === undefined ? "" : String(v).replace(".", ","); }
    var bankName = { nykredit: "Nykredit", nordea: "Nordea", sydbank: "Sydbank",
                     jyske: "Jyske Bank", rd: "Realkredit Danmark",
                     sparkron: "Sparekassen Kronjylland" };
    var all = state.cmp.bankData && Object.keys(state.cmp.bankData).length
      ? state.cmp.bankData : { nykredit: state.data };
    Object.keys(all).forEach(function (b) {
      var d = all[b];
      if (!d) return;
      d.points.forEach(function (pt) {
        rows.push([bankName[b] || b, d.labels[pt.p], pt.pub, pt.target, pt.h,
                   num(pt.fc), num(pt.fc_lo), num(pt.fc_hi),
                   num(pt.act), pt.act_date || "", num(pt.err),
                   pt.hit === null || pt.hit === undefined ? "" : (pt.hit ? "ja" : "nej")]);
      });
    });
    var csv = rows.map(function (r) { return r.join(";"); }).join("\r\n");
    var blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "renteprognose-data.csv";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 500);
  }

  /* ---------- bank-sammenligning ---------- */
  state.cmp = { comparison: null, bankData: {}, product: "F5", horizon: "3M" };

  function bankPath(b) {
    return b === "nykredit" ? "data/dataset.json" : "data/banks/" + b + "/dataset.json";
  }

  function cmpPoints(bank, canon, h) {
    var d = state.cmp.bankData[bank];
    var cmp = state.cmp.comparison;
    if (!d || !cmp) return [];
    var prods = [];
    Object.keys(cmp.mapping[bank] || {}).forEach(function (bp) {
      if (cmp.mapping[bank][bp] === canon) prods.push(bp);
    });
    return d.points.filter(function (pt) {
      return prods.indexOf(pt.p) !== -1 && pt.h === h && pt.err !== null && inWin(pt.pub);
    });
  }

  var CMP_MIN_N = 3, CMP_MIN_CELLS = 3;
  var CMP_HORIZONS = ["3M", "6M", "9M", "12M"];

  var cmpCache = { key: null, value: null };

  /* Nøgle for de input der kan ændre beregningen. overlapStart beregnes efter
     dataene er hentet, så den indgår for at undgå et for tidligt cache-hit. */
  function cmpKey() {
    return [state.period, state.overlapStart,
            Object.keys(state.cmp.bankData).length].join("|");
  }

  /* Fælles indgang til sammenligningen. Uden periodefilter er
     comparison.json allerede regnet færdig af scraper/compare.py - så
     genbruger vi den i stedet for at gentage rangeringen i JS (og risikerer
     at de to implementationer glider fra hinanden). Er der filtreret, eller
     mangler den præcomputerede version, regner vi selv - én gang pr. filter. */
  function comparison() {
    var cmp = state.cmp.comparison;
    if (!cmp) return null;
    var key = cmpKey();
    if (cmpCache.key === key) return cmpCache.value;

    var filtered = state.period !== "all" &&
      (state.period === "overlap" ? state.overlapStart !== null : true);
    var value;
    if (!filtered && cmp.cells && cmp.championship) {
      value = { cells: cmp.cells, championship: cmp.championship,
                biasTable: cmp.bias_table, rdHitrate: cmp.rd_hitrate,
                overall: cmp.overall };
    } else {
      value = computeComparison();
    }
    cmpCache.key = key;
    cmpCache.value = value;
    return value;
  }

  /* Genberegner hele sammenligningen ud fra punkter i det valgte vindue.
     Bruges kun når periode-filteret er aktivt - uden filter genbruger
     comparison() de færdige tal fra scraper/compare.py. Logikken her spejler
     compare.py, så de to skal holdes i takt. */
  function computeComparison() {
    var cmp = state.cmp.comparison;
    function r2(v) { return Math.round(v * 100) / 100; }

    var cells = [], rankPts = {}, overall = {}, biasTable = {}, rdHits = {};
    Object.keys(cmp.banks).forEach(function (b) { rankPts[b] = []; });
    ["3M", "6M", "9M", "12M"].forEach(function (h) { rdHits[h] = []; });

    // fejl pr. (kanonisk produkt, horisont, bank). Podie-overall bruger ALLE
    // bankens prognoser (som dataset-overall), ikke kun sammenlignelige produkter.
    var byCell = {};
    Object.keys(cmp.banks).forEach(function (b) {
      var d = state.cmp.bankData[b];
      if (!d) return;
      var map = cmp.mapping[b] || {};
      var allErrs = [];
      d.points.forEach(function (pt) {
        if (pt.err === null || !inWin(pt.pub)) return;
        allErrs.push(pt.err);
        if (!map[pt.p] || CMP_HORIZONS.indexOf(pt.h) === -1) return;
        var k = map[pt.p] + "|" + pt.h;
        ((byCell[k] = byCell[k] || {})[b] = byCell[k][b] || []).push(pt.err);
      });
      overall[b] = jsSummarize(allErrs);
      var pubs = d.points
        .filter(function (pt) { return pt.err !== null && inWin(pt.pub); })
        .map(function (pt) { return pt.pub; });
      overall[b].period = pubs.length
        ? [pubs.reduce(function (a, x) { return a < x ? a : x; }),
           pubs.reduce(function (a, x) { return a > x ? a : x; })] : [null, null];
    });

    Object.keys(byCell).sort().forEach(function (k) {
      var parts = k.split("|");
      var eligible = Object.keys(byCell[k]).filter(function (b) {
        return byCell[k][b].length >= CMP_MIN_N;
      });
      if (eligible.length < 2) return;
      var stats = {};
      eligible.forEach(function (b) { stats[b] = jsSummarize(byCell[k][b]); });
      var ranking = eligible.slice().sort(function (a, b) {
        return stats[a].mae - stats[b].mae;
      });
      ranking.forEach(function (b, i) { rankPts[b].push(i + 1); });
      cells.push({ product: parts[0], horizon: parts[1], banks: stats, ranking: ranking });
    });

    var championship = Object.keys(rankPts)
      .filter(function (b) { return rankPts[b].length >= CMP_MIN_CELLS; })
      .map(function (b) {
        var rp = rankPts[b];
        var mean = rp.reduce(function (a, x) { return a + x; }, 0) / rp.length;
        return { bank: b, mean_rank: r2(mean), cells: rp.length,
                 wins: rp.filter(function (r) { return r === 1; }).length };
      })
      .sort(function (a, b) {
        return a.mean_rank - b.mean_rank || b.wins - a.wins;
      });

    // samlet bias over F3+F5
    Object.keys(cmp.banks).forEach(function (b) {
      var d = state.cmp.bankData[b];
      if (!d) { biasTable[b] = jsSummarize([]); biasTable[b].period = [null, null]; return; }
      var map = cmp.mapping[b] || {};
      var errs = [], pubs = [];
      d.points.forEach(function (pt) {
        if (pt.err === null || !inWin(pt.pub)) return;
        // Perioden dækker bankens data i vinduet - samme definition som i
        // scraper/compare.py, hvor den ikke er begrænset til F3/F5.
        pubs.push(pt.pub);
        var c = map[pt.p];
        if ((c === "F3" || c === "F5") && CMP_HORIZONS.indexOf(pt.h) !== -1) {
          errs.push(pt.err);
        }
      });
      biasTable[b] = jsSummarize(errs);
      biasTable[b].period = pubs.length
        ? [pubs.reduce(function (a, x) { return a < x ? a : x; }),
           pubs.reduce(function (a, x) { return a > x ? a : x; })] : [null, null];
    });

    // RD hit-rate
    var rdd = state.cmp.bankData.rd;
    if (rdd) {
      rdd.points.forEach(function (pt) {
        if ((pt.p === "f1" || pt.p === "f3" || pt.p === "f5") && pt.hit !== null &&
            pt.hit !== undefined && inWin(pt.pub) && rdHits[pt.h]) {
          rdHits[pt.h].push(pt.hit);
        }
      });
    }
    var rdHitrate = {};
    Object.keys(rdHits).forEach(function (h) {
      if (rdHits[h].length) {
        var nHit = rdHits[h].filter(function (x) { return x; }).length;
        rdHitrate[h] = { n: rdHits[h].length, hit_rate: r2(nHit / rdHits[h].length) };
      }
    });

    return { cells: cells, championship: championship, biasTable: biasTable,
             rdHitrate: rdHitrate, overall: overall };
  }

  function renderChamp() {
    var cmp = state.cmp.comparison;
    var cc = comparison();
    var tb = document.querySelector("#champ-table tbody");
    tb.innerHTML = "";
    cc.championship.forEach(function (c, i) {
      var b = c.bank;
      var bias = cc.biasTable[b] || {};
      var tr = document.createElement("tr");
      var period = bias.period && bias.period[0]
        ? fmtDate(parseDate(bias.period[0])) + " – " + fmtDate(parseDate(bias.period[1])) : "–";
      var bHtml = (i === 0 ? "<span class='champ-winner'>" : "<span>") +
        cmp.banks[b].label + "</span>";
      tr.innerHTML = "<td></td><td></td><td></td><td></td><td></td><td></td><td></td>";
      var tds = tr.querySelectorAll("td");
      tds[0].textContent = (i + 1) + ".";
      tds[1].innerHTML = bHtml;
      tds[2].textContent = String(c.mean_rank).replace(".", ",");
      tds[3].textContent = c.cells;
      tds[4].textContent = c.wins;
      tds[5].textContent = fmtSigned(bias.bias);
      tds[5].className = bias.bias > 0 ? "bias-pos" : bias.bias < 0 ? "bias-neg" : "";
      tds[6].textContent = period;
      tb.appendChild(tr);
    });
    var missing = Object.keys(cmp.banks).filter(function (b) {
      return !cc.championship.some(function (c) { return c.bank === b; });
    }).map(function (b) { return cmp.banks[b].label; });
    var lead = cc.championship.length ? cmp.banks[cc.championship[0].bank].label : "–";
    document.getElementById("champ-explain").textContent =
      "Mesterskabet dækker " + cc.cells.length + " discipliner (produkt × horisont, " +
      "min. 2 banker). " + lead + " fører." +
      (missing.length ? " Uden for mesterskabet (for få data i perioden): " + missing.join(", ") + "." : "");
  }

  function buildCmpProducts() {
    var cmp = state.cmp.comparison;
    var seen = {};
    comparison().cells.forEach(function (c) { seen[c.product] = true; });
    var sel = document.getElementById("cmp-product");
    sel.innerHTML = "";
    Object.keys(seen).sort().forEach(function (p) {
      var o = document.createElement("option");
      o.value = p;
      o.textContent = cmp.canonical_labels[p] || p;
      sel.appendChild(o);
    });
    if (seen[state.cmp.product]) sel.value = state.cmp.product;
    else { state.cmp.product = sel.value; }
  }

  function renderCompareChart() {
    destroyChart("compare");
    var cmp = state.cmp.comparison;
    var P = state.cmp.product, H = state.cmp.horizon;
    var datasets = [];
    var allX = [];
    Object.keys(cmp.banks).forEach(function (b) {
      var pts = cmpPoints(b, P, H).map(function (pt) {
        return { x: parseDate(pt.target), y: pt.err, pub: pt.pub,
                 fc: pt.fc, lo: pt.fc_lo, hi: pt.fc_hi, act: pt.act, hit: pt.hit };
      });
      if (!pts.length) return;
      pts.forEach(function (q) { allX.push(q.x); });
      datasets.push({
        label: cmp.banks[b].label,
        data: pts,
        backgroundColor: cmp.banks[b].color,
        borderColor: cmp.banks[b].color,
        pointRadius: 5,
        pointHoverRadius: 7
      });
    });
    var ys = [];
    datasets.forEach(function (ds) { ds.data.forEach(function (q) { ys.push(q.y); }); });
    if (!datasets.length) { setEmpty("compare", true); return; }
    setEmpty("compare", false);
    function niceFloor(v) { return Math.floor(v * 2) / 2; }
    function niceCeil(v) { return Math.ceil(v * 2) / 2; }
    var DAY = 86400000;
    var ctx = document.getElementById("chart-compare");
    state.charts.compare = new Chart(ctx, {
      type: "scatter",
      data: { datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) {
                var q = items[0].raw;
                return items[0].dataset.label + " → mål " + fmtDateFull(q.x);
              },
              label: function (item) {
                var q = item.raw;
                var lines = ["Spået " + fmtDate(parseDate(q.pub)) + ": " + fmtPct(q.fc)];
                if (q.lo !== null && q.lo !== undefined)
                  lines.push("Interval: " + fmtPct(q.lo) + " – " + fmtPct(q.hi) +
                    (q.hit ? " (ramt)" : " (forbi)"));
                lines.push("Facit: " + fmtPct(q.act));
                lines.push("Fejl: " + fmtSigned(q.y));
                return lines;
              }
            }
          }
        },
        scales: {
          x: xScale(allX.length ? {
            min: Math.min.apply(null, allX) - 20 * DAY,
            max: Math.max.apply(null, allX) + 20 * DAY
          } : {}),
          y: {
            min: ys.length ? niceFloor(Math.min.apply(null, ys.concat([0])) - 0.25) : -1,
            max: ys.length ? niceCeil(Math.max.apply(null, ys.concat([0])) + 0.25) : 1,
            title: { display: true, text: "Fejl i procentpoint" },
            grid: { color: "rgba(18,22,27,.08)" }
          }
        }
      }
    });
    var lg = document.getElementById("cmp-legend");
    lg.innerHTML = "";
    datasets.forEach(function (ds) {
      var s = document.createElement("span");
      var i = document.createElement("i");
      i.style.background = ds.backgroundColor;
      s.appendChild(i);
      s.appendChild(document.createTextNode(ds.label + " (" + ds.data.length + ")"));
      lg.appendChild(s);
    });
  }

  function renderCellTable() {
    var cmp = state.cmp.comparison;
    var P = state.cmp.product, H = state.cmp.horizon;
    var cell = null;
    comparison().cells.forEach(function (c) {
      if (c.product === P && c.horizon === H) cell = c;
    });
    var hName = { "3M": "3 mdr.", "6M": "6 mdr.", "9M": "9 mdr.", "12M": "12 mdr." }[H];
    document.getElementById("cell-title").textContent =
      "– " + (cmp.canonical_labels[P] || P) + ", " + hName;
    var tb = document.querySelector("#cell-table tbody");
    tb.innerHTML = "";
    if (!cell) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td colspan='6'>Ingen disciplin endnu – for få datapunkter i denne kombination.</td>";
      tb.appendChild(tr);
      return;
    }
    cell.ranking.forEach(function (b, i) {
      var m = cell.banks[b];
      var r = document.createElement("tr");
      r.innerHTML = "<td></td><td></td><td></td><td></td><td></td><td></td><td></td>";
      var tds = r.querySelectorAll("td");
      tds[0].textContent = (i + 1) + ".";
      tds[1].textContent = cmp.banks[b].label;
      tds[2].textContent = m.n;
      tds[3].textContent = m.mae === null ? "–" : String(m.mae).replace(".", ",");
      tds[4].textContent = fmtSigned(m.bias);
      tds[4].className = m.bias > 0 ? "bias-pos" : m.bias < 0 ? "bias-neg" : "";
      tds[5].textContent = fmtShare(m.opt_share);
      tds[6].textContent = fmtShare(m.pess_share);
      tb.appendChild(r);
    });
  }

  function renderHitrate() {
    destroyChart("hitrate");
    var cmp = state.cmp.comparison;
    var rdHitrate = comparison().rdHitrate;
    var order = { "3M": 0, "6M": 1, "9M": 2, "12M": 3 };
    var hs = Object.keys(rdHitrate).sort(function (a, b) {
      return (order[a] === undefined ? 9 : order[a]) - (order[b] === undefined ? 9 : order[b]);
    });
    if (!hs.length) { setEmpty("hitrate", true); return; }
    setEmpty("hitrate", false);
    var hName = { "3M": "3 mdr.", "6M": "6 mdr.", "9M": "9 mdr.", "12M": "12 mdr." };
    var ctx = document.getElementById("chart-hitrate");
    state.charts.hitrate = new Chart(ctx, {
      type: "bar",
      data: {
        labels: hs.map(function (h) { return hName[h] || h; }),
        datasets: [{
          label: "Hit-rate",
          data: hs.map(function (h) { return Math.round(rdHitrate[h].hit_rate * 100); }),
          backgroundColor: "rgba(18,58,99,.85)"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (item) {
                var h = hs[item.dataIndex];
                return item.parsed.y + " % ramt (n=" + rdHitrate[h].n + ")";
              }
            }
          }
        },
        scales: {
          y: { min: 0, max: 100, title: { display: true, text: "% facit i intervallet" },
               grid: { color: "rgba(18,22,27,.08)" } },
          x: { grid: { display: false } }
        }
      }
    });
  }

  function renderCompareAll() {
    buildCmpProducts();
    renderCompareChart();
    renderCellTable();
  }

  /* ---------- periode-filter ---------- */
  function computeOverlapStart() {
    var starts = [];
    Object.keys(state.cmp.bankData).forEach(function (b) {
      var pubs = state.cmp.bankData[b].points
        .filter(function (pt) { return pt.err !== null; })
        .map(function (pt) { return pt.pub; });
      if (pubs.length) {
        starts.push(pubs.reduce(function (a, x) { return a < x ? a : x; }));
      }
    });
    state.overlapStart = starts.length
      ? starts.reduce(function (a, x) { return a > x ? a : x; }) : null;
  }

  function updatePeriodLabel() {
    var el = document.getElementById("period-window");
    if (!el) return;
    var s = windowStart();
    if (!s) { el.textContent = "Viser alle prognoser."; return; }
    var txt = "Viser prognoser spået efter " + fmtDateFull(parseDate(s));
    if (state.period === "overlap") txt += " (fælles start for alle banker)";
    el.textContent = txt + ".";
  }

  function renderAll() {
    updatePeriodLabel();
    renderHero();
    renderProduct();
    renderScore();
    renderPodium();
    renderChamp();
    renderCompareAll();
    renderHitrate();
  }

  function wirePeriodPicker() {
    var btns = document.querySelectorAll(".period-picker button");
    function sync() {
      for (var j = 0; j < btns.length; j++) {
        btns[j].className =
          btns[j].getAttribute("data-period") === state.period ? "active" : "";
      }
      updatePeriodLabel();
    }
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function () {
        state.period = this.getAttribute("data-period");
        sync();
        renderAll();
      });
    }
    sync();
  }

  /* ---------- bankvælger + skam-skammel ---------- */
  function buildBankPicker() {
    var cmp = state.cmp.comparison;
    ["bank-picker", "bank-picker-2"].forEach(function (id) {
      var box = document.getElementById(id);
      if (!box) return;
      box.innerHTML = "";
      Object.keys(cmp.banks).forEach(function (b) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.setAttribute("role", "tab");
        var dot = document.createElement("i");
        dot.style.background = cmp.banks[b].color;
        btn.appendChild(dot);
        btn.appendChild(document.createTextNode(cmp.banks[b].label));
        if (b === state.bank) btn.className = "active";
        btn.addEventListener("click", function () { selectBank(b, true); });
        box.appendChild(btn);
      });
    });
  }

  function selectBank(b, scroll) {
    if (!state.cmp.bankData[b]) return;
    state.bank = b;
    state.data = state.cmp.bankData[b];
    state.product = state.data.order.indexOf("f5") !== -1 ? "f5" : state.data.order[0];
    document.getElementById("bank-name-produkter").textContent =
      state.cmp.comparison.banks[b].label;
    document.getElementById("bank-name-score").textContent =
      state.cmp.comparison.banks[b].label;
    document.getElementById("dl-json").href = bankPath(b);
    renderHero();
    renderTabs(state.data);
    renderProduct();
    renderScore();
    var btns = document.querySelectorAll(".bank-picker button");
    var keys = Object.keys(state.cmp.comparison.banks);
    for (var i = 0; i < btns.length; i++) {
      btns[i].className = keys[i % keys.length] === b ? "active" : "";
    }
    if (scroll) {
      document.getElementById("produkter").scrollIntoView({ behavior: "smooth" });
    }
  }

  var PODIUM_MIN_N = 30;

  function renderPodium() {
    var cmp = state.cmp.comparison;
    var overall = comparison().overall;
    var excluded = Object.keys(overall).filter(function (b) {
      var o = overall[b];
      return o.mae === null || (o.n || 0) < PODIUM_MIN_N;
    });
    var ranked = Object.keys(overall)
      .filter(function (b) { return excluded.indexOf(b) === -1; })
      .sort(function (a, b) { return overall[b].mae - overall[a].mae; })
      .slice(0, 3);
    var note = "Skammelen måler den rene gennemsnitsfejl (MAE) på alle prognoser med facit " +
      "(min. " + PODIUM_MIN_N + " stk.) — hvor mange procentpoint hver bank i snit rammer " +
      "ved siden af. " +
      (excluded.length ? "Endnu ikke med: " +
        excluded.map(function (b) { return cmp.banks[b].label; }).join(", ") +
        " — de har for lidt historik til at komme i skammekrogen. " : "") +
      "Vil du se den fair disciplin-for-disciplin-sammenligning, finder du mesterskabet længere nede.";
    var noteEl = document.getElementById("podium-note");
    noteEl.innerHTML = "";
    noteEl.appendChild(document.createTextNode(note.split("mesterskabet")[0]));
    var a = document.createElement("a");
    a.href = "#sammenlign";
    a.textContent = "mesterskabet";
    noteEl.appendChild(a);
    noteEl.appendChild(document.createTextNode(" længere nede."));
    var box = document.getElementById("podium");
    box.innerHTML = "";
    if (ranked.length < 3) return;
    // Podium: den mest upræcise (højeste MAE) på toppen, flankeret af nr. 2 og 3.
    var order = [ranked[1], ranked[0], ranked[2]];
    var cls = ["second", "first", "third"];
    order.forEach(function (b, i) {
      var o = overall[b];
      var step = document.createElement("div");
      step.className = "podium-step " + cls[i];
      var period = o.period && o.period[0]
        ? fmtDate(parseDate(o.period[0])) + "–" + fmtDate(parseDate(o.period[1])) : "";
      step.innerHTML =
        "<div class='place'>" + (i === 1 ? "1." : i === 0 ? "2." : "3.") + "</div>" +
        "<div class='bank'>" + cmp.banks[b].label + "</div>" +
        "<div class='mae'>" + o.mae.toFixed(2).replace(".", ",") + " pp</div>" +
        "<div class='sub'>middel absolut fejl · n=" + o.n + "<br>" + period + "</div>";
      step.addEventListener("click", function () { selectBank(b, true); });
      box.appendChild(step);
    });
  }

  function initCompare() {
    fetch("data/comparison.json")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (cmp) {
        state.cmp.comparison = cmp;
        state.cmp.bankData.nykredit = state.data;
        var others = Object.keys(cmp.banks).filter(function (b) { return b !== "nykredit"; });
        return Promise.all(others.map(function (b) {
          return fetch(bankPath(b)).then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
          }).then(function (d) { state.cmp.bankData[b] = d; });
        }));
      })
      .then(function () {
        computeOverlapStart();
        renderChamp();
        buildBankPicker();
        renderPodium();
        buildCmpProducts();
        document.getElementById("cmp-horizon").value = state.cmp.horizon;
        renderCompareAll();
        renderHitrate();
        document.getElementById("cmp-product").addEventListener("change", function (e) {
          state.cmp.product = e.target.value;
          renderCompareAll();
        });
        document.getElementById("cmp-horizon").addEventListener("change", function (e) {
          state.cmp.horizon = e.target.value;
          renderCompareAll();
        });
      })
      .catch(function () { /* sammenligning springes over hvis data mangler */ });
  }

  /* ---------- init ---------- */
  function init() {
    fetch("data/dataset.json")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        state.data = d;
        state.product = (d.order.indexOf("f5") !== -1) ? "f5" : d.order[0];
        renderHero();
        renderTabs(d);
        renderProduct();
        renderScore();
        wirePeriodPicker();
        document.getElementById("horizon-select").addEventListener("change", function () {
          renderScore();
        });
        document.getElementById("toggle-all").addEventListener("change", function (e) {
          state.showAll = e.target.checked;
          renderMain(state.data, state.product);
        });
        document.getElementById("dl-csv").addEventListener("click", downloadCSV);
        initCompare();
      })
      .catch(function (err) {
        document.querySelector("#overblik .lede").innerHTML =
          "<strong>Kunne ikke indlæse dataene.</strong> Åbn siden via en lokal webserver, " +
          "fx med <code>python -m http.server</code> i projektmappen. (" + err + ")";
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
