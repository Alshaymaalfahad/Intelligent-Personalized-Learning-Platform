/* Shared app layer: language, API, DOM helpers, icons, the coach mascot, and the app shell
   (sidebar + top bar). Loaded first on every page, right after i18n.js.
   AI-generated text is always inserted with textContent, never innerHTML. */

window.App = (() => {
  const { t, lang } = I18n;

  /* ---------- DOM ---------- */

  function el(tag, opts = {}, ...children) {
    const node = document.createElement(tag);
    if (opts.className) node.className = opts.className;
    if (opts.text !== undefined && opts.text !== null) node.textContent = opts.text;
    if (opts.dir) node.dir = opts.dir;
    if (opts.type) node.type = opts.type;
    if (opts.href) node.href = opts.href;
    if (opts.id) node.id = opts.id;
    if (opts.title) node.title = opts.title;
    if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) node.setAttribute(k, v);
    for (const c of children) if (c !== null && c !== undefined && c !== false) node.append(c);
    return node;
  }

  function button(text, className, onClick, icon) {
    const b = el("button", { className: `btn ${className || ""}`.trim(), type: "button" }, icon ? svg(icon) : null, el("span", { text }));
    if (onClick) b.addEventListener("click", onClick);
    return b;
  }

  const $ = (id) => document.getElementById(id);

  /* ---------- API (sends the interface language for localized messages) ---------- */

  async function api(method, path, body) {
    const headers = { "X-Lang": lang() };
    if (body) headers["Content-Type"] = "application/json";
    const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    let data = null;
    try {
      data = await res.json();
    } catch {
      /* empty body */
    }
    if (!res.ok) {
      const err = new Error((data && typeof data.detail === "string" && data.detail) || t("error.generic"));
      err.status = res.status;
      err.retryable = !data || data.retryable !== false;
      throw err;
    }
    return data;
  }

  /* ---------- Remembered trainee / assessment (per-viewer convenience only) ---------- */

  const store = {
    get(key) {
      try {
        return localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, value);
      } catch {
        /* storage unavailable */
      }
    },
    remove(key) {
      try {
        localStorage.removeItem(key);
      } catch {
        /* storage unavailable */
      }
    },
  };

  /* ---------- Icons (inline SVG, stroke style) ---------- */

  const ICONS = {
    home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
    clipboard: "M9 4h6v3H9zM7 5H5v16h14V5h-2M9 12h6M9 16h4",
    chart: "M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6",
    compass: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM15.5 8.5l-2 5-5 2 2-5z",
    trophy: "M8 4h8v5a4 4 0 0 1-8 0zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8 21h8M10 17h4",
    bell: "M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0",
    flame: "M12 3c1 3 5 5 5 10a5 5 0 0 1-10 0c0-3 2-4 2-7 1 1 2 2 3 3 0-2 0-4 0-6z",
    check: "M5 12.5 10 17l9-10",
    lock: "M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z",
    play: "M8 5v14l11-7z",
    arrow: "M5 12h14M13 6l6 6-6 6",
    back: "M19 12H5M11 6l-6 6 6 6",
    book: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 5v16",
    bulb: "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z",
    star: "m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
    globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18",
    sparkle: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6",
    search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5",
    refresh: "M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4",
    terminal: "M4 5h16v14H4zM7 9l3 3-3 3M12 15h5",
    database: "M12 8c4.4 0 8-1.3 8-3s-3.6-3-8-3-8 1.3-8 3 3.6 3 8 3zM4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
    shield: "M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6z",
    network: "M12 5a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM5 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM19 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM12 5v6M5 17l7-6 7 6",
    layers: "m12 3 9 5-9 5-9-5zM3 13l9 5 9-5",
    cpu: "M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4",
    plus: "M12 5v14M5 12h14",
    x: "M6 6l12 12M18 6 6 18",
    chat: "M4 5h16v11H9l-5 4z",
    door: "M4 21h16M6 21V4h9v17M15 6h3v15M11.5 12h.01",
    searchGlobe: "M11 19a8 8 0 1 1 7.4-11M3.5 9h7M11 3c-3 3.5-3 12.5 0 16M15.5 17.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM21 21l-3.4-3.4",
    dotsCircle: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8h.01M8.5 14.5h.01M15.5 14.5h.01",
    presentation: "M3 4h18v12h-7M7 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM2.5 20.5a4.5 4.5 0 0 1 9 0M14.5 8.5h3M14.5 11.5h2",
    users: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M17 3a4 4 0 0 1 0 8M22 21a7 7 0 0 0-5-6.7",
    briefcase: "M4 7h16v13H4zM9 7V4h6v3M4 12h16",
    download: "M12 4v12M6 10l6 6 6-6M4 20h16",
    hourglass: "M6 3h12M6 21h12M7 3c0 5 10 5 10 9s-10 4-10 9M17 3c0 5-10 5-10 9",
    flag: "M5 21V4M5 4h11l-2 4 2 4H5",
    bolt: "M13 2 4 14h7l-1 8 9-12h-7z",
    image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15.5 9.5h.01",
    file: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h5",
    flask: "M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3M7 15h10",
    info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5h.01",
    clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  };

  function svg(name, size = 20) {
    const ns = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(ns, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("width", size);
    s.setAttribute("height", size);
    s.setAttribute("fill", "none");
    s.setAttribute("stroke", "currentColor");
    s.setAttribute("stroke-width", "2");
    s.setAttribute("stroke-linecap", "round");
    s.setAttribute("stroke-linejoin", "round");
    s.setAttribute("aria-hidden", "true");
    s.classList.add("icon");
    s.dataset.icon = name; // lets RTL mirror directional icons
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", ICONS[name] || ICONS.sparkle);
    s.append(p);
    return s;
  }

  /* ---------- The coach mascot (a round owl) ---------- */

  function nudge(size = 56) {
    const ns = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(ns, "svg");
    s.setAttribute("viewBox", "0 0 64 64");
    s.setAttribute("width", size);
    s.setAttribute("height", size);
    s.setAttribute("aria-hidden", "true");
    s.classList.add("nudge");
    const parts = [
      ["circle", { cx: 32, cy: 33, r: 29, fill: "var(--coach-ring)" }],
      ["circle", { cx: 32, cy: 32, r: 26, fill: "var(--coach-body)" }],
      ["circle", { cx: 23, cy: 29, r: 8.5, fill: "#fff" }],
      ["circle", { cx: 41, cy: 29, r: 8.5, fill: "#fff" }],
      ["circle", { cx: 23, cy: 29.5, r: 4.6, fill: "#0b1f24" }],
      ["circle", { cx: 41, cy: 29.5, r: 4.6, fill: "#0b1f24" }],
      ["circle", { cx: 24.6, cy: 27.8, r: 1.6, fill: "#fff" }],
      ["circle", { cx: 42.6, cy: 27.8, r: 1.6, fill: "#fff" }],
      ["circle", { cx: 15.5, cy: 38, r: 3.2, fill: "#d4b26a", opacity: 0.55 }],
      ["circle", { cx: 48.5, cy: 38, r: 3.2, fill: "#d4b26a", opacity: 0.55 }],
      ["path", { d: "M29 37h6l-3 4.2z", fill: "#f4b860" }],
    ];
    for (const [tag, attrs] of parts) {
      const n = document.createElementNS(ns, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
      s.append(n);
    }
    return s;
  }

  /* Drawn icons for the five learning activities (no emoji). */
  const ACTIVITY_ICONS = { escape_room: "door", gap_hunter: "searchGlobe", work_challenge: "briefcase", shadow: "dotsCircle", teach_others: "presentation" };
  const activityIcon = (type, size = 30) => svg(ACTIVITY_ICONS[type] || "sparkle", size);

  /* ---------- App shell: sidebar + top bar ---------- */

  const NAV = [
    ["home", "home", () => "index.html"],
    ["skills", "briefcase", () => (store.get("journey_id") ? `skills.html?id=${encodeURIComponent(store.get("journey_id"))}` : "skills.html")],
    ["journey", "compass", () => (store.get("journey_id") ? `journey.html?id=${encodeURIComponent(store.get("journey_id"))}` : "skills.html")],
    ["badges", "trophy", () => "badges.html"],
  ];

  function langToggle() {
    const other = lang() === "en" ? "ar" : "en";
    const b = el("button", { className: "pill lang-toggle", type: "button", title: t("shell.language") }, svg("globe", 16), el("span", { text: t(`lang.${other}`) }));
    b.addEventListener("click", () => {
      I18n.setLang(other);
      location.reload();
    });
    return b;
  }

  function shell(active) {
    const nav = el("nav", { className: "side-nav", attrs: { "aria-label": t("shell.menu") } },
      ...NAV.map(([key, icon, href]) => el("a", { className: `nav-link ${key === active ? "active" : ""}`, href: href() }, svg(icon), el("span", { text: t(`nav.${key}`) }))));
    const sidebar = el("aside", { className: "sidebar" },
      el("a", { className: "brand", href: "index.html" }, el("span", { className: "brand-mark" }, svg("cpu", 22)),
        el("span", { className: "brand-text" }, el("strong", { text: "Intelligent" }), el("small", { text: "LEARNING" }))),
      nav,
      el("div", { className: "side-nudge" }, nudge(40), el("div", {}, el("strong", { text: t("coach.name") }, el("span", { className: "online-dot" })), el("span", { text: t("shell.nudge_ready") }))));

    const streak = el("span", { className: "pill", id: "streak-pill", title: t("shell.streak_hint") }, svg("flame", 16), el("span", { text: t("shell.streak", { n: 0 }) }));
    const avatar = el("a", { className: "avatar", href: NAV[1][2](), title: t("nav.skills") }, svg("user", 18));
    const logout = el("button", { className: "pill", type: "button", title: t("shell.sign_out") }, svg("back", 16), el("span", { text: t("shell.sign_out") }));
    logout.addEventListener("click", signOut);
    const topbar = el("header", { className: "topbar" }, streak, langToggle(), store.get("trainee_id") ? logout : null, avatar);

    const main = document.querySelector("main");
    const layout = el("div", { className: "app-layout" }, sidebar, el("div", { className: "app-main" }, topbar));
    main.parentNode.insertBefore(layout, main);
    layout.querySelector(".app-main").append(main);
    refreshProgress();
  }

  /* Forget the ID on this device (shared computers). */
  function signOut() {
    ["trainee_id", "journey_id", "assessment_id"].forEach((k) => store.remove(k));
    location.href = "index.html";
  }

  async function refreshProgress() {
    const tid = store.get("trainee_id");
    if (!tid) return null;
    try {
      const p = await api("GET", `/api/trainees/${encodeURIComponent(tid)}/progress`);
      const pill = $("streak-pill");
      if (pill) pill.querySelector("span").textContent = t("shell.streak", { n: p.streak_days });
      return p;
    } catch {
      return null;
    }
  }

  /* ---------- Small widgets ---------- */

  function bar(percent, target, className = "") {
    const fill = el("div", { className: "bar-fill" });
    fill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    if (target !== undefined && percent < target) fill.classList.add("below");
    const wrap = el("div", { className: `bar ${className}` }, fill);
    if (target !== undefined) {
      const mark = el("div", { className: "bar-target" });
      mark.style.insetInlineStart = `${target}%`;
      wrap.append(mark);
    }
    return wrap;
  }

  function chip(text, kind = "", icon) {
    return el("span", { className: `chip-tag ${kind}` }, icon ? svg(icon, 14) : null, el("span", { text }));
  }

  /* Table ("a | b" with header), code/log/config (monospace) or plain text lines. */
  function artifact(lines, kind) {
    if (!lines || !lines.length || kind === "none") return null;
    const looksTable = kind === "table" || (!kind && lines[0].includes("|"));
    if (looksTable) {
      const rows = lines.map((l) => l.split("|").map((c) => c.trim()));
      return el("div", { className: "table-wrap" },
        el("table", { className: "data-table" },
          el("thead", {}, el("tr", {}, ...rows[0].map((c) => el("th", { text: c })))),
          el("tbody", {}, ...rows.slice(1).map((r) => el("tr", {}, ...r.map((c) => el("td", { text: c })))))));
    }
    if (kind === "text") return el("ul", { className: "plain-list" }, ...lines.map((l) => el("li", { text: l })));
    return el("pre", { className: "code", dir: "ltr" }, el("code", { text: lines.join("\n") }));
  }

  function loadingView(text, hint = "") {
    return el("div", { className: "card center loading-card", attrs: { "aria-live": "polite" } },
      nudge(72), el("div", { className: "spinner" }), el("p", { className: "loading-text", text }), hint ? el("p", { className: "hint", text: hint }) : null);
  }

  // Items shown inside a numbered list must not carry their own "1)" / "2." prefix.
  const plain = (text) => String(text ?? "").replace(/^\s*(?:(?:step|الخطوة|خطوة)\s*)?[([]?[0-9٠-٩]{1,2}\s*(?:[)\]]|[.:\-–—](?=\s))\s*/i, "").trim() || String(text ?? "").trim();

  return { plain, signOut, el, button, $, api, store, svg, nudge, activityIcon, shell, refreshProgress, bar, chip, artifact, loadingView, t, lang };
})();
