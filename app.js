/* Copy Lab ops console. Does not place trades. */
(function () {
  const charts = {};
  const state = { snap: null, user: null, role: "local", db: null };

  function $(id) {
    return document.getElementById(id);
  }
  function money(n, digits) {
    if (n == null || Number.isNaN(n)) return "—";
    const d = digits == null ? 1 : digits;
    const abs = Math.abs(n).toFixed(d);
    return (n < 0 ? "−$" : "+$") + abs;
  }
  function isLocalHost() {
    return ["localhost", "127.0.0.1"].indexOf(location.hostname) !== -1;
  }
  function page() {
    return (location.hash || "#now").replace("#", "") || "now";
  }
  function setRoute() {
    const p = page();
    document.querySelectorAll("nav a").forEach(function (a) {
      a.classList.toggle("on", a.getAttribute("data-page") === p);
    });
    document.querySelectorAll("[data-view]").forEach(function (el) {
      el.classList.toggle("hidden", el.getAttribute("data-view") !== p);
    });
    if (p === "funnel" || p === "research" || p === "hunt") {
      if (p === "funnel") renderFunnel(state.snap);
      if (p === "research") renderResearch(state.snap);
      if (p === "hunt") renderHunt();
    }
  }

  function roleOf(email) {
    const cfg = window.OPS_CONFIG || { owners: [], viewers: [] };
    const e = (email || "").toLowerCase();
    if ((cfg.owners || []).map(function (x) { return x.toLowerCase(); }).indexOf(e) !== -1) return "owner";
    if ((cfg.viewers || []).map(function (x) { return x.toLowerCase(); }).indexOf(e) !== -1) return "viewer";
    return null;
  }

  function showApp() {
    $("gate").classList.add("hidden");
    $("gate").hidden = true;
    $("app").classList.remove("hidden");
    $("app").hidden = false;
    $("who").textContent = state.user
      ? state.user.email + " · " + state.role
      : "local lab (no Firebase yet)";
    const canWrite = state.role === "owner" || state.role === "local";
    $("btn-note").disabled = !canWrite;
    $("btn-cmd").disabled = !canWrite;
  }

  function showGate(msg) {
    $("app").classList.add("hidden");
    $("app").hidden = true;
    $("gate").classList.remove("hidden");
    $("gate").hidden = false;
    $("gate-msg").textContent = msg || "";
  }

  async function loadConfig() {
    return new Promise(function (resolve) {
      const s = document.createElement("script");
      s.src = "./firebase-config.js";
      s.onload = function () { resolve(true); };
      s.onerror = function () { resolve(false); };
      document.head.appendChild(s);
    });
  }

  function darkChart() {
    Chart.defaults.color = "#8b909c";
    Chart.defaults.borderColor = "#2a2d36";
    Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  }

  function drawBar(id, labels, data, opts) {
    if (charts[id]) charts[id].destroy();
    const ctx = $(id).getContext("2d");
    charts[id] = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{ label: opts.label, data: data, backgroundColor: opts.color || "#6ea8fe" }],
      },
      options: {
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, max: opts.max, title: { display: true, text: opts.xTitle } },
          y: { title: { display: true, text: opts.yTitle } },
        },
      },
    });
  }

  function renderNow(s) {
    $("s-cash").textContent = "$" + Number(s.cash_usd).toFixed(2);
    $("s-live").textContent = money(s.last_live_pnl_usd, 2);
    $("s-sims").textContent = String((s.universe || {}).total_isolated_sims || 76);
    $("verdict-body").textContent = s.verdict;
    const sys = s.system || {};
    const rows = [
      ["Discover", (sys.discover || []).join("; "), "Not a second copy bot"],
      ["Gates", (sys.gates || []).join("; "), "Not top of the board this week"],
      ["Lab", sys.lab, "Not the leader’s own PnL"],
      ["Veto", sys.veto, "Not a go-live"],
      ["Execute", sys.execute, "Not dashboard −$10"],
    ];
    $("sys-rows").innerHTML = rows.map(function (r) {
      return "<tr><td>" + r[0] + "</td><td>" + r[1] + "</td><td>" + r[2] + "</td></tr>";
    }).join("");
  }

  function renderResearch(s) {
    $("research-lead").textContent = s.verdict;
    const conc = s.concentration || [];
    drawBar(
      "chart-conc",
      conc.map(function (c) { return c.name; }),
      conc.map(function (c) { return c.share; }),
      { label: "Top-market share", xTitle: "Share of |sim PnL|", yTitle: "Wallet", max: 1, color: "#e0b34e" }
    );
    $("sport-passers").innerHTML = (s.month_passers_sport || []).map(function (r) {
      return "<tr><td>" + r.username + "</td><td>" + Math.round(r.history_days) + "</td><td>" +
        money(r.w60) + "</td><td>" + money(r.w90) + "</td><td>" + r.copies + "</td></tr>";
    }).join("");
  }

  function renderFunnel(s) {
    const f = s.funnel_month;
    drawBar(
      "chart-funnel",
      ["Unique pulled", "Dropped <60d", "Dropped whale", "Passed 60d", "Simulated", "Both windows"],
      [f.unique, f.history_lt_60d, f.whale_month, f.history_pass, f.simulated, f.both_windows],
      { label: "Wallets", xTitle: "Wallets", yTitle: "Step", color: "#6ea8fe" }
    );
    const ns = s.funnel_nonsport;
    $("funnel-ns").textContent = ns.unique + " unique → " + ns.history_pass + " with 60d → " +
      ns.simulated + " simulated → " + ns.both_windows + " both windows positive.";
    const a = s.funnel_all_time;
    $("funnel-all").textContent = a.unique + " unique → " + a.history_90d + " with 90d → " +
      a.simulated + " simulated → " + a.both_windows + " both windows positive (thin politics).";
  }

  function farmCell(f) {
    if (!f) return "—";
    return (f.level || "") + (f.signals != null ? " (" + f.signals + ")" : "");
  }

  function renderVeto(s) {
    $("cg-rows").innerHTML = (s.copygrade_indexed || []).map(function (r) {
      const tone = (r.score || 0) < 50 ? "bad" : (r.score || 0) < 70 ? "warn" : "info";
      return "<tr><td><span class='dot " + tone + "'></span>" + r.username +
        "</td><td>" + (r.source || "") + "</td><td>" + r.score + "</td><td>" + (r.label || "") +
        "</td><td>" + farmCell(r.farming) + "</td><td>" + money(r.edge_real) + "</td></tr>";
    }).join("");
    $("cg-lab").innerHTML = (s.copygrade_shortlist_lab || []).map(function (r) {
      return "<tr><td>" + r.username + "</td><td>" + Math.round(r.history_days) + "</td><td>" + r.tpd +
        "</td><td>" + money(r.w60) + "</td><td>" + money(r.w90) + "</td><td>" +
        (r.candle ? "yes " + r.updown : "no") + "</td><td>" + (r.top_market || "—") + "</td></tr>";
    }).join("");
  }

  function renderLists(s) {
    $("ban-rows").innerHTML = (s.do_not_copy || []).map(function (r) {
      return "<tr><td><span class='dot bad'></span>" + r.name + "</td><td>" + r.why + "</td></tr>";
    }).join("");
    $("watch-rows").innerHTML = (s.watch_not_enable || []).map(function (r) {
      return "<tr><td>" + r.name + "</td><td>" + r.domain + "</td><td>" + r.history_days +
        "</td><td>" + money(r.w60) + " / " + money(r.w90) + "</td><td>" + r.why_not_yet + "</td></tr>";
    }).join("");
  }

  function renderLive(s) {
    const live = s.live || {};
    $("live-reason").textContent = live.reason || "";
    $("live-eval").textContent = live.eval_counter || "";
    $("live-sl-old").textContent = live.balance_sl_old != null ? "$" + live.balance_sl_old : "—";
    $("live-sl-new").textContent = live.balance_sl_if_reenabled != null ? "$" + live.balance_sl_if_reenabled : "—";
  }

  function renderDocs(s) {
    $("doc-rows").innerHTML = (s.handoffs || []).map(function (h) {
      const href = "./docs/" + h.path.replace(/^docs\//, "");
      return "<tr><td>" + h.date + "</td><td>" + h.title + "</td><td><a href='" + href + "'>" + h.path + "</a></td></tr>";
    }).join("");
  }

  function notesKey() { return "copy-lab-ops-notes"; }
  function cmdKey() { return "copy-lab-ops-commands"; }

  function readLocal(key) {
    try { return JSON.parse(localStorage.getItem(key) || "[]"); } catch (e) { return []; }
  }
  function writeLocal(key, rows) {
    localStorage.setItem(key, JSON.stringify(rows));
  }

  function renderNotes() {
    const rows = readLocal(notesKey());
    $("notes").innerHTML = rows.slice().reverse().map(function (n) {
      return "<div class='note'><time>" + n.at + "</time> · " + (n.who || "local") +
        "<div>" + n.text + "</div></div>";
    }).join("") || "<p class='lead'>No notes yet.</p>";
  }

  async function persistNote(row) {
    const rows = readLocal(notesKey());
    rows.push(row);
    writeLocal(notesKey(), rows);
    if (state.db && state.role === "owner") {
      await state.db.collection("ops").doc("notes").collection("items").add(row);
    }
    renderNotes();
  }

  async function persistCmd(row) {
    const rows = readLocal(cmdKey());
    rows.push(row);
    writeLocal(cmdKey(), rows);
    if (state.db && state.role === "owner") {
      await state.db.collection("ops").doc("commands").collection("items").add(row);
    }
  }

  function bindLog() {
    $("btn-note").onclick = function () {
      const text = ($("note-text").value || "").trim();
      if (!text) return;
      $("note-text").value = "";
      persistNote({ at: new Date().toISOString(), who: (state.user && state.user.email) || "local", text: text });
    };
    $("btn-cmd").onclick = function () {
      persistCmd({
        at: new Date().toISOString(),
        who: (state.user && state.user.email) || "local",
        cmd: "run_weekly_screen",
      });
      persistNote({
        at: new Date().toISOString(),
        who: (state.user && state.user.email) || "local",
        text: "Queued command: run_weekly_screen (lab only — not enable_copy).",
      });
    };
  }

  function renderPick(s) {
    const p = s.solution || {};
    $("pick-lead").textContent = p.summary || "";
    $("pick-name").textContent = (p.name || "—") + " · " + (p.domain || "");
    $("pick-why").textContent = p.why || "";
    $("pick-addr").textContent = "Adres do wklejenia w PolyCop: " + (p.address || "");
    const caps = s.caps_if_enabled_later || {};
    const rows = [
      ["Wallets Active", "1 (tylko ten). Reszta Paused."],
      ["Fixed / Max trade / Max Yes-No / Max market", "$" + (caps.fixed_usd || 5)],
      ["Ignore below", "$" + (caps.ignore_below_usd || 20)],
      ["Total spend", "$" + (caps.total_spend_usd || 15)],
      ["Balance SL", "$" + (caps.balance_sl_usd || 31) + " — stary $42 jest zły"],
      ["Turn On All Copy", "NIE"],
    ];
    $("pick-caps").innerHTML = rows.map(function (r) {
      return "<tr><td>" + r[0] + "</td><td>" + r[1] + "</td></tr>";
    }).join("");
  }

  function moneyPlain(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return (n < 0 ? "−$" : "+$") + Math.abs(n).toFixed(1);
  }

  async function renderHunt() {
    try {
      const h = await (await fetch("./data/hunt.json?t=" + Date.now())).json();
      $("hunt-status").textContent = (h.status || "?") + " · checked " + (h.checked || 0) +
        " · " + (h.updated_at || "");
      $("hunt-rows").innerHTML = (h.candidates || []).map(function (r) {
        const cg = r.copygrade || {};
        return "<tr><td>" + r.score + "</td><td>" + r.username + "</td><td>" + r.cat +
          "</td><td>" + Math.round(r.history_days) + "</td><td>" + moneyPlain(r.w60) +
          "</td><td>" + moneyPlain(r.w90) + "</td><td>" + r.conc + "</td><td>" +
          (cg.label || cg.status || "—") + "</td></tr>";
      }).join("") || "<tr><td colspan='8'>Jeszcze nic — hunt leci.</td></tr>";
      $("hunt-log").textContent = (h.log || []).slice(-25).join("\n");
    } catch (e) {
      $("hunt-status").textContent = "Hunt jeszcze nie zapisał pliku (startuję).";
    }
  }

  async function renderRemote() {
    try {
      const r = await (await fetch("./data/remote.json?t=" + Date.now())).json();
      if (r.url) {
        $("live-reason").textContent = (state.snap.live && state.snap.live.reason) || "";
        const extra = document.getElementById("remote-url");
        if (extra) extra.innerHTML = "Zdalnie: <a href='" + r.url + "/ops/'>" + r.url + "/ops/</a>";
        const lan = document.getElementById("how-lan");
        if (lan && r.lan) lan.textContent = r.lan;
      }
    } catch (e) { /* no tunnel file yet */ }
  }

  function renderAll() {
    const s = state.snap;
    if (!s) return;
    darkChart();
    renderNow(s);
    renderPick(s);
    renderVeto(s);
    renderLists(s);
    renderLive(s);
    renderDocs(s);
    renderNotes();
    renderHunt();
    renderRemote();
    const p = page();
    if (p === "funnel") renderFunnel(s);
    if (p === "research") renderResearch(s);
    if (p === "hunt") renderHunt();
  }

  async function bootFirebase() {
    const cfg = window.OPS_CONFIG && window.OPS_CONFIG.firebase;
    if (!cfg || !cfg.apiKey) return false;
    firebase.initializeApp(cfg);
    state.db = firebase.firestore();
    $("btn-google").onclick = function () {
      const provider = new firebase.auth.GoogleAuthProvider();
      firebase.auth().signInWithPopup(provider);
    };
    firebase.auth().onAuthStateChanged(function (user) {
      if (!user) {
        showGate("Sign in with the allowlisted Google account.");
        return;
      }
      const role = roleOf(user.email);
      if (!role) {
        showGate("Signed in as " + user.email + " — not on the allowlist. Add the email to firebase-config.js owners/viewers.");
        return;
      }
      state.user = user;
      state.role = role;
      showApp();
    });
    return true;
  }

  async function main() {
    window.addEventListener("hashchange", setRoute);
    setRoute();
    bindLog();
    const snap = await (await fetch("./data/snapshot.json")).json();
    state.snap = snap;
    await loadConfig();
    const hasFb = await bootFirebase();
    if (!hasFb) {
      // Remote tunnel / LAN must work before Firebase exists.
      state.role = "local";
      showApp();
    }
    renderAll();
    setInterval(function () {
      renderHunt();
      renderRemote();
    }, 15000);
  }

  main().catch(function (err) {
    showGate(String(err));
  });
})();
