/* Copy Lab board. Does not place trades. */
(function () {
  const charts = {};
  const state = { snap: null, user: null, role: null, hunt: null };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function money(n, digits) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    const d = digits == null ? 1 : digits;
    const v = Number(n);
    return (v < 0 ? "−$" : "+$") + Math.abs(v).toFixed(d);
  }
  function usd(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return "$" + Number(n).toFixed(2);
  }
  function conc(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return Number(n).toFixed(2);
  }

  async function sha256hex(text) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(function (b) {
      return b.toString(16).padStart(2, "0");
    }).join("");
  }

  function unlocked() { return sessionStorage.getItem("copy-lab-ok") === "1"; }
  function unlockSession() { sessionStorage.setItem("copy-lab-ok", "1"); }

  function roleOf(email) {
    const cfg = window.OPS_CONFIG || { owners: [], viewers: [] };
    const e = (email || "").toLowerCase();
    if ((cfg.owners || []).map(function (x) { return x.toLowerCase(); }).indexOf(e) !== -1) return "owner";
    if ((cfg.viewers || []).map(function (x) { return x.toLowerCase(); }).indexOf(e) !== -1) return "viewer";
    return null;
  }

  function tabFromHash() {
    return (location.hash || "").replace("#", "") === "guide" ? "guide" : "board";
  }

  function showTab(name) {
    const isGuide = name === "guide";
    const board = $("view-board");
    const guide = $("view-guide");
    if (board) {
      board.classList.toggle("hidden", isGuide);
      board.hidden = isGuide;
    }
    if (guide) {
      guide.classList.toggle("hidden", !isGuide);
      guide.hidden = !isGuide;
    }
    document.querySelectorAll(".tab").forEach(function (btn) {
      btn.classList.toggle("on", btn.getAttribute("data-tab") === (isGuide ? "guide" : "board"));
    });
    try {
      history.replaceState(null, "", isGuide ? "#guide" : "#board");
    } catch (e) { /* ignore */ }
    if (!isGuide) {
      Object.keys(charts).forEach(function (id) {
        if (charts[id] && typeof charts[id].resize === "function") charts[id].resize();
      });
    }
  }

  function showApp() {
    $("gate").classList.add("hidden");
    $("gate").hidden = true;
    $("app").classList.remove("hidden");
    $("app").hidden = false;
    $("app").classList.add("app-in");
    $("who").textContent = (state.user && state.user.email) || "damianbiniarz@gmail.com";
    showTab(tabFromHash());
  }

  function showGate(msg) {
    $("app").classList.add("hidden");
    $("app").hidden = true;
    $("gate").classList.remove("hidden");
    $("gate").hidden = false;
    $("gate-msg").textContent = msg || "";
  }

  async function tryPageCode() {
    const typed = ($("page-code").value || "").trim();
    const expect = (window.OPS_CONFIG && window.OPS_CONFIG.pageCodeSha256) || "";
    if (!typed || !expect) {
      showGate("Enter the page password.");
      return;
    }
    const hex = await sha256hex(typed);
    if (hex !== expect) {
      showGate("Wrong password.");
      return;
    }
    unlockSession();
    state.role = "owner";
    showApp();
    renderAll();
  }

  function firebaseReady() {
    const cfg = window.OPS_CONFIG && window.OPS_CONFIG.firebase;
    return cfg && cfg.apiKey && window.firebase;
  }

  function classifyHunt(row, official) {
    const cg = row.copygrade || {};
    const label = String(cg.label || "");
    const w60 = Number(row.w60 || 0);
    const w90 = Number(row.w90 || 0);
    const c = Number(row.conc || 1);
    const days = Number(row.history_days || 0);
    const copies = Number(row.copies || 0);
    const candle = Number(row.candle || 0);
    const o60 = official && official.w60 != null ? Number(official.w60) : 17;
    const o90 = official && official.w90 != null ? Number(official.w90) : 9.2;
    if (label.indexOf("Avoid") !== -1) return { call: "reject", why: "CopyGrade Avoid — follower is not paid after fees." };
    if (candle > 0.25) return { call: "reject", why: "5-minute candle book. A $5 copier churns." };
    if (w60 <= 0 || w90 <= 0) return { call: "reject", why: "Not profitable in both 60d and 90d lab windows." };
    if (c > 0.45) return { call: "reject", why: "Top market " + Math.round(c * 100) + "% of |PnL| — one event, not a book." };
    if (copies < 6) return { call: "reject", why: "Fewer than 6 copyable fills under $15 spend." };
    if (w60 > o60 && w90 > o90 && c <= 0.45 && days >= 90) {
      return { call: "wait", why: "Beats Antblack on both windows with a 90d track. Still your enable in PolyCop." };
    }
    if (days < 90) return { call: "wait", why: "Both windows green, track under 90 days — streak risk." };
    if (w60 < 8 && w90 < 8) return { call: "reject", why: "Lab edge too small versus a $13.58 hole." };
    return { call: "wait", why: "Partial gates only." };
  }

  function officialWatch(s) {
    return ((s.board || {}).options || []).find(function (r) { return r.name === "Antblack"; }) || s.solution || {};
  }

  function fieldRows(s, hunt) {
    const known = {};
    const rows = ((s.board || {}).options || []).slice();
    rows.forEach(function (r) { known[(r.name || "").toLowerCase()] = true; });
    const official = officialWatch(s);
    (hunt && hunt.candidates || []).forEach(function (h) {
      const name = h.username || "";
      if (known[name.toLowerCase()]) return;
      known[name.toLowerCase()] = true;
      const cls = classifyHunt(h, official);
      rows.push({
        name: name,
        domain: h.cat || h.domain || "",
        source: "hunt",
        call: cls.call,
        why_short: cls.why,
        meaning: cls.why,
        w60: h.w60,
        w90: h.w90,
        days: h.history_days,
        conc: h.conc
      });
    });
    rows.sort(function (a, b) {
      if (a.call === "wait" && b.call !== "wait") return -1;
      if (b.call === "wait" && a.call !== "wait") return 1;
      return (Number(b.w90) || 0) - (Number(a.w90) || 0);
    });
    return rows;
  }

  function rowHtml(r) {
    const call = r.call === "wait" ? "wait" : "reject";
    return '<tr class="' + call + '"><td><span class="pill ' + call + '">' +
      (call === "wait" ? "WAIT" : "NO") + "</span></td>" +
      '<td><span class="name">' + esc(r.name) + '</span><span class="src">' +
      esc((r.domain || "") + (r.source ? " · " + r.source : "")) + "</span></td>" +
      "<td>" + money(r.w60) + "</td><td>" + money(r.w90) + "</td>" +
      "<td>" + (r.days != null ? Math.round(r.days) + "d" : "—") + "</td>" +
      "<td>" + conc(r.conc) + "</td>" +
      "<td>" + esc(r.why_short || r.meaning || "") + "</td></tr>";
  }

  function drawH(id, labels, data, colors, xTitle) {
    if (!$(id) || !window.Chart) return;
    if (charts[id]) charts[id].destroy();
    Chart.defaults.color = "#9aa3b2";
    Chart.defaults.borderColor = "rgba(255,255,255,0.08)";
    charts[id] = new Chart($(id).getContext("2d"), {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          data: data,
          backgroundColor: colors || "#7aa2ff",
          borderRadius: 8,
          borderSkipped: false
        }]
      },
      options: {
        indexAxis: "y",
        animation: { duration: 900, easing: "easeOutQuart" },
        plugins: { legend: { display: false } },
        scales: {
          x: {
            beginAtZero: true,
            title: { display: true, text: xTitle },
            grid: { color: "rgba(255,255,255,0.06)" }
          },
          y: { ticks: { autoSkip: false }, grid: { display: false } }
        }
      }
    });
  }

  function renderCharts(s, rows) {
    const f = s.funnel_month || {};
    drawH("chart-funnel",
      ["Unique names", "History <60d (drop)", "Passed 60d", "Simulated", "Both windows +"],
      [f.unique || 0, f.history_lt_60d || 0, f.history_pass || 0, f.simulated || 0, f.both_windows || 0],
      "#7aa2ff",
      "Wallets"
    );
    const top = rows.slice(0, 8);
    drawH("chart-pnl",
      top.map(function (r) { return r.name; }),
      top.map(function (r) { return Number(r.w90) || 0; }),
      top.map(function (r) { return r.call === "wait" ? "#f5c15c" : "rgba(255,255,255,0.22)"; }),
      "90d lab USD at $5 copy"
    );
    const conc = (s.concentration || []).slice(0, 8);
    drawH("chart-conc",
      conc.map(function (c) { return c.name; }),
      conc.map(function (c) { return c.share; }),
      conc.map(function (c) { return c.share > 0.45 ? "#ff6b6b" : "#7aa2ff"; }),
      "Share of |PnL| in top market (0.45 cutoff)"
    );
  }

  function renderPredict(s, hunt) {
    const n = hunt && hunt.checked ? hunt.checked : 0;
    const ant = officialWatch(s);
    const per30 = ant.w60 != null ? (Number(ant.w60) / 2).toFixed(1) : "8.5";
    if ($("pred-a")) {
      $("pred-a").textContent = "Forecast: $0 extra copy loss from here. Hunt already scanned " +
        n + " extra wallets this run (sport/politics/crypto/culture/finance/economics). No name has cleared 90d + book + CopyGrade together. This is the recover-then-earn path: wait for a real specialist, do not bleed the $39.";
    }
    if ($("pred-b")) {
      $("pred-b").textContent = "Lab: 60d " + money(ant.w60) + " / 90d " + money(ant.w90) +
        " at $5 copy, 13 tennis markets, conc 0.11, CopyGrade 64 caution. If the 60d pace repeated it is about $" +
        per30 + " / 30 days — not a promise. 90d is weaker than 60d, track is 76 days, farming watch. Does not, on this sample, fill a $13.58 hole quickly.";
    }
    if ($("pred-c")) {
      $("pred-c").textContent = "Gabriell +$70 is one GTA view event. Bromsloy +$53 is 100% 5-minute Bitcoin candles. Jittz +$51 is a World Cup date cluster. gambamaster lab +$24 is CopyGrade Avoid (−100% real edge). Predicted outcome if you paste these: the next period does not pay. Same class of error as invorser esports.";
    }
  }

  function renderBans(s) {
    const onBoard = {};
    ((s.board || {}).options || []).forEach(function (r) { onBoard[(r.name || "").toLowerCase()] = true; });
    $("ban-list").innerHTML = (s.do_not_copy || []).filter(function (r) {
      return !onBoard[(r.name || "").toLowerCase()];
    }).map(function (r) {
      return "<li><b>" + esc(r.name) + "</b> — " + esc(r.why) + "</li>";
    }).join("");
  }

  function renderOverride(s) {
    const p = (s.board && s.board.override) || s.solution || {};
    const caps = s.caps_if_enabled_later || {};
    const rows = [
      ["Active wallets", "1 — Antblack only, everyone else Paused"],
      ["Address", p.address || ""],
      ["Fixed / max Yes-No / max market", "$" + (caps.fixed_usd || 5)],
      ["Ignore below", "$" + (caps.ignore_below_usd || 20)],
      ["Total spend", "$" + (caps.total_spend_usd || 15)],
      ["Balance SL", "$" + (caps.balance_sl_usd || 31)],
      ["Turn On All Copy", "Never"]
    ];
    $("override-box").innerHTML = "<p class='addr'>" + esc(p.address || "") +
      "</p><table class='caps'><tbody>" + rows.map(function (r) {
        return "<tr><td>" + esc(r[0]) + "</td><td>" + esc(r[1]) + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  async function loadHunt() {
    try {
      const h = await (await fetch("./data/hunt.json?t=" + Date.now())).json();
      state.hunt = h;
      let pulse = "";
      try {
        const p = await (await fetch("./data/pulse.json?t=" + Date.now())).json();
        if (p.hunt === "running") pulse = "HUNT RUNNING · ";
      } catch (e) { /* optional */ }
      const when = h.updated_at ? String(h.updated_at).replace("T", " ").slice(0, 16) + " UTC" : "?";
      $("hunt-pulse").textContent = pulse + "last hunt " + when;
      $("hunt-plain").textContent = "GitHub Actions at :20 and :50 UTC. Last run checked " +
        (h.checked || 0) + " new wallets. Names land in the table and charts. Hunt never turns PolyCop on.";
    } catch (e) {
      $("hunt-pulse").textContent = "Hunt file missing";
    }
  }

  async function renderAll() {
    const s = state.snap;
    if (!s) return;
    $("s-cash").textContent = usd(s.cash_usd);
    $("s-live").textContent = money(s.last_live_pnl_usd, 2);
    renderBans(s);
    renderOverride(s);
    await loadHunt();
    const rows = fieldRows(s, state.hunt);
    $("field-body").innerHTML = rows.map(rowHtml).join("");
    renderPredict(s, state.hunt);
    renderCharts(s, rows);
    if (tabFromHash() === "board") {
      Object.keys(charts).forEach(function (id) {
        if (charts[id] && typeof charts[id].resize === "function") charts[id].resize();
      });
    }
  }

  async function bootFirebase() {
    if (!firebaseReady()) return false;
    firebase.initializeApp(window.OPS_CONFIG.firebase);
    $("btn-google").hidden = false;
    $("btn-google").onclick = function () {
      firebase.auth().signInWithPopup(new firebase.auth.GoogleAuthProvider());
    };
    firebase.auth().onAuthStateChanged(function (user) {
      if (!user) return;
      const role = roleOf(user.email);
      if (!role) {
        showGate("Google " + user.email + " is not on the allowlist.");
        return;
      }
      unlockSession();
      state.user = user;
      state.role = role;
      showApp();
      renderAll();
    });
    return true;
  }

  function bind() {
    if ($("btn-code")) $("btn-code").onclick = tryPageCode;
    if ($("page-code")) {
      $("page-code").addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") tryPageCode();
      });
    }
    document.querySelectorAll(".tab").forEach(function (btn) {
      btn.onclick = function () { showTab(btn.getAttribute("data-tab")); };
    });
    window.addEventListener("hashchange", function () { showTab(tabFromHash()); });
  }

  async function main() {
    bind();
    try {
      const fbFile = await fetch("./firebase-config.js", { cache: "no-store" });
      if (fbFile.ok) {
        const el = document.createElement("script");
        el.textContent = await fbFile.text();
        document.head.appendChild(el);
      }
    } catch (e) { /* optional */ }
    state.snap = await (await fetch("./data/snapshot.json?t=" + Date.now())).json();
    const hasFb = await bootFirebase();
    const host = location.hostname;
    if ((host === "127.0.0.1" || host === "localhost") &&
        new URLSearchParams(location.search).get("lab") === "1") {
      unlockSession();
    }
    if (unlocked()) {
      state.role = state.role || "owner";
      showApp();
      renderAll();
    } else if (!hasFb) {
      showGate("Google is not on this deploy yet. Enter the page password from chat.");
    } else {
      showGate("");
    }
    setInterval(function () {
      if (unlocked()) renderAll();
    }, 15000);
  }

  main().catch(function (err) {
    showGate(String(err));
  });
})();
