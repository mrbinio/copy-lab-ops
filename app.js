/* Copy Lab decision board. Does not place trades. */
(function () {
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

  function showApp() {
    $("gate").classList.add("hidden");
    $("gate").hidden = true;
    $("app").classList.remove("hidden");
    $("app").hidden = false;
    $("who").textContent = (state.user && state.user.email) || "damianbiniarz@gmail.com";
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

    if (label.indexOf("Avoid") !== -1) {
      return { call: "reject", why: "CopyGrade Avoid" };
    }
    if (candle > 0.25) {
      return { call: "reject", why: "5-minute candle book" };
    }
    if (w60 <= 0 || w90 <= 0) {
      return { call: "reject", why: "Not profitable in both lab windows" };
    }
    if (c > 0.45) {
      return { call: "reject", why: "Top market " + Math.round(c * 100) + "% of |PnL|" };
    }
    if (copies < 6) {
      return { call: "reject", why: "Fewer than 6 copyable fills under $15" };
    }
    if (w60 > o60 && w90 > o90 && c <= 0.45 && days >= 90) {
      return { call: "wait", why: "Beats Antblack on both windows — still your enable" };
    }
    if (days < 90) {
      return { call: "wait", why: "Both windows green, track under 90 days" };
    }
    if (w60 < 8 && w90 < 8) {
      return { call: "reject", why: "Lab edge too small vs $13.58 hole" };
    }
    return { call: "wait", why: "Partial gates only" };
  }

  function rowHtml(r) {
    const call = r.call === "wait" ? "wait" : "reject";
    const label = call === "wait" ? "WAIT" : "NO";
    return '<tr class="' + call + '">' +
      '<td><span class="pill ' + call + '">' + label + "</span></td>" +
      '<td><span class="name">' + esc(r.name) + '</span><span class="src">' +
      esc((r.domain || "") + (r.source ? " · " + r.source : "")) + "</span></td>" +
      "<td>" + money(r.w60) + "</td>" +
      "<td>" + money(r.w90) + "</td>" +
      "<td>" + (r.days != null ? Math.round(r.days) + "d" : "—") + "</td>" +
      "<td>" + conc(r.conc) + "</td>" +
      '<td class="why">' + esc(r.why_short || r.meaning || "") + "</td>" +
      "</tr>";
  }

  function renderNow(s) {
    const board = s.board || {};
    $("s-cash").textContent = usd(s.cash_usd);
    $("s-live").textContent = money(s.last_live_pnl_usd, 2);
    $("s-hole").textContent = usd(Math.abs(Number(s.last_live_pnl_usd) || 0));
    $("copy-state").textContent = board.copy_state || "COPY OFF";
    $("live-line").textContent = board.live_line || "";
    $("decision-headline").textContent = board.headline || "Do not enable copy.";
    $("decision-why").textContent = board.why || "";
    $("decision-change").textContent = board.change || "";
  }

  function officialWatch(s) {
    return ((s.board || {}).options || []).find(function (r) { return r.name === "Antblack"; }) || s.solution || {};
  }

  function renderField(s, hunt) {
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
        source: "hourly hunt",
        call: cls.call,
        why_short: cls.why + (h.top_market ? " (" + String(h.top_market).slice(0, 42) + ")" : ""),
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
    $("field-body").innerHTML = rows.map(rowHtml).join("");
  }

  function renderBans(s) {
    const onBoard = {};
    ((s.board || {}).options || []).forEach(function (r) { onBoard[(r.name || "").toLowerCase()] = true; });
    const extra = (s.do_not_copy || []).filter(function (r) {
      return !onBoard[(r.name || "").toLowerCase()];
    });
    $("ban-list").innerHTML = extra.map(function (r) {
      return "<li><b>" + esc(r.name) + "</b> — " + esc(r.why) + "</li>";
    }).join("");
  }

  function renderOverride(s) {
    const p = (s.board && s.board.override) || s.solution || {};
    const caps = s.caps_if_enabled_later || {};
    const rows = [
      ["Active wallet", p.name || "—"],
      ["Address", p.address || ""],
      ["Fixed / max Yes-No / max market", "$" + (caps.fixed_usd || 5)],
      ["Ignore below", "$" + (caps.ignore_below_usd || 20)],
      ["Total spend", "$" + (caps.total_spend_usd || 15)],
      ["Balance SL", "$" + (caps.balance_sl_usd || 31)],
      ["Turn On All Copy", "Never"]
    ];
    $("override-box").innerHTML = "<p>" + esc(p.note || "") +
      "</p><p class='addr'>" + esc(p.address || "") + "</p><table class='caps'><tbody>" +
      rows.map(function (r) {
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
        if (p.hunt === "running") pulse = "Hunt running now. ";
      } catch (e) { /* optional */ }
      const when = h.updated_at ? String(h.updated_at).replace("T", " ").slice(0, 16) + " UTC" : "?";
      $("hunt-pulse").textContent = pulse + "Hunt last run " + when + " · " + (h.checked || 0) + " extra wallets.";
    } catch (e) {
      $("hunt-pulse").textContent = "Hunt file missing on this deploy.";
    }
  }

  async function renderAll() {
    const s = state.snap;
    if (!s) return;
    renderNow(s);
    renderBans(s);
    renderOverride(s);
    await loadHunt();
    renderField(s, state.hunt);
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
        showGate("Google " + user.email + " is not on the allowlist. Use damianbiniarz@gmail.com.");
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
  }

  async function main() {
    bind();
    try {
      const fbFile = await fetch("./firebase-config.js", { cache: "no-store" });
      if (fbFile.ok) {
        const s = document.createElement("script");
        s.textContent = await fbFile.text();
        document.head.appendChild(s);
      }
    } catch (e) { /* optional */ }
    const snap = await (await fetch("./data/snapshot.json?t=" + Date.now())).json();
    state.snap = snap;
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
