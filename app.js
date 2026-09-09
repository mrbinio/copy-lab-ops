/* Copy Lab ops. Does not place trades. */
(function () {
  const charts = {};
  const state = { snap: null, user: null, role: null, db: null, hunt: null };

  function $(id) { return document.getElementById(id); }
  function money(n, digits) {
    if (n == null || Number.isNaN(n)) return "—";
    const d = digits == null ? 1 : digits;
    const abs = Math.abs(n).toFixed(d);
    return (n < 0 ? "−$" : "+$") + abs;
  }
  function moneyPlain(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return (n < 0 ? "−$" : "+$") + Math.abs(n).toFixed(1);
  }

  async function sha256hex(text) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(function (b) {
      return b.toString(16).padStart(2, "0");
    }).join("");
  }

  function unlocked() {
    return sessionStorage.getItem("copy-lab-ok") === "1";
  }
  function unlockSession() {
    sessionStorage.setItem("copy-lab-ok", "1");
  }

  function page() {
    return (location.hash || "#now").replace("#", "") || "now";
  }
  function setRoute() {
    const p = page();
    if (p === "funnel" && state.snap) renderFunnel(state.snap);
    if (p === "research" && state.snap) renderResearch(state.snap);
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
    $("who").textContent = state.user && state.user.email
      ? state.user.email
      : "damianbiniarz@gmail.com";
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
      showGate("Wpisz hasło strony.");
      return;
    }
    const hex = await sha256hex(typed);
    if (hex !== expect) {
      showGate("Złe hasło.");
      return;
    }
    unlockSession();
    state.role = "owner";
    showApp();
    renderAll();
  }

  function darkChart() {
    if (!window.Chart) return;
    Chart.defaults.color = "#5c5850";
    Chart.defaults.borderColor = "#d9d3c7";
  }

  function drawBar(id, labels, data, opts) {
    if (!$(id) || !window.Chart) return;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart($(id).getContext("2d"), {
      type: "bar",
      data: { labels: labels, datasets: [{ label: opts.label, data: data, backgroundColor: opts.color || "#1f4b99" }] },
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
    if ($("s-sims")) $("s-sims").textContent = String((s.universe || {}).total_isolated_sims || 76);
    if ($("verdict-body")) $("verdict-body").textContent = s.verdict || "";
  }

  function renderPick(s) {
    const p = s.solution || {};
    const name = (p.name || "—") + " · " + (p.domain || "");
    $("hero-name").textContent = name;
    $("hero-why").textContent = p.why || p.summary || "";
    $("hero-addr").textContent = p.address || "";
    $("hero-meaning").innerHTML =
      "Co to znaczy: lab na $5 / ignore &lt;$20 / spend $15. 60 dni i 90 dni na plusie. " +
      "Nie esport, nie świeca Bitcoin 5 min, CopyGrade nie mówi Avoid. " +
      "76 dni to krótko — dlatego hunt leci dalej i nadpisuje tę kartę, jeśli ktoś przebije.";
    if ($("pick-name")) $("pick-name").textContent = name;
    if ($("pick-why")) $("pick-why").textContent = p.why || "";
    if ($("pick-addr")) $("pick-addr").textContent = p.address || "";
    const caps = s.caps_if_enabled_later || {};
    const rows = [
      ["Tylko 1 Active, reszta Paused", "Nie kopiujesz ośmiu osób naraz. Jeden specjalista."],
      ["Fixed / Max / Yes-No / Market = $" + (caps.fixed_usd || 5), "Jedna kopia nie zjada stacka $39."],
      ["Ignore poniżej $" + (caps.ignore_below_usd || 20), "Pomija drobnice, która spala prowizję."],
      ["Total spend $" + (caps.total_spend_usd || 15), "Naraz w rynku max ~$15, nie cały cash."],
      ["Balance SL $" + (caps.balance_sl_usd || 31), "Stary SL $42 jest zły przy cash ~$39. Nowy ≈ cash − $8."],
      ["Turn On All Copy = NIE", "Nigdy cała lista. Tylko ten jeden adres."],
    ];
    $("pick-caps").innerHTML = rows.map(function (r) {
      return "<tr><td>" + r[0] + "</td><td>" + r[1] + "</td></tr>";
    }).join("");
  }

  function beatsOfficial(h, official) {
    if (!h || !h.username) return false;
    const o60 = official && official.w60 != null ? official.w60 : 17;
    const o90 = official && official.w90 != null ? official.w90 : 9;
    if ((h.w60 || 0) <= o60) return false;
    if ((h.w90 || 0) <= o90) return false;
    if ((h.conc || 1) > 0.45) return false;
    const lab = String((h.copygrade && (h.copygrade.label || h.copygrade.status)) || "");
    if (lab.indexOf("Avoid") !== -1) return false;
    return true;
  }

  async function renderHunt() {
    try {
      const h = await (await fetch("./data/hunt.json?t=" + Date.now())).json();
      state.hunt = h;
      let pulse = "";
      try {
        const p = await (await fetch("./data/pulse.json?t=" + Date.now())).json();
        if (p.hunt === "running") pulse = "TERAZ SZUKA (GitHub Actions, Mac może być off). ";
      } catch (e) { /* optional */ }
      const when = h.updated_at ? String(h.updated_at).replace("T", " ").slice(0, 16) + " UTC" : "?";
      const st = h.status === "running" ? "w trakcie skanowania" : (h.status === "done" ? "ostatni przebieg skończony" : (h.status || "?"));
      $("hunt-pulse").textContent = pulse + st + " · " + when + " · sprawdzono " + (h.checked || 0) + " portfeli";
      if ($("hunt-status")) {
        $("hunt-status").textContent = $("hunt-pulse").textContent;
      }
      const official = (state.snap && state.snap.solution) || {};
      const pick = h.pick;
      if (!pick) {
        $("hunt-plain").textContent = "Na razie hunt nie ma kandydata lepszego niż Antblack. Następny przebieg sam się odpali co godzinę.";
      } else if (beatsOfficial(pick, official)) {
        $("hunt-plain").textContent = "NOWE ROZWIĄZANIE z huntu: " + pick.username +
          " bije Antblack (60d " + moneyPlain(pick.w60) + ", 90d " + moneyPlain(pick.w90) +
          "). W PolyCop wklejasz tego, nie Antblack — jak zdecydujesz ręcznie.";
        $("hero-name").textContent = pick.username + " · hunt";
        $("hero-addr").textContent = pick.wallet || "";
      } else {
        $("hunt-plain").textContent = "Ostatni kandydat huntu: " + pick.username +
          " (" + (pick.cat || "") + ", " + Math.round(pick.history_days || 0) + "d, 60d " +
          moneyPlain(pick.w60) + " / 90d " + moneyPlain(pick.w90) + ", conc " + pick.conc +
          "). To NIE przebija Antblack — za cienki sim albo za duża koncentracja. Pick zostaje Antblack.";
      }
      const cards = (h.candidates || []).slice(0, 6).map(function (r) {
        const cg = r.copygrade || {};
        return "<div class='hunt-card'><b>" + r.username + "</b>" +
          "<span class='hint'>" + (r.cat || "") + " · " + Math.round(r.history_days || 0) +
          " dni historii · 60d " + moneyPlain(r.w60) + " · 90d " + moneyPlain(r.w90) +
          " · skupienie " + r.conc + " (mniej = lepiej, próg 0.45) · CopyGrade: " +
          (cg.label || cg.status || "brak") + "</span></div>";
      }).join("");
      $("hunt-cards").innerHTML = cards || "<p class='hint'>Pusta lista — skan jeszcze filtruje.</p>";
      $("hunt-log").textContent = (h.log || []).slice(-20).join("\n");
    } catch (e) {
      $("hunt-pulse").textContent = "Hunt jeszcze nie zapisał przebiegu na stronie.";
    }
  }

  function renderResearch(s) {
    if (!$("research-lead")) return;
    $("research-lead").textContent = s.verdict || "";
    const conc = s.concentration || [];
    drawBar("chart-conc", conc.map(function (c) { return c.name; }), conc.map(function (c) { return c.share; }),
      { label: "Top-market", xTitle: "Udział |PnL|", yTitle: "Portfel", max: 1, color: "#1f4b99" });
    $("sport-passers").innerHTML = (s.month_passers_sport || []).map(function (r) {
      return "<tr><td>" + r.username + "</td><td>" + Math.round(r.history_days) + "</td><td>" +
        money(r.w60) + "</td><td>" + money(r.w90) + "</td><td>" + r.copies + "</td></tr>";
    }).join("");
  }

  function renderFunnel(s) {
    if (!$("chart-funnel")) return;
    const f = s.funnel_month || {};
    drawBar("chart-funnel",
      ["Unique", "<60d", "Whale", "Pass 60d", "Sim", "Oba okna"],
      [f.unique, f.history_lt_60d, f.whale_month, f.history_pass, f.simulated, f.both_windows],
      { label: "Wallets", xTitle: "Ile", yTitle: "Krok", color: "#1f4b99" });
    const ns = s.funnel_nonsport || {};
    $("funnel-ns").textContent = "Non-sport: " + ns.unique + " → " + ns.history_pass + " z 60d → " + ns.simulated + " sim → " + ns.both_windows + " oba okna +.";
    const a = s.funnel_all_time || {};
    $("funnel-all").textContent = "ALL mid-tier: " + a.unique + " → " + a.history_90d + " z 90d → " + a.simulated + " sim → " + a.both_windows + " oba okna +.";
  }

  function farmCell(f) {
    if (!f) return "—";
    return (f.level || "") + (f.signals != null ? " (" + f.signals + ")" : "");
  }

  function renderVeto(s) {
    if (!$("cg-rows")) return;
    $("cg-rows").innerHTML = (s.copygrade_indexed || []).map(function (r) {
      return "<tr><td>" + r.username + "</td><td>" + (r.source || "") + "</td><td>" + r.score +
        "</td><td>" + (r.label || "") + "</td><td>" + farmCell(r.farming) + "</td><td>" + money(r.edge_real) + "</td></tr>";
    }).join("");
    $("cg-lab").innerHTML = (s.copygrade_shortlist_lab || []).map(function (r) {
      return "<tr><td>" + r.username + "</td><td>" + Math.round(r.history_days) + "</td><td>" + r.tpd +
        "</td><td>" + money(r.w60) + "</td><td>" + money(r.w90) + "</td><td>" +
        (r.candle ? "tak" : "nie") + "</td><td>" + (r.top_market || "—") + "</td></tr>";
    }).join("");
  }

  function renderLists(s) {
    const bans = s.do_not_copy || [];
    $("ban-list").innerHTML = bans.map(function (r) {
      return "<li><b>" + r.name + "</b> — " + r.why + "</li>";
    }).join("");
  }

  function renderLive(s) {
    const live = s.live || {};
    if ($("live-reason")) $("live-reason").textContent = live.reason || "";
    if ($("live-eval")) $("live-eval").textContent = live.eval_counter || "";
  }

  function renderDocs(s) {
    if (!$("doc-rows")) return;
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
  function writeLocal(key, rows) { localStorage.setItem(key, JSON.stringify(rows)); }
  function renderNotes() {
    if (!$("notes")) return;
    const rows = readLocal(notesKey());
    $("notes").innerHTML = rows.slice().reverse().map(function (n) {
      return "<div class='note'>" + (n.text || "") + "</div>";
    }).join("");
  }
  async function persistNote(row) {
    const rows = readLocal(notesKey());
    rows.push(row);
    writeLocal(notesKey(), rows);
    renderNotes();
  }
  async function persistCmd() {}
  function bindLog() {
    if ($("btn-code")) $("btn-code").onclick = tryPageCode;
    if ($("page-code")) {
      $("page-code").addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") tryPageCode();
      });
    }
    if ($("btn-note")) {
      $("btn-note").onclick = function () {
        const text = ($("note-text").value || "").trim();
        if (text) persistNote({ at: new Date().toISOString(), text: text });
      };
    }
  }

  function renderRemote() {}

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
    renderResearch(s);
    renderFunnel(s);
  }

  async function bootFirebase() {
    const cfg = window.OPS_CONFIG && window.OPS_CONFIG.firebase;
    if (!cfg || !cfg.apiKey || !window.firebase) return false;
    firebase.initializeApp(cfg);
    $("btn-google").hidden = false;
    $("btn-google").onclick = function () {
      firebase.auth().signInWithPopup(new firebase.auth.GoogleAuthProvider());
    };
    firebase.auth().onAuthStateChanged(function (user) {
      if (!user) return;
      const role = roleOf(user.email);
      if (!role) {
        showGate("To Google (" + user.email + ") nie jest na liście. Trzeba damianbiniarz@gmail.com.");
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

  async function main() {
    bindLog();
    window.addEventListener("hashchange", setRoute);
    const snap = await (await fetch("./data/snapshot.json")).json();
    state.snap = snap;
    await bootFirebase();
    if (unlocked()) {
      state.role = state.role || "owner";
      showApp();
      renderAll();
    } else {
      showGate("Hasło strony (nie hasło Gmail).");
    }
    setInterval(function () {
      if (unlocked()) renderHunt();
    }, 15000);
  }

  main().catch(function (err) {
    showGate(String(err));
  });
})();
