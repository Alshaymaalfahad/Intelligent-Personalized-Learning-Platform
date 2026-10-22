/* Skills: pick the skills to develop (stages → axes → skills), optionally rate your level,
   and start the learning journey. A new trainee signs up with an ID they choose. Once the
   journey starts the picks are locked; the next round opens when every station is done. */
(() => {
  const { el, button, svg, nudge, api, store, shell, chip, activityIcon, loadingView, t } = App;
  shell("skills");
  document.title = t("skills.title");
  const page = document.getElementById("page");
  const DRAFT_KEY = "skills_draft";

  let cat; // localized catalog from the server
  const traineeId = store.get("trainee_id"); // set once signed up / signed in
  const pendingId = !traineeId && store.get("pending_id"); // a new ID confirmed on the home page
  const ID_RULE = /^(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9_-]{6,20}$/;
  const picked = new Map(); // skill_id -> { level, later }
  const dismissed = new Set(); // prerequisite suggestions the trainee declined
  let openAxis = null;
  let stageFilter = "all";
  let query = "";

  const skillsOf = (axisId) => cat.skills.filter((s) => s.axis === axisId);
  const skillById = (id) => cat.skills.find((s) => s.id === id);
  const axisById = (id) => cat.axes.find((a) => a.id === id);
  const levelName = (id) => cat.levels.find((l) => l.id === id).name;

  /* Lab order: work stage, then catalog order, with any picked prerequisite first (same as the server). */
  function labOrder(ids) {
    const stageIdx = Object.fromEntries(cat.stages.map((s, i) => [s.id, i]));
    const pos = Object.fromEntries(cat.skills.map((s, i) => [s.id, i]));
    const key = (id) => stageIdx[axisById(skillById(id).axis).stage] * 1000 + pos[id];
    const chosen = new Set(ids);
    const out = [];
    const place = (id) => {
      if (out.includes(id)) return;
      for (const pre of [...(cat.prerequisites[id] || [])].sort((a, b) => key(a) - key(b))) if (chosen.has(pre)) place(pre);
      out.push(id);
    };
    [...chosen].sort((a, b) => key(a) - key(b)).forEach(place);
    return out;
  }

  /* Active (at most max_active) and «later», as the journey will have them. */
  function plan() {
    const active = [];
    const later = [];
    let overflow = 0;
    for (const id of labOrder([...picked.keys()])) {
      const p = picked.get(id);
      if (p.later) later.push(id);
      else if (active.length < cat.max_active) active.push(id);
      else {
        later.push(id);
        overflow += 1;
      }
    }
    return { active, later, overflow };
  }

  function saveDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify([...picked.entries()]));
    } catch {
      /* storage unavailable */
    }
  }

  function toggle(id, on) {
    if (on) picked.set(id, picked.get(id) || { level: null, later: false });
    else picked.delete(id);
    saveDraft();
    draw();
  }

  /* ---------- Skill rows (level 2) ---------- */

  function infoDialog(skill) {
    const dlg = el("dialog", { className: "info-dialog", attrs: { "aria-label": skill.name } },
      el("div", { className: "head-row" }, el("h2", { text: skill.name }), button("", "btn-small btn-secondary icon-only", () => dlg.close(), "x")),
      el("h3", { text: t("skills.info_learn") }), el("p", { text: skill.learn }),
      el("h3", { text: t("skills.info_activity") }),
      el("div", { className: "info-activity" }, el("span", { className: `icon-badge tone-${skill.activity}` }, activityIcon(skill.activity, 22)),
        el("div", {}, el("strong", { text: t(`activity.${skill.activity}.name`) }), el("p", { className: "hint", text: t(`activity.${skill.activity}.summary`) }))),
      el("h3", { text: t("skills.info_example") }), el("p", { className: "example-box", text: skill.example }),
      el("p", { className: "hint" }, svg("clock", 14), el("span", { text: ` ${t("skills.minutes", { n: skill.minutes })}` })));
    dlg.querySelector(".icon-only").setAttribute("aria-label", t("skills.close"));
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
  }

  function skillRow(skill, showAxis = false) {
    const p = picked.get(skill.id);
    const box = el("input", { type: "checkbox", id: `sk-${skill.id}` });
    box.checked = !!p;
    box.addEventListener("change", () => toggle(skill.id, box.checked));
    const info = button("", "btn-small btn-secondary icon-only", () => infoDialog(skill), "info");
    info.setAttribute("aria-label", t("skills.info", { name: skill.name }));
    const level = p ? el("div", { className: "level-pick", attrs: { role: "group", "aria-label": t("skills.your_level") } },
      el("span", { className: "small", text: t("skills.your_level") }),
      ...cat.levels.map((l) => {
        const b = button(l.name, `btn-small ${p.level === l.id ? "" : "btn-secondary"}`, () => {
          p.level = p.level === l.id ? null : l.id;
          saveDraft();
          draw();
        });
        b.setAttribute("aria-pressed", String(p.level === l.id));
        return b;
      }),
      el("span", { className: "hint", text: t("skills.level_optional") })) : null;
    return el("div", { className: `skill-row ${p ? "on" : ""}` },
      el("div", { className: "skill-main" }, box,
        el("label", { attrs: { for: `sk-${skill.id}` } },
          showAxis ? el("span", { className: "hint", text: axisById(skill.axis).name }) : null,
          el("strong", { text: skill.name }), el("span", { className: "muted small", text: skill.can_do })),
        el("span", { className: "skill-meta" }, chip(t("skills.min_short", { n: skill.minutes }), "muted", "clock"), info)),
      level);
  }

  function axisPanel(axis) {
    const skills = skillsOf(axis.id);
    const all = skills.every((s) => picked.has(s.id));
    const whole = el("input", { type: "checkbox", id: `all-${axis.id}` });
    whole.checked = all;
    whole.addEventListener("change", () => {
      skills.forEach((s) => (whole.checked ? picked.set(s.id, picked.get(s.id) || { level: null, later: false }) : picked.delete(s.id)));
      saveDraft();
      draw();
    });
    return el("div", { className: "card axis-panel", id: `panel-${axis.id}` },
      el("div", { className: "head-row" },
        el("h3", {}, svg(axis.icon, 20), el("span", { text: ` ${axis.name}` })),
        el("label", { className: "whole-axis", attrs: { for: `all-${axis.id}` } }, whole, el("span", { text: t("skills.whole_axis") }))),
      ...skills.map((s) => skillRow(s)));
  }

  /* ---------- Axis cards (level 1) ---------- */

  function axisCard(axis) {
    const skills = skillsOf(axis.id);
    const count = skills.filter((s) => picked.has(s.id)).length;
    const card = el("button", { className: `axis-card ${openAxis === axis.id ? "open" : ""} ${count ? "has-picks" : ""}`, type: "button",
      attrs: { "aria-expanded": String(openAxis === axis.id), "aria-controls": `panel-${axis.id}` } },
      el("span", { className: "icon-badge" }, svg(axis.icon, 24)),
      el("strong", { text: axis.name }),
      el("span", { className: "muted small", text: axis.tagline }),
      el("span", { className: "axis-foot" }, el("span", { className: "small", text: t("skills.n_skills", { n: skills.length }) }),
        count ? chip(t("skills.n_of", { k: count, n: skills.length }), "green", "check") : null));
    card.addEventListener("click", () => {
      openAxis = openAxis === axis.id ? null : axis.id;
      draw();
      if (openAxis) document.getElementById(`panel-${axis.id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    return card;
  }

  function stageSection(stage) {
    const axes = cat.axes.filter((a) => a.stage === stage.id);
    const open = axes.find((a) => a.id === openAxis);
    return el("section", { className: "stage-section" },
      el("h2", { className: "stage-title" }, svg(stage.icon, 20), el("span", { text: stage.name })),
      el("div", { className: "axis-grid" }, ...axes.map(axisCard)),
      open ? axisPanel(open) : null);
  }

  function bundles() {
    return el("section", { className: "stage-section" },
      el("h2", { className: "stage-title" }, svg("star", 20), el("span", { text: t("skills.suggestions") })),
      el("div", { className: "bundle-grid" }, ...cat.bundles.map((b) => {
        const all = b.skills.every((id) => picked.has(id));
        return el("div", { className: "card bundle-card" },
          el("div", { className: "head-row" }, el("h3", {}, svg(b.icon, 18), el("span", { text: ` ${b.name}` })), all ? chip(t("skills.added"), "green", "check") : null),
          el("p", { className: "muted small", text: b.desc }),
          el("ul", { className: "plain-list" }, ...b.skills.map((id) => el("li", { className: "small", text: skillById(id).name }))),
          all ? null : button(t("skills.add_bundle"), "btn-small", () => {
            b.skills.forEach((id) => picked.set(id, picked.get(id) || { level: null, later: false }));
            saveDraft();
            draw();
          }, "plus"));
      })));
  }

  function searchResults() {
    const q = query.toLowerCase();
    const hits = cat.skills.filter((s) => [s.name, s.can_do, s.learn, axisById(s.axis).name].some((x) => x.toLowerCase().includes(q)));
    return el("section", { className: "stage-section" },
      el("h2", { className: "stage-title" }, svg("search", 20), el("span", { text: t("skills.results", { n: hits.length }) })),
      hits.length ? el("div", { className: "card axis-panel" }, ...hits.map((s) => skillRow(s, true))) : el("p", { className: "muted", text: t("skills.no_results") }));
  }

  /* ---------- «My journey» side panel ---------- */

  function suggestion() {
    for (const id of picked.keys()) {
      const missing = (cat.prerequisites[id] || []).find((pre) => !picked.has(pre) && !dismissed.has(`${id}>${pre}`));
      if (!missing) continue;
      return el("div", { className: "prereq-tip" },
        el("p", { className: "small" }, svg("bulb", 16), el("span", { text: ` ${t("skills.prereq", { skill: skillById(id).name, pre: skillById(missing).name })}` })),
        el("div", { className: "actions" },
          button(t("skills.add"), "btn-small", () => toggle(missing, true), "plus"),
          button(t("skills.no_thanks"), "btn-small btn-secondary", () => {
            dismissed.add(`${id}>${missing}`);
            draw();
          })));
    }
    return null;
  }

  function journeyPanel() {
    const { active, later, overflow } = plan();
    const minutes = active.reduce((sum, id) => sum + skillById(id).minutes, 0);
    const item = (id, isLater) => {
      const p = picked.get(id);
      const remove = button("", "btn-small btn-secondary icon-only", () => toggle(id, false), "x");
      remove.setAttribute("aria-label", t("skills.remove", { name: skillById(id).name }));
      const move = button(isLater ? t("skills.bring_back") : t("skills.postpone"), "btn-small btn-secondary", () => {
        p.later = !isLater;
        saveDraft();
        draw();
      });
      return el("li", { className: isLater ? "later" : "" },
        el("span", { className: "dot-ico" }, svg(isLater ? "hourglass" : "check", 14)),
        el("span", { className: "grow" }, el("span", { text: skillById(id).name }), p.level ? el("span", { className: "hint", text: ` · ${levelName(p.level)}` }) : null),
        isLater && !p.later ? null : move, remove);
    };
    const start = el("button", { className: "btn btn-big", type: "button" }, el("span", { text: t("skills.start_journey") }), svg("arrow", 20));
    start.addEventListener("click", async () => {
      if (traineeId) return submit(traineeId, false);
      if (!pendingId) return askForId();
      const refused = await submit(pendingId, true);
      if (refused) askForId(refused); // e.g. someone took this ID meanwhile
    });
    start.disabled = active.length === 0;
    return el("aside", { className: "card journey-panel" },
      el("h2", {}, svg("compass", 20), el("span", { text: ` ${t("skills.my_journey")}` })),
      active.length ? el("ul", { className: "pick-list" }, ...active.map((id) => item(id, false))) : el("p", { className: "muted small", text: t("skills.empty") }),
      overflow ? el("p", { className: "notice small", text: t("skills.overflow", { n: active.length + overflow, max: cat.max_active }) }) : null,
      later.length ? el("div", {}, el("p", { className: "sub-title", text: t("skills.later") }), el("ul", { className: "pick-list" }, ...later.map((id) => item(id, true)))) : null,
      suggestion(),
      el("div", { className: "panel-stats" },
        el("span", { text: t("skills.count", { k: active.length, max: cat.max_active }) }),
        el("span", {}, svg("clock", 14), el("span", { text: ` ${t("skills.about_hours", { h: Math.round(minutes / 30) / 2 })}` }))),
      pendingId ? el("p", { className: "hint center" }, el("span", { text: `${t("start.signing_up_as")} ` }), el("strong", { text: pendingId, dir: "ltr" })) : null,
      start);
  }

  /* ---------- Page ---------- */

  function draw() {
    const scrollY = window.scrollY;
    const focusedId = document.activeElement && document.activeElement.id;
    const search = el("input", { type: "search", id: "skill-search", attrs: { placeholder: t("skills.search"), "aria-label": t("skills.search") } });
    search.value = query;
    search.addEventListener("input", () => {
      query = search.value.trim();
      draw();
    });
    const filters = el("div", { className: "filter-row", attrs: { role: "group", "aria-label": t("skills.filter") } },
      ...[{ id: "all", name: t("skills.all") }, ...cat.stages].map((s) => {
        const b = el("button", { className: `pill ${stageFilter === s.id ? "active" : ""}`, type: "button", text: s.name, id: `stage-${s.id}` });
        b.addEventListener("click", () => {
          stageFilter = s.id;
          draw();
        });
        b.setAttribute("aria-pressed", String(stageFilter === s.id));
        return b;
      }));
    const stages = cat.stages.filter((s) => stageFilter === "all" || s.id === stageFilter);
    page.replaceChildren(el("div", { className: "split skills-page" },
      el("div", {},
        el("div", { className: "page-intro" },
          el("h1", { className: "big-title", text: t("skills.headline") }),
          el("p", { className: "muted", text: t("skills.sub") })),
        el("div", { className: "search-box" }, svg("search", 18), search),
        filters,
        query ? searchResults() : el("div", {}, stageFilter === "all" ? bundles() : null, ...stages.map(stageSection))),
      journeyPanel()));
    if (focusedId) {
      const again = document.getElementById(focusedId);
      if (again) {
        again.focus();
        if (again.type === "search") again.setSelectionRange(again.value.length, again.value.length);
      }
    }
    window.scrollTo(0, scrollY);
  }

  /* A new trainee picks their own ID: their key to come back, like a password. */
  function askForId(firstError) {
    const input = el("input", { type: "text", id: "new-id", dir: "ltr", attrs: { maxlength: "20", autocomplete: "off", spellcheck: "false", "aria-describedby": "id-rule" } });
    const error = el("p", { className: "error", attrs: { role: "alert" } });
    const confirmBtn = el("button", { className: "btn btn-big", type: "submit" }, el("span", { text: t("skills.start_journey") }), svg("arrow", 20));
    const form = el("form", { className: "id-form" },
      el("label", { attrs: { for: "new-id" } }, el("strong", { text: t("signup.label") })), input,
      el("p", { className: "hint", id: "id-rule", text: t("signup.rule") }),
      el("p", { className: "notice small", text: t("signup.keep_it") }),
      error, confirmBtn);
    const dlg = el("dialog", { className: "info-dialog", attrs: { "aria-labelledby": "signup-title" } },
      el("div", { className: "head-row" }, el("h2", { id: "signup-title", text: t("signup.title") }), button("", "btn-small btn-secondary icon-only", () => dlg.close(), "x")),
      el("p", { className: "muted", text: t("signup.sub") }), form,
      el("p", { className: "small" }, el("span", { text: `${t("signup.have_id")} ` }), el("a", { href: "index.html#continue", text: t("signup.sign_in") })));
    dlg.querySelector(".icon-only").setAttribute("aria-label", t("skills.close"));
    input.addEventListener("input", () => (error.textContent = ""));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = input.value.trim();
      if (!ID_RULE.test(id)) return (error.textContent = t("signup.invalid"));
      error.textContent = "";
      confirmBtn.disabled = true;
      const message = await submit(id, true, dlg);
      confirmBtn.disabled = false;
      if (message) error.textContent = message;
    });
    if (firstError) error.textContent = firstError;
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
    input.focus();
  }

  /* Creates the journey; returns an error message for the sign-up dialog if the ID is refused. */
  async function submit(id, isNew, dlg) {
    const { active, later } = plan();
    const selections = [...active, ...later].map((sid) => ({ skill_id: sid, level: picked.get(sid).level, later: later.includes(sid) && picked.get(sid).later }));
    const pause = new Promise((r) => setTimeout(r, 1200)); // a short, readable transition
    let j;
    try {
      if (!dlg) page.replaceChildren(el("div", { className: "building" }, loadingView(t("skills.building"), t("skills.building_hint"))));
      j = await api("POST", "/api/journeys", { trainee_id: id, new_trainee: isNew, language: I18n.lang(), selections });
    } catch (e) {
      if (dlg) return e.message;
      draw();
      if (isNew) return e.message; // shown in the sign-up dialog
      page.prepend(el("p", { className: "error", text: e.message }));
      return null;
    }
    if (dlg) {
      dlg.close();
      page.replaceChildren(el("div", { className: "building" }, loadingView(t("skills.building"), t("skills.building_hint"))));
    }
    store.remove("pending_id");
    store.set("trainee_id", j.trainee_id);
    store.set("journey_id", j.journey_id);
    store.set("assessment_id", j.journey_id);
    try {
      localStorage.removeItem(DRAFT_KEY);
    } catch {
      /* storage unavailable */
    }
    await pause;
    location.href = `journey.html?id=${encodeURIComponent(j.journey_id)}`;
    return null;
  }

  /* Picks are locked while a journey is in progress. */
  function lockedView(journey) {
    page.replaceChildren(el("div", { className: "card center locked-card" }, nudge(72),
      el("h1", {}, svg("lock", 24), el("span", { text: ` ${t("skills.locked_title")}` })),
      el("p", { className: "muted", text: t("skills.locked_sub", { done: journey.done, total: journey.stations.length }) }),
      el("ul", { className: "pick-list" }, ...journey.stations.map((s) =>
        el("li", { className: s.state === "done" ? "" : "later" }, el("span", { className: "dot-ico" }, svg(s.state === "done" ? "check" : "lock", 14)), el("span", { className: "grow", text: s.name })))),
      el("a", { className: "btn btn-big", href: `journey.html?id=${encodeURIComponent(journey.journey_id)}` }, el("span", { text: t("skills.to_journey") }), svg("arrow", 20))));
  }

  (async () => {
    page.replaceChildren(loadingView(t("skills.loading")));
    try {
      cat = await api("GET", "/api/skills");
      if (traineeId) {
        let p = null;
        try {
          p = await api("GET", `/api/trainees/${encodeURIComponent(traineeId)}/progress`);
        } catch (e) {
          if (e.status !== 404) throw e;
          App.signOut(); // the saved ID no longer exists
          return;
        }
        if (p.journey_id) {
          const j = await api("GET", `/api/journeys/${encodeURIComponent(p.journey_id)}`);
          if (!j.complete) return lockedView(j);
          j.later.forEach((l) => picked.set(l.skill_id, { level: null, later: false })); // the next round starts with the saved ones
        }
      }
      if (!picked.size) {
        try {
          const draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || "[]");
          draft.forEach(([id, p]) => cat.skills.some((s) => s.id === id) && picked.set(id, p));
        } catch {
          /* no draft */
        }
      }
      draw();
    } catch (e) {
      page.replaceChildren(el("div", { className: "card center" }, nudge(64), el("p", { className: "error", text: e.message })));
    }
  })();
})();
