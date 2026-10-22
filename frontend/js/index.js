/* Landing page: what the platform does, how it works, the five activities, and "continue". */
(() => {
  const { el, button, svg, nudge, activityIcon, api, store, t, lang } = App;
  document.title = t("landing.title");

  async function continueWith(raw) {
    const id = raw.trim().toUpperCase();
    if (!id) return;
    const error = document.getElementById("continue-error");
    error.textContent = "";
    try {
      const p = await api("GET", `/api/trainees/${encodeURIComponent(id)}/progress`);
      store.remove("pending_id");
      store.set("trainee_id", p.trainee_id);
      if (!p.journey_id) return (location.href = "skills.html");
      store.set("journey_id", p.journey_id);
      location.href = p.journey_complete ? "skills.html" : `journey.html?id=${encodeURIComponent(p.journey_id)}`;
    } catch (e) {
      error.textContent = e.status === 404 ? t("landing.not_found") : e.message;
    }
  }

  /* «Pick my skills» always asks for the ID first: a known ID goes to its journey;
     a new one is confirmed, then the trainee picks skills and signs up with it. */
  const ID_RULE = /^(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9_-]{6,20}$/;

  function openIdDialog() {
    const input = el("input", { type: "text", id: "start-id", dir: "ltr", attrs: { maxlength: "20", autocomplete: "off", spellcheck: "false", "aria-describedby": "start-id-rule" } });
    input.value = store.get("trainee_id") || "";
    const error = el("p", { className: "error", attrs: { role: "alert" } });
    const go = el("button", { className: "btn btn-big", type: "submit" }, el("span", { text: t("landing.continue") }), svg("arrow", 20));
    const form = el("form", { className: "id-form" },
      el("label", { attrs: { for: "start-id" } }, el("strong", { text: t("signup.label") })), input,
      el("p", { className: "hint", id: "start-id-rule", text: t("signup.rule") }), error, go);
    const close = button("", "btn-small btn-secondary icon-only", () => dlg.close(), "x");
    close.setAttribute("aria-label", t("skills.close"));
    const body = el("div", {}, el("p", { className: "muted", text: t("start.sub") }), form);
    const dlg = el("dialog", { className: "info-dialog", attrs: { "aria-labelledby": "start-title" } },
      el("div", { className: "head-row" }, el("h2", { id: "start-title", text: t("start.title") }), close), body);

    function confirmNew(id) {
      const create = el("button", { className: "btn btn-big", type: "button" }, el("span", { text: t("start.create") }), svg("arrow", 20));
      create.addEventListener("click", () => {
        ["trainee_id", "journey_id", "assessment_id"].forEach((k) => store.remove(k));
        store.set("pending_id", id);
        location.href = "skills.html";
      });
      body.replaceChildren(
        el("p", {}, el("span", { text: t("start.new_id") }), el("strong", { text: ` ${id}`, dir: "ltr" })),
        el("p", { className: "notice small", text: t("signup.keep_it") }),
        el("div", { className: "actions between" }, button(t("start.back"), "btn-secondary", () => {
          body.replaceChildren(el("p", { className: "muted", text: t("start.sub") }), form);
          input.focus();
        }), create));
      create.focus();
    }

    input.addEventListener("input", () => (error.textContent = ""));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = input.value.trim().toUpperCase();
      if (!ID_RULE.test(id)) return (error.textContent = t("signup.invalid"));
      go.disabled = true;
      try {
        const p = await api("GET", `/api/trainees/${encodeURIComponent(id)}/progress`);
        store.remove("pending_id");
        store.set("trainee_id", p.trainee_id);
        if (p.journey_id) store.set("journey_id", p.journey_id);
        location.href = p.journey_id && !p.journey_complete ? `journey.html?id=${encodeURIComponent(p.journey_id)}` : "skills.html";
      } catch (err) {
        go.disabled = false;
        if (err.status === 404) confirmNew(id);
        else error.textContent = err.message;
      }
    });
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
    input.focus();
  }

  const other = lang() === "en" ? "ar" : "en";
  const langBtn = el("button", { className: "pill", type: "button" }, svg("globe", 16), el("span", { text: t(`lang.${other}`) }));
  langBtn.addEventListener("click", () => {
    I18n.setLang(other);
    location.reload();
  });

  const input = el("input", { type: "text", attrs: { placeholder: t("landing.continue_placeholder"), dir: "ltr", "aria-label": t("landing.continue_label") } });
  const form = el("form", {}, input, el("button", { className: "btn btn-small", type: "submit", text: t("landing.continue") }));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    continueWith(input.value);
  });

  const steps = ["pick", "level", "map", "learn", "progress"];
  const STEP_ICONS = { pick: "search", level: "chart", map: "compass", learn: "play", progress: "briefcase" };
  const activities = ["escape_room", "gap_hunter", "work_challenge", "shadow", "teach_others"];

  const page = el("div", { className: "landing" },
    el("header", { className: "landing-nav" },
      el("a", { className: "brand", href: "index.html" }, el("span", { className: "brand-mark" }, svg("cpu", 22)),
        el("span", { className: "brand-text" }, el("strong", { text: "Intelligent" }), el("small", { text: "LEARNING PLATFORM" }))),
      el("nav", {}, el("a", { href: "#how", text: t("landing.nav_how") }), el("a", { href: "#activities", text: t("landing.nav_activities") }), langBtn)),

    el("section", { className: "hero" },
      el("div", {},
        el("span", { className: "chip-tag" }, svg("sparkle", 14), el("span", { text: t("landing.badge") })),
        el("h1", { text: t("landing.headline") }),
        el("p", { className: "muted", text: t("landing.subhead") }),
        el("div", { className: "hero-actions" },
          startButton(),
          el("div", { className: "continue-box", id: "continue" }, el("strong", { className: "small", text: t("landing.already") }), form,
            el("p", { className: "error", id: "continue-error" })))),
      heroArt()),

    el("h2", { className: "section-title", id: "how", text: t("landing.how_title") }),
    el("p", { className: "center muted", text: t("landing.how_sub") }),
    el("ol", { className: "how-row" }, ...steps.map((s, i) =>
      el("li", { className: "card how-step" }, el("div", { className: "num", text: String(i + 1) }),
        el("h3", { text: t(`landing.step_${s}`) }), el("p", { className: "muted small", text: t(`landing.step_${s}_desc`) }),
        el("span", { className: "chip-tag" }, svg(STEP_ICONS[s], 14), el("span", { text: t(`landing.step_${s}_tag`) }))))),

    el("div", { className: "card nudge-say tip-card" }, nudge(56),
      el("div", {}, el("strong", { text: t("landing.tip_title") }), el("p", { text: t("landing.tip") }))),

    el("h2", { className: "section-title", id: "activities", text: t("landing.activities_title") }),
    el("p", { className: "center muted", text: t("landing.activities_sub") }),
    el("div", { className: "activity-grid" }, ...activities.map((a) =>
      el("div", { className: `card activity-card tone-${a}` },
        el("div", { className: "icon-badge" }, activityIcon(a)),
        el("h3", { text: t(`activity.${a}.name`) }),
        el("p", { className: "muted", text: t(`activity.${a}.summary`) }),
        el("div", { className: "meta" }, el("span", { className: "chip-tag white", text: t(`activity.${a}.best_for`) }))))),

    el("footer", { className: "footer" }, el("strong", { text: "Intelligent Learning" }), el("span", { text: t("landing.footer") })));

  function startButton() {
    const b = el("button", { className: "btn btn-big hero-start", type: "button" }, el("span", { text: t("landing.start") }), svg("arrow", 20));
    b.addEventListener("click", openIdDialog);
    return b;
  }

  function heroArt() {
    // A dashed path rising from the start dot, passing behind "Step 2: Learn", up to the goal.
    const ns = "http://www.w3.org/2000/svg";
    const path = document.createElementNS(ns, "svg");
    path.setAttribute("aria-hidden", "true");
    path.classList.add("rise-path");
    const line = document.createElementNS(ns, "path");
    path.append(line);
    const learn = el("span", { className: "on", text: t("landing.art_learn") });
    const art = el("div", { className: "hero-art" }, path, el("span", { className: "dot-start" }), el("span", { className: "dot-goal" }),
      el("span", { className: "chip-tag amber trophy-chip" }, svg("trophy", 16), el("span", { text: t("landing.art_trophy") })),
      el("div", { className: "owl-wrap" }, nudge(150), el("span", { className: "wave", text: "👋", attrs: { "aria-hidden": "true" } })),
      el("div", { className: "path-steps" }, el("span", { text: t("landing.art_check") }), svg("arrow", 16), learn, svg("arrow", 16), el("span", { text: t("landing.art_win") })),
      el("div", { className: "next-bar" }, el("span", { text: t("landing.art_next") }), el("span", { className: "next-tag" }, svg("bolt", 16), el("span", { text: t("landing.art_baseline") }))));

    // Drawn from the real positions, so it always runs behind the middle step at any screen size.
    const draw = () => {
      const box = art.getBoundingClientRect();
      if (!box.width) return;
      const center = (node) => {
        const r = node.getBoundingClientRect();
        return { x: r.left + r.width / 2 - box.left, y: r.top + r.height / 2 - box.top };
      };
      const a = center(art.querySelector(".dot-start"));
      const m = center(learn);
      const b = center(art.querySelector(".dot-goal"));
      path.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
      line.setAttribute("d", [
        `M ${a.x} ${a.y}`,
        `C ${a.x + (m.x - a.x) * 0.45} ${a.y}, ${m.x - (m.x - a.x) * 0.35} ${m.y + 6}, ${m.x} ${m.y}`,
        `C ${m.x + (b.x - m.x) * 0.45} ${m.y - 8}, ${b.x} ${m.y - (m.y - b.y) * 0.35}, ${b.x} ${b.y}`,
      ].join(" "));
    };
    new ResizeObserver(draw).observe(art);
    document.fonts?.ready.then(draw);
    return art;
  }

  document.getElementById("page").replaceWith(page);
})();
