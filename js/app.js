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
      ctx.strokeStyle = "rgba(90,100,120,.55)";
      ctx.setLineDash([5, 4]);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(px, area.top);
      ctx.lineTo(px, area.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(90,100,120,.9)";
      ctx.font = "11px sans-serif";
      ctx.fillText("i dag", px + 5, area.top + 12);
      ctx.restore();
    }
  };

  function xScale(extra) {
    return Object.assign({
      type: "linear",
      ticks: {
        maxTicksLimit: 9,
        callback: function (v) { return fmtDate(v); }
      },
      grid: { color: "rgba(20,40,80,.07)" }
    }, extra || {});
  }

  var state = { data: null, product: null, showAll: true, charts: {} };

  function destroyChart(key) {
    if (state.charts[key]) { state.charts[key].destroy(); delete state.charts[key]; }
  }

  /* ---------- hero ---------- */
  function renderHero(d) {
    var o = d.overall;
    var biasEl = document.getElementById("stat-bias");
    biasEl.textContent = fmtSigned(o.bias);
    biasEl.className = "stat-value " + (o.bias > 0 ? "pos" : "neg");
    document.getElementById("stat-opt").textContent = fmtShare(o.opt_share);
    document.getElementById("stat-n").textContent = o.n;
    document.getElementById("stat-period").textContent =
      "prognoser fra " + fmtDate(parseDate(d.meta.first_pub)) + " til " +
      fmtDate(parseDate(d.meta.last_pub));

    var worst = null;
    d.points.forEach(function (p) {
      if (p.err === null) return;
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
    var vints = vintagesFor(d, p);
    if (!state.showAll) vints = vints.slice(-6);

    var datasets = vints.map(function (v) {
      var anchor = anchorFor(d, p, v.pub);
      var pts = [];
      if (anchor !== null) pts.push({ x: parseDate(v.pub), y: anchor });
      v.pts.forEach(function (pt) { pts.push({ x: parseDate(pt.target), y: pt.fc }); });
      return {
        label: "Prognose " + fmtDate(parseDate(v.pub)),
        data: pts,
        borderColor: "rgba(31,95,168,.35)",
        backgroundColor: "rgba(31,95,168,.35)",
        borderWidth: 1.5,
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
      borderColor: "#141414",
      backgroundColor: "#141414",
      borderWidth: 3,
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
    var xMin = Math.min.apply(null, allX) - 20 * DAY;
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
            grid: { color: "rgba(20,40,80,.07)" }
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
      if (pt.p !== p || pt.err === null) return;
      pts.push({ x: parseDate(pt.target), y: pt.err, pub: pt.pub, fc: pt.fc, act: pt.act });
      colors.push(pt.err > 0 ? "rgba(192,57,43,.75)" : pt.err < 0 ? "rgba(30,125,70,.75)" : "rgba(120,120,120,.75)");
    });
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
      borderColor: "rgba(0,0,0,.5)", borderWidth: 1.5, pointRadius: 0,
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
            grid: { color: "rgba(20,40,80,.07)" }
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
    var m = d.metrics[p] || {};
    var vals = hs.map(function (h) { return (m[h] && m[h].n) ? m[h].bias : 0; });
    var ctx = document.getElementById("chart-horizon");
    state.charts.horizon = new Chart(ctx, {
      type: "bar",
      data: {
        labels: hs.map(function (h) { return names[h]; }),
        datasets: [{
          label: "Gns. fejl (pp)",
          data: vals,
          backgroundColor: vals.map(function (v) {
            return v >= 0 ? "rgba(192,57,43,.8)" : "rgba(30,125,70,.8)";
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
            grid: { color: "rgba(20,40,80,.07)" }
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
  function renderScore(d) {
    var h = document.getElementById("horizon-select").value;
    var tb = document.querySelector("#score-table tbody");
    tb.innerHTML = "";
    var hName = { alle: "alle horisonter", "3M": "3 mdr", "6M": "6 mdr",
                  "9M": "9 mdr", "12M": "12 mdr" }[h];
    d.order.forEach(function (p) {
      var m = (d.metrics[p] || {})[h] || { n: 0 };
      var tr = document.createElement("tr");
      var biasCls = m.bias === null || m.bias === undefined ? "" :
                    (m.bias > 0 ? "bias-pos" : m.bias < 0 ? "bias-neg" : "");
      tr.innerHTML =
        "<td></td><td></td><td></td><td></td><td></td>";
      var cells = tr.querySelectorAll("td");
      cells[0].textContent = d.labels[p];
      cells[1].textContent = m.n || "–";
      cells[2].textContent = fmtSigned(m.bias);
      cells[2].className = biasCls;
      cells[3].textContent = m.mae === null || m.mae === undefined ? "–" : fmtPct(m.mae).replace(" %", "");
      cells[4].textContent = fmtShare(m.opt_share);
      tb.appendChild(tr);
    });
    document.getElementById("score-note").textContent =
      "Horisont: " + hName + ". Positiv gns. fejl (rød) = renten endte i snit højere end spået, " +
      "altså for optimistiske prognoser. Negativ (grøn) = for pessimistiske.";
  }

  /* ---------- CSV-download ---------- */
  function downloadCSV(d) {
    var rows = [["produkt", "prognosedato", "maldato", "horisont",
                 "prognose_pct", "facit_pct", "facit_dato", "fejl_pp"]];
    function num(v) { return v === null || v === undefined ? "" : String(v).replace(".", ","); }
    d.points.forEach(function (pt) {
      rows.push([d.labels[pt.p], pt.pub, pt.target, pt.h, num(pt.fc),
                 num(pt.act), pt.act_date || "", num(pt.err)]);
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
        renderHero(d);
        renderTabs(d);
        renderProduct();
        renderScore(d);
        document.getElementById("horizon-select").addEventListener("change", function () {
          renderScore(state.data);
        });
        document.getElementById("toggle-all").addEventListener("change", function (e) {
          state.showAll = e.target.checked;
          renderMain(state.data, state.product);
        });
        document.getElementById("dl-csv").addEventListener("click", function () {
          downloadCSV(state.data);
        });
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
