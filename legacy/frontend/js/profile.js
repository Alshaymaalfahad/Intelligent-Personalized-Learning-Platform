/* Trainee profile: field → interests (3 suggested + your own) → optional goal → start the assessment. */
(() => {
  const { el, button, svg, nudge, api, store, shell, chip, t, lang } = App;
  shell("profile");
  document.title = t("profile.title");

  const MAX_INTERESTS = 6;
  const OTHER = "__other__";
  const SPEC_ICONS = {
    "Software Engineering": "terminal", "Information Systems": "layers", "Computer Science": "cpu",
    Cybersecurity: "shield", "Data Science and AI": "database", "Network Engineering": "network",
  };
  const params = new URLSearchParams(location.search);
  const page = document.getElementById("page");
  let catalog = [];
  let spec = null; // selected catalog entry, or OTHER
  let picked = new Set(); // catalog interest names
  let custom = []; // trainee-typed interests
  const state = { goal: "", customSpec: "" };

  const specLabel = (s) => (lang() === "ar" ? s.label_ar : s.name);
  const interestLabel = (i) => (lang() === "ar" ? i.label_ar : i.name);

  /* ---------- Existing profile ---------- */

  async function showProfile(id) {
    let p;
    try {
      p = await api("GET", `/api/trainees/${encodeURIComponent(id)}`);
    } catch (e) {
      return page.replaceChildren(el("div", { className: "card" }, el("p", { className: "error", text: e.message })));
    }
    store.set("trainee_id", p.trainee_id);
    const progress = await api("GET", `/api/trainees/${encodeURIComponent(id)}/progress`).catch(() => null);
    const latest = progress && progress.latest_assessment;
    const errorLine = el("p", { className: "error" });
    const start = button(t("profile.new_assessment"), "", async () => {
      start.disabled = true;
      try {
        const a = await api("POST", "/api/assessments", { trainee_id: p.trainee_id });
        store.set("assessment_id", a.assessment_id);
        location.href = `assessment.html?id=${encodeURIComponent(a.assessment_id)}`;
      } catch (e) {
        start.disabled = false;
        errorLine.textContent = e.message;
      }
    }, "play");
    page.replaceChildren(
      el("section", { className: "card welcome" },
        el("div", {}, el("span", { className: "eyebrow", text: t("profile.saved_eyebrow") }), el("h1", { text: t("profile.saved_title") }),
          el("p", { className: "muted", text: `${t("profile.trainee_id")}: ${p.trainee_id}` })),
        el("div", { className: "coach-card" }, nudge(64), el("p", { text: t("profile.saved_coach") }))),
      el("section", { className: "card" },
        el("div", { className: "grid grid-2" },
          el("div", {}, el("span", { className: "eyebrow", text: t("profile.field") }), el("h3", { text: p.specialization })),
          el("div", {}, el("span", { className: "eyebrow", text: t("profile.interests") }), el("div", { className: "chips" }, ...p.interests.map((i) => chip(i, "cyan")))),
          el("div", {}, el("span", { className: "eyebrow", text: t("profile.goal") }), el("p", { text: p.additional_message || "—" })),
          el("div", {}, el("span", { className: "eyebrow", text: t("profile.content_language") }), el("p", { text: t(`lang.${p.language || "ar"}`) }))),
        el("div", { className: "actions" }, start,
          latest ? el("a", { className: "btn btn-secondary", href: latest.status === "completed" ? `report.html?id=${latest.assessment_id}` : `assessment.html?id=${latest.assessment_id}`, text: t("profile.continue_latest") }) : null),
        errorLine));
  }

  /* ---------- New profile form ---------- */

  function stepsHeader() {
    const filled = [true, !!spec, picked.size + custom.length > 0];
    return el("div", { className: "steps-header" }, ...["field", "interests", "goal"].map((k, i) =>
      el("div", { className: `sh ${filled[i] ? "on" : ""}` }, el("span", { className: "dot", text: String(i + 1) }), el("span", { text: t(`profile.step_${k}`) }))));
  }

  function fieldCards() {
    const cards = catalog.map((s) => {
      const b = el("button", { className: "field-card", type: "button", attrs: { "aria-pressed": String(spec === s) } },
        el("span", { className: "icon-badge" }, svg(SPEC_ICONS[s.name] || "sparkle", 22)),
        el("strong", { text: specLabel(s) }), el("span", { text: t(`spec.${s.name}`) }));
      b.addEventListener("click", () => {
        spec = s;
        picked = new Set();
        render();
      });
      return b;
    });
    const other = el("button", { className: "field-card", type: "button", attrs: { "aria-pressed": String(spec === OTHER) } },
      el("span", { className: "icon-badge" }, svg("plus", 22)), el("strong", { text: t("profile.other_field") }), el("span", { text: t("profile.other_field_desc") }));
    other.addEventListener("click", () => {
      spec = OTHER;
      picked = new Set();
      render();
    });
    return el("div", { className: "field-grid" }, ...cards, other);
  }

  function interestsBox() {
    const box = el("div", { className: "card" }, el("h2", { text: t("profile.interests_title") }), el("p", { className: "muted small", text: t("profile.interests_sub") }));
    if (!spec) {
      box.append(el("p", { className: "hint", text: t("profile.pick_field_first") }));
      return box;
    }
    const chips = el("div", { className: "chips" });
    if (spec !== OTHER) {
      for (const i of spec.interests) {
        const on = picked.has(i.name);
        const b = el("button", { className: "chip-toggle", type: "button", attrs: { "aria-pressed": String(on) } }, svg(on ? "check" : "plus", 16), el("span", { text: interestLabel(i) }));
        b.addEventListener("click", () => {
          if (on) picked.delete(i.name);
          else if (picked.size + custom.length < MAX_INTERESTS) picked.add(i.name);
          render();
        });
        chips.append(b);
      }
    }
    for (const name of custom) {
      const remove = el("button", { className: "chip-remove", type: "button", text: "×", attrs: { "aria-label": t("profile.remove", { name }) } });
      remove.addEventListener("click", () => {
        custom = custom.filter((n) => n !== name);
        render();
      });
      chips.append(el("span", { className: "chip-toggle", attrs: { "aria-pressed": "true" } }, el("span", { text: name }), remove));
    }
    const input = el("input", { type: "text", id: "own-interest", attrs: { maxlength: "60", placeholder: t("profile.add_own_placeholder"), "aria-label": t("profile.add_own") } });
    const add = () => {
      const name = input.value.trim();
      if (!name || picked.size + custom.length >= MAX_INTERESTS) return;
      const known = spec !== OTHER && spec.interests.some((i) => [i.name, i.label_ar].map((x) => x.toLowerCase()).includes(name.toLowerCase()));
      if (known || custom.some((c) => c.toLowerCase() === name.toLowerCase())) return (input.value = "");
      custom.push(name);
      render();
      document.getElementById("own-interest")?.focus();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        add();
      }
    });
    box.append(chips,
      el("div", { className: "inline-add" }, input, button(t("profile.add"), "btn-secondary btn-small", add, "plus")),
      el("p", { className: "hint", text: t("profile.selected_count", { n: picked.size + custom.length, max: MAX_INTERESTS }) }));
    return box;
  }

  function goalBox() {
    const ta = el("textarea", { attrs: { rows: "4", maxlength: "500", placeholder: t("profile.goal_placeholder") } });
    ta.value = state.goal;
    const counter = el("span", { className: "hint", text: `${ta.value.length}/500` });
    ta.addEventListener("input", () => {
      state.goal = ta.value;
      counter.textContent = `${ta.value.length}/500`;
    });
    return el("div", { className: "card" }, el("h2", { text: t("profile.goal_title") }),
      el("p", { className: "muted small", text: t("profile.goal_sub") }), ta, counter);
  }

  function render() {
    const errorLine = el("p", { className: "error", id: "form-error" });
    const customSpec = el("input", { type: "text", attrs: { maxlength: "100", placeholder: t("profile.other_field_placeholder") } });
    customSpec.value = state.customSpec;
    customSpec.addEventListener("input", () => (state.customSpec = customSpec.value));
    const start = button(t("profile.start"), "btn-big", submit, "arrow");
    start.id = "start-btn";
    page.replaceChildren(
      stepsHeader(),
      el("section", { className: "card welcome" },
        el("div", {}, el("span", { className: "eyebrow", text: t("profile.eyebrow") }), el("h1", { text: t("profile.headline") }),
          el("p", { className: "muted", text: t("profile.subhead") })),
        el("div", { className: "coach-card" }, nudge(64), el("div", {}, el("span", { className: "eyebrow", text: t("profile.coach_name") }), el("p", { text: t("profile.coach") })))),
      el("div", { className: "head-row" }, el("h2", { text: t("profile.field_title") }), el("span", { className: "small", text: t("profile.field_hint") })),
      fieldCards(),
      spec === OTHER ? el("div", { className: "card flat other-field" }, customSpec) : null,
      el("div", { className: "grid grid-2 form-grid" }, interestsBox(), goalBox()),
      el("div", { className: "banner" }, el("span", { className: "icon-badge" }, svg("hourglass", 22)),
        el("div", {}, el("span", { className: "eyebrow", text: t("profile.safe_eyebrow") }), el("p", { text: t("profile.safe") }),
          el("p", { className: "hint", text: t("profile.language_note", { language: t(`lang.${lang()}`) }) }))),
      errorLine,
      el("div", { className: "actions between" }, el("a", { className: "btn btn-secondary", href: "index.html" }, el("span", { text: t("profile.back") })), start));
  }

  async function submit() {
    const err = document.getElementById("form-error");
    const specialization = spec === OTHER ? state.customSpec.trim() : spec && spec.name;
    const interests = [...picked, ...custom];
    if (!specialization || specialization.length < 2) return (err.textContent = t("profile.err_field"));
    if (!interests.length) return (err.textContent = t("profile.err_interests"));
    const btn = document.getElementById("start-btn");
    btn.disabled = true;
    try {
      const trainee = await api("POST", "/api/trainees", {
        language: lang(), specialization, interests, additional_message: state.goal.trim() || null,
      });
      store.set("trainee_id", trainee.trainee_id);
      const a = await api("POST", "/api/assessments", { trainee_id: trainee.trainee_id });
      store.set("assessment_id", a.assessment_id);
      location.href = `assessment.html?id=${encodeURIComponent(a.assessment_id)}`;
    } catch (e) {
      btn.disabled = false;
      err.textContent = e.status === 422 ? t("profile.err_invalid") : e.message;
    }
  }

  (async () => {
    if (params.get("id")) return showProfile(params.get("id"));
    try {
      catalog = await api("GET", "/api/specializations");
    } catch (e) {
      return page.replaceChildren(el("div", { className: "card" }, el("p", { className: "error", text: e.message })));
    }
    render();
  })();
})();
