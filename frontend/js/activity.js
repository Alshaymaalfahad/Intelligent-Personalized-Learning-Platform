/* Activity page: briefing (why → learn → together → quick check) → mission → levels → final
   challenge → result. Each activity's level body is drawn by its renderer (activity-*.js). */
(() => {
  const { el, button, svg, nudge, activityIcon, api, store, shell, bar, chip, artifact, loadingView, t } = App;
  shell("journey");

  const params = new URLSearchParams(location.search);
  let activityId = params.get("id");
  let assessmentId = params.get("assessment");
  let competencyId = params.get("competency");
  let activityType = params.get("type");
  const page = document.getElementById("page");

  let act = null; // activity view from the server
  let report = null;
  let step = null; // journey step of this gap
  let lessonInfo = null;
  let lesson = null;
  let levelState = {};
  let showMissionFirst = false;
  let mentorText = null;

  const STATIONS = ["why", "learn", "together", "check", "play", "boss"];
  const BADGES_BY_TYPE = {
    gap_hunter: ["hawk_eye", "zero_false_alarms", "boss_slayer", "ready"],
    escape_room: ["escape_artist", "independent", "boss_slayer", "ready"],
    work_challenge: ["client_star", "independent", "boss_slayer", "ready"],
    shadow: ["golden_collector", "expert_shadow", "boss_slayer", "ready"],
    teach_others: ["inspiring_teacher", "independent", "boss_slayer", "ready"],
  };
  const BADGE_ICONS = { hawk_eye: "🦅", zero_false_alarms: "🎯", boss_slayer: "👑", ready: "🏅", escape_artist: "🗝️", independent: "🧭", client_star: "⭐", golden_collector: "🃏", expert_shadow: "🥷", inspiring_teacher: "🎓" };
  const STYLE_ICONS = { story: "book", visual: "image", interactive: "bolt", brief: "file" };

  const actName = () => t(`activity.${activityType}.name`);
  const activityUrl = (type) => `activity.html?${new URLSearchParams({ assessment: assessmentId, competency: competencyId, type })}`;

  /* ---------- Layout ---------- */

  function stepper(current) {
    const idx = STATIONS.indexOf(current);
    const items = [];
    STATIONS.forEach((s, i) => {
      if (i) items.push(el("span", { className: `step-line ${i <= idx ? "done" : ""}` }));
      const state = i < idx ? "done" : i === idx ? "active" : "";
      items.push(el("span", { className: `step ${state}` }, el("span", { className: "dot" }, i < idx ? svg("check", 14) : el("span", { text: String(i + 1) })), el("span", { text: t(`station.${s}`) })));
    });
    return el("nav", { className: "stepper", attrs: { "aria-label": t("station.aria") } }, ...items);
  }

  function sidePanels() {
    const prog = (report && report.learning_progress && report.learning_progress[competencyId]) || null;
    // Only a measured score is shown: before the first final challenge there is nothing to show yet.
    const current = prog ? prog.current : step && !step.self_rated ? step.baseline_score : null;
    const earned = new Set((act && act.badges.map((b) => b.id)) || []);
    const coach = el("div", { className: "card side-panel" },
      el("div", { className: "nudge-say" }, nudge(48), el("div", {}, el("strong", { text: t("act.coach") }), el("div", { className: "hint", text: t("act.coach_role") }))),
      el("p", { className: "card soft", text: mentorText || t("act.coach_default") }));
    const progressCard = el("div", { className: "card side-panel" }, el("h3", {}, el("span", { text: t("act.your_progress") }), svg("chart", 18)),
      el("div", { className: "bar-row" }, el("span", { text: t("act.gap_mastery") }), el("strong", { text: current === null ? "—" : `${Math.round(current)}%` })),
      bar(current || 0, report ? report.target_score : 70),
      current === null ? el("p", { className: "hint", text: t("act.not_measured") }) : null,
      el("div", { className: "mini-stats" },
        el("div", {}, el("small", { text: "XP" }), el("strong", { text: String(act ? act.xp : 0) })),
        el("div", {}, el("small", { text: t("act.hints_used") }), el("strong", { text: String(act ? act.hints_used : 0) }))));
    const badges = el("div", { className: "card side-panel" }, el("h3", {}, el("span", { text: t("nav.badges") }), chip(t("act.unlocked", { n: earned.size }), "cyan")),
      ...BADGES_BY_TYPE[activityType].map((b) => el("div", { className: `badge-line ${earned.has(b) ? "earned" : "locked"}` },
        el("span", { className: "ico", text: BADGE_ICONS[b] }),
        el("div", {}, el("strong", { text: t(`badge.${b}.name`) }), el("span", { className: "hint", text: t(`badge.${b}.desc`) })))));
    const others = step ? [step.activity, ...step.alternatives].filter((a) => a.activity_type !== activityType) : [];
    const alt = el("div", { className: "card side-panel" }, el("h3", {}, el("span", { text: t("act.try_another") }), svg("compass", 18)),
      el("p", { className: "hint", text: t("act.try_another_sub") }),
      el("div", { className: "alt-grid" }, ...others.map((a) => el("a", { href: activityUrl(a.activity_type) }, activityIcon(a.activity_type, 20), el("span", { text: t(`activity.${a.activity_type}.name`) })))));
    return el("aside", {}, coach, progressCard, badges, alt);
  }

  function render(station, ...main) {
    page.replaceChildren(stepper(station), el("div", { className: "split" }, el("div", {}, ...main), sidePanels()));
    window.scrollTo({ top: 0 });
  }

  function loading(text, hint) {
    page.replaceChildren(loadingView(text, hint));
  }

  function fail(message, retry) {
    page.replaceChildren(el("div", { className: "card" }, el("h2", { text: t("error.title") }), el("p", { text: message }),
      retry ? el("div", { className: "actions" }, button(t("error.retry"), "", retry)) : null));
  }

  /* ---------- Entry ---------- */

  async function init() {
    loading(t("act.loading"));
    try {
      if (activityId) {
        act = await api("GET", `/api/activities/${encodeURIComponent(activityId)}`);
        assessmentId = act.assessment_id;
        competencyId = act.competency_id;
        activityType = act.activity.activity_type;
      }
      if (!assessmentId || !competencyId || !activityType) return fail(t("act.bad_link"));
      store.set("assessment_id", assessmentId);
      if (assessmentId.toUpperCase().startsWith("JR-")) store.set("journey_id", assessmentId.toUpperCase());
      report = await api("GET", `/api/assessments/${encodeURIComponent(assessmentId)}/report`);
      store.set("trainee_id", report.trainee_id);
      step = (report.learning_journey || []).find((s) => s.competency_id === competencyId);
      if (!step) return fail(t("act.not_in_journey"));
      lessonInfo = await api("GET", `/api/assessments/${encodeURIComponent(assessmentId)}/lessons/${encodeURIComponent(competencyId)}`);
      lesson = lessonInfo.lesson;
    } catch (e) {
      return fail(e.message, init);
    }
    document.title = actName();
    if (act) return drive();
    if (lesson && lesson.completed) return showActivityIntro();
    if (lesson) return showLesson("why");
    showLessonStart();
  }

  /* ---------- Briefing ---------- */

  function lessonCard(...children) {
    return el("div", { className: "card" }, el("span", { className: "eyebrow", text: t("lesson.briefing_for", { activity: actName(), gap: step.name }) }), ...children);
  }

  function nextButton(label, onClick) {
    return el("div", { className: "actions end" }, button(label, "btn-big", onClick, "arrow"));
  }

  function showLessonStart() {
    const info = lessonInfo;
    const styles = el("div", { className: "solutions" }, ...info.styles.map((s) =>
      button(`${t(`lesson.style.${s}`)}${s === info.suggested_style ? ` · ${t("lesson.best_for_you")}` : ""}`, s === info.suggested_style ? "" : "btn-secondary", () => createLesson(s), STYLE_ICONS[s])));
    render("why", el("div", { className: "mission-banner" }, el("span", { className: "chip-tag solid", text: t("lesson.before_adventure") }),
      el("h2", { text: t("lesson.start_title", { gap: step.name }) }), el("p", { text: t("lesson.start_sub", { activity: actName() }) })),
    el("div", { className: "card" },
      el("div", { className: "head-row" }, el("h3", { text: t("lesson.gap_type", { type: t(`depth.${info.depth}.label`) }) }), chip(t(`depth.${info.depth}.label`), "cyan")),
      el("p", { className: "muted", text: t(`depth.${info.depth}.desc`) }),
      el("h3", { text: t("lesson.how_explain") }),
      el("p", { className: "hint", text: info.suggested_style ? t("lesson.suggested_note") : t("lesson.pick_note") }),
      styles,
      info.can_skip ? el("div", { className: "actions" }, button(t("lesson.skip"), "btn-secondary", showActivityIntro)) : null));
  }

  async function createLesson(style) {
    loading(t("lesson.preparing"), t("lesson.preparing_hint"));
    try {
      lesson = await api("POST", `/api/assessments/${encodeURIComponent(assessmentId)}/lessons/${encodeURIComponent(competencyId)}`, { style });
    } catch (e) {
      return fail(e.message, () => createLesson(style));
    }
    showLesson("learn");
  }

  function explanationBlocks(l, interactive = true) {
    const sections = l.explanation.sections;
    if (l.style === "visual") {
      return el("div", { className: "visual-grid" }, ...sections.map((s) =>
        el("div", { className: "visual-block" }, el("span", { className: "visual-emoji", text: s.emoji || "•" }), el("strong", { text: s.heading }), el("p", { text: s.body }))));
    }
    if (l.style === "interactive" && interactive) {
      return el("div", {}, ...sections.map((s) => {
        const answer = el("div", { className: "hidden" }, el("p", { text: s.body }));
        const reveal = button(t("lesson.reveal"), "btn-small btn-secondary", () => {
          answer.classList.remove("hidden");
          reveal.remove();
        });
        return el("div", { className: "lesson-section" }, el("h3", { text: s.heading }), el("p", { className: "sub-title", text: `🤔 ${s.reveal_question}` }), reveal, answer);
      }));
    }
    return el("div", { className: l.style === "story" ? "story" : "" }, ...sections.map((s) =>
      el("div", { className: "lesson-section" }, el("h3", { text: l.style === "story" || !s.emoji ? s.heading : `${s.emoji} ${s.heading}` }), el("p", { text: s.body }))));
  }

  function keyIdeas(l) {
    return el("div", {}, el("h3", {}, svg("bulb", 20), el("span", { text: ` ${t("lesson.key_ideas")}` })),
      el("div", { className: "key-ideas" }, ...l.explanation.takeaways.map((k) => el("div", { className: "key-idea" }, el("div", { className: "ico" }, svg("check", 20)), el("p", { text: k })))));
  }

  function styleTabs(l) {
    return el("div", { className: "style-tabs", attrs: { role: "group", "aria-label": t("lesson.how_explain") } }, ...lessonInfo.styles.map((s) => {
      const b = button(t(`lesson.style.${s}`), `btn-small ${s === l.style ? "" : "btn-secondary"}`, () => {
        if (s !== l.style && confirm(t("lesson.switch_confirm"))) createLesson(s);
      }, STYLE_ICONS[s]);
      b.setAttribute("aria-pressed", String(s === l.style));
      return b;
    }));
  }

  function showLesson(station) {
    const l = lesson;
    if (station === "why") {
      mentorText = t("lesson.coach_why");
      return render("why", lessonCard(el("h1", { text: `🎬 ${l.why.title}` }), el("p", { className: "story-card", text: l.why.story }),
        el("p", { className: "warn-text", text: `${t("lesson.impact")}: ${l.why.impact}` }), nextButton(t("lesson.explain_me"), () => showLesson("learn"))));
    }
    if (station === "learn") {
      mentorText = t("lesson.coach_learn");
      return render("learn", lessonCard(
        el("div", { className: "head-row" }, el("h1", { text: l.explanation.title }), chip(t(`depth.${l.depth}.label`), "amber")),
        styleTabs(l), explanationBlocks(l), keyIdeas(l),
        el("div", { className: "banner" }, el("span", { className: "icon-badge" }, svg("star", 20)), el("div", {}, el("strong", { text: t("lesson.ready_title") }), el("p", { className: "hint", text: t("lesson.ready_sub") }))),
        nextButton(t("lesson.lets_practice"), () => showLesson("together"))));
    }
    if (station === "together") {
      mentorText = t("lesson.coach_together");
      const ex = l.example;
      const steps = el("ol", { className: "expert-steps" });
      let shown = 0;
      const final = el("div", { className: "hidden" });
      const more = button(t("lesson.next_step"), "btn-secondary", () => {
        const s = ex.steps[shown++];
        steps.append(el("li", {}, el("strong", { text: App.plain(s.step) }), el("div", { className: "hint", text: s.explanation })));
        if (shown >= ex.steps.length) {
          more.remove();
          final.classList.remove("hidden");
        }
      });
      const options = el("div", { className: "solutions" }, ...ex.final_options.map((o, i) => button(o, "btn-secondary step-card", async () => {
        options.querySelectorAll("button").forEach((b) => (b.disabled = true));
        try {
          const r = await api("POST", `/api/lessons/${encodeURIComponent(l.lesson_id)}/final-step`, { choice: i });
          options.children[r.correct_index].classList.add("selected");
          final.append(el("p", { className: r.correct ? "ok-text" : "warn-text", text: `${r.correct ? t("lesson.right") : t("lesson.right_step", { step: ex.final_options[r.correct_index] })} ${r.explanation}` }),
            nextButton(t("lesson.quick_check"), () => showLesson("check")));
        } catch (e) {
          final.append(el("p", { className: "error", text: e.message }));
        }
      })));
      final.append(el("h3", { text: `👉 ${t("lesson.your_turn")}: ${ex.final_question}` }), options);
      return render("together", lessonCard(el("h1", { text: `🤝 ${t("station.together")}` }), el("p", { className: "muted", text: t("lesson.together_sub") }),
        el("p", { text: ex.problem }), artifact(ex.lines), steps, el("div", { className: "actions" }, more), final));
    }
    if (station === "check") {
      mentorText = t("lesson.coach_check");
      let answered = 0;
      const done = el("div", { className: "hidden" }, nextButton(t("lesson.start_activity", { activity: actName() }), startActivity));
      const qs = l.check.map((q, idx) => {
        const fb = el("div", {});
        const opts = el("div", { className: "solutions" }, ...q.options.map((o, i) => button(o, "btn-secondary step-card", async () => {
          opts.querySelectorAll("button").forEach((b) => (b.disabled = true));
          try {
            const r = await api("POST", `/api/lessons/${encodeURIComponent(l.lesson_id)}/check`, { index: idx, choice: i });
            opts.children[r.correct_index].classList.add("selected");
            fb.append(el("p", { className: r.correct ? "ok-text" : "warn-text", text: `${r.correct ? "✓" : "✗"} ${r.explanation}` }));
          } catch (e) {
            fb.append(el("p", { className: "error", text: e.message }));
          }
          if (++answered === l.check.length) done.classList.remove("hidden");
        })));
        return el("div", { className: "lesson-section" }, el("h3", { text: `${idx + 1}. ${q.question}` }), opts, fb);
      });
      return render("check", lessonCard(el("h1", { text: `✅ ${t("station.check")}` }), el("p", { className: "muted", text: t("lesson.no_grades") }), ...qs, done));
    }
  }

  async function startActivity() {
    try {
      if (lesson && !lesson.completed) lesson = await api("POST", `/api/lessons/${encodeURIComponent(lesson.lesson_id)}/complete`);
    } catch {
      /* not blocking */
    }
    showActivityIntro();
  }

  /* ---------- Mission card ---------- */

  function rules() {
    return el("ul", { className: "plain-list" }, ...[t(`rules.${activityType}`), t("rules.hint"), t("rules.levels"), t("rules.no_punish"), t("rules.tracking")].map((r) => el("li", { className: "small", text: r })));
  }

  function showActivityIntro() {
    mentorText = t("act.coach_intro");
    render("play", el("div", { className: "mission-banner" }, el("span", { className: "chip-tag solid" }, activityIcon(activityType, 16), el("span", { text: actName() })),
      el("h2", { text: step.name }), el("p", { text: t(`activity.${activityType}.summary`) })),
    el("div", { className: "card" }, el("h3", { text: t("act.how_play") }), rules(),
      el("div", { className: "actions between" }, lesson ? button(t("act.review_lesson"), "btn-secondary", reviewLesson, "book") : el("span", {}),
        button(t("act.start_mission"), "btn-big", createActivity, "play"))));
  }

  async function createActivity() {
    loading(t("act.preparing"), t("act.preparing_hint"));
    try {
      act = await api("POST", `/api/assessments/${encodeURIComponent(assessmentId)}/activities`, { competency_id: competencyId, activity_type: activityType });
    } catch (e) {
      return fail(e.message, createActivity);
    }
    activityId = act.activity_id;
    history.replaceState(null, "", `activity.html?id=${encodeURIComponent(activityId)}`);
    showMissionFirst = act.current_level === 1 && act.levels[0].xp === 0 && act.levels[0].hints_used === 0;
    levelState = {};
    drive();
  }

  function showMission() {
    mentorText = act.levels[0].mentor_message;
    render("play", el("div", { className: "mission-banner" }, el("span", { className: "chip-tag solid", text: t("act.mission_card") }),
      el("h2", { text: act.mission.title }), el("p", { text: act.mission.story })),
    el("div", { className: "card" },
      el("p", {}, el("strong", { text: `${t("act.goal")}: ` }), document.createTextNode(act.mission.goal)),
      el("p", {}, el("strong", { text: `${t("act.win")}: ` }), document.createTextNode(act.mission.win_condition)),
      rules(),
      el("div", { className: "actions end" }, button(t("act.start_level_1"), "btn-big", () => {
        showMissionFirst = false;
        drive();
      }, "play"))));
  }

  /* ---------- Levels ---------- */

  function drive() {
    if (act.status === "completed") return showResult();
    if (act.status === "generating") {
      loading(t("act.next_level"));
      return setTimeout(reload, 3000);
    }
    if (showMissionFirst) return showMission();
    showLevel();
  }

  async function reload() {
    try {
      act = await api("GET", `/api/activities/${encodeURIComponent(activityId)}`);
      drive();
    } catch (e) {
      fail(e.message, reload);
    }
  }

  const level = () => act.levels[act.levels.length - 1];
  const renderer = () => ActivityKit.renderers[activityType];

  function showLevel(message) {
    const lv = level();
    mentorText = message || lv.mentor_message;
    levelState[lv.number] = levelState[lv.number] || {};
    const body = el("div", {});
    const hint = button(t("act.hint", { n: act.rules.hint }), "btn-secondary", useHint, "bulb");
    hint.disabled = !lv.can_hint || lv.is_boss;
    const finish = button((renderer().finishLabel && renderer().finishLabel(lv)) || t("act.finish_level"), "", finishLevel, "arrow");
    const ctx = {
      act, state: levelState[lv.number], level,
      rerender: (msg) => showLevel(msg || mentorText),
      mentor: (msg) => {
        mentorText = msg;
        const box = document.getElementById("nudge-line");
        if (box) box.textContent = msg;
      },
      send,
    };
    render(lv.is_boss ? "boss" : "play",
      el("div", { className: "mission-banner" },
        el("span", { className: "chip-tag solid", text: lv.is_boss ? `👑 ${t("station.boss")}` : t("act.level_of", { n: lv.number, total: act.total_levels - 1 }) }),
        el("h2", { text: act.mission ? act.mission.title : actName() }),
        el("p", { className: "small", text: act.mission ? act.mission.goal : "" })),
      el("div", { className: "status-row" }, chip(`⭐ ${act.xp} XP`, "amber"), chip(renderer().stat(lv, act), "cyan"),
        lv.is_boss ? chip(t("act.no_hints"), "muted") : chip(`💡 ${t("act.hints_used_n", { n: lv.hints_used })}`, "muted")),
      lv.hints.length ? el("ul", { className: "hint-list" }, ...lv.hints.map((h) => el("li", { text: `💡 ${h}` }))) : null,
      body,
      el("div", { className: "card soft nudge-say" }, nudge(52), el("div", { className: "bubble-box" }, el("strong", { text: t("act.nudge_says") }), el("p", { id: "nudge-line", text: mentorText }))),
      el("div", { className: "actions between" }, el("span", { className: "actions" }, lv.is_boss ? null : hint, lesson ? button(t("act.review_lesson"), "btn-secondary", reviewLesson, "book") : null), finish));
    renderer().render(body, lv, ctx);
  }

  function setBusy(text) {
    page.querySelectorAll("button, textarea, input").forEach((n) => (n.disabled = true));
    const box = document.getElementById("nudge-line");
    if (box && text) box.textContent = `⏳ ${text}`;
  }

  async function send(endpoint, body, onOutcome, loadingText) {
    setBusy(loadingText);
    try {
      const res = await api("POST", `/api/activities/${encodeURIComponent(activityId)}/${endpoint}`, body);
      act = res.activity;
      showLevel(onOutcome ? onOutcome(res.outcome) : undefined);
    } catch (e) {
      showLevel(e.message);
    }
  }

  async function useHint() {
    try {
      const res = await api("POST", `/api/activities/${encodeURIComponent(activityId)}/hint`);
      act = res.activity;
      showLevel(t("act.hint_text", { n: act.rules.hint, hint: res.outcome.hint }));
    } catch (e) {
      showLevel(e.message);
    }
  }

  async function finishLevel() {
    const lv = level();
    const confirmText = renderer().finishConfirm && renderer().finishConfirm(lv);
    if (confirmText && !confirm(confirmText)) return;
    const number = lv.number;
    const before = new Set(act.badges.map((b) => b.id));
    loading(lv.is_boss ? t("act.computing") : t("act.next_level"), lv.is_boss ? "" : t("act.preparing_hint"));
    try {
      act = await api("POST", `/api/activities/${encodeURIComponent(activityId)}/finish-level`);
    } catch (e) {
      return fail(e.message, finishLevel);
    }
    if (act.status === "completed") report = await api("GET", `/api/assessments/${encodeURIComponent(assessmentId)}/report`).catch(() => report);
    showSummary(act.levels[number - 1], act.badges.filter((b) => !before.has(b.id)));
  }

  /* ---------- 📖 Review the lesson (free) ---------- */

  async function reviewLesson() {
    let l = lesson;
    if (activityId) {
      try {
        l = await api("POST", `/api/activities/${encodeURIComponent(activityId)}/review-lesson`);
      } catch {
        /* fall back to the copy we have */
      }
    }
    if (!l) return;
    const dialog = el("dialog", { className: "lesson-dialog" },
      el("h2", { text: `📖 ${l.explanation.title}` }),
      el("p", { className: "hint", text: t("act.review_free") }),
      explanationBlocks(l, false), keyIdeas(l),
      el("h3", { text: `🤝 ${t("station.together")}` }), el("p", { text: l.example.problem }), artifact(l.example.lines),
      el("ol", { className: "expert-steps" }, ...l.example.steps.map((s) => el("li", {}, el("strong", { text: App.plain(s.step) }), el("div", { className: "hint", text: s.explanation })))),
      el("form", { attrs: { method: "dialog" }, className: "actions end" }, el("button", { className: "btn", type: "submit", text: t("act.back_to_mission") })));
    dialog.addEventListener("close", () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }

  /* ---------- Summary & result ---------- */

  function stat(icon, label, value) {
    return el("div", { className: "stat" }, el("span", { className: "ico" }, svg(icon, 20)), el("div", {}, el("small", { text: label }), el("strong", { text: String(value) })));
  }

  function badgeChip(b) {
    return el("div", { className: "badge-line earned" }, el("span", { className: "ico", text: BADGE_ICONS[b.id] || b.icon }),
      el("div", {}, el("strong", { text: t(`badge.${b.id}.name`) }), el("span", { className: "hint", text: t(`badge.${b.id}.desc`) })));
  }

  function showSummary(lv, newBadges) {
    const r = renderer();
    mentorText = t("act.coach_summary");
    render(lv.is_boss ? "boss" : "play", el("div", { className: "card" },
      el("h1", { text: lv.is_boss ? t("act.boss_done") : t("act.level_done", { n: lv.number }) }),
      el("div", { className: "stat-row" }, stat("star", t("act.level_xp"), `${Math.max(0, lv.xp)} / ${lv.max_xp}`), stat("bulb", t("act.hints_used"), lv.hints_used)),
      ...newBadges.map(badgeChip),
      ...((r.summary && r.summary(lv, act)) || []).filter(Boolean),
      el("div", { className: "actions end" }, button(act.status === "completed" ? t("act.see_result") : level().is_boss ? t("act.to_boss") : t("act.next_level_btn"), "btn-big", drive, "arrow"))));
  }

  function rankName(rank) {
    if (activityType === "work_challenge") {
      const job = (act.mission && act.mission.job_title) || t("rank.work_challenge.default_job");
      return rank === "beginner" ? t("rank.work_challenge.beginner") : rank === "mid" ? job : t("rank.work_challenge.expert", { job });
    }
    return t(`rank.${activityType}.${rank}`);
  }

  function upNext() {
    const steps = (report && report.learning_journey) || [];
    const prog = (report && report.learning_progress) || {};
    // Same rule as the journey map: the next station is the first one not played yet.
    const nextStep = steps.find((s) => !prog[s.competency_id] && s.competency_id !== competencyId);
    if (!nextStep) return null;
    const i = steps.indexOf(nextStep);
    return el("div", { className: "card" },
      el("div", { className: "head-row" }, el("span", { className: "eyebrow", text: t("act.up_next") }), chip(t("act.unlocked_one"), "cyan", "lock")),
      el("span", { className: "hint", text: t("report.station", { n: i + 1 }) }), el("h2", { text: nextStep.name }),
      el("a", { className: "btn", href: `activity.html?${new URLSearchParams({ assessment: assessmentId, competency: nextStep.competency_id, type: nextStep.activity.activity_type })}` },
        el("span", { text: t("act.go_station", { n: i + 1 }) }), svg("arrow", 18, "flip")));
  }

  function passport() {
    const steps = (report && report.learning_journey) || [];
    const prog = (report && report.learning_progress) || {};
    return el("div", { className: "card" }, el("h2", {}, svg("briefcase", 20), el("span", { text: ` ${t("act.passport")}` })),
      el("div", { className: "passport-list" }, ...steps.map((s) => {
        const p = prog[s.competency_id];
        return el("div", {}, el("span", { text: s.name }), p ? chip(t(`progress.${p.status}`), p.status === "passed" ? "green" : "amber") : chip(t("progress.todo"), "muted"));
      })));
  }

  function showResult() {
    const r = act.result;
    mentorText = t(`decision.${r.decision}.message`);
    const jump = Math.round(r.score_after - r.score_before);
    const meter = bar(r.score_before, r.target_score, "big");
    const fill = meter.querySelector(".bar-fill");
    requestAnimationFrame(() => requestAnimationFrame(() => (fill.style.width = `${r.score_after}%`)));
    const back = el("a", { className: "btn btn-big", href: `journey.html?id=${encodeURIComponent(act.assessment_id)}` }, el("span", { text: t("act.back_journey") }), svg("compass", 18));
    const actions = [back];
    if (r.decision === "partial") actions.unshift(button(t("act.another_round"), "btn-secondary btn-big", createActivity, "refresh"));
    if (r.decision === "persistent" && r.alternative) {
      actions.unshift(el("a", { className: "btn btn-secondary btn-big", href: activityUrl(r.alternative.activity_type) },
        el("span", { text: t("act.try_method", { name: t(`activity.${r.alternative.activity_type}.name`) }) })));
    }
    render("boss",
      el("div", { className: "card" },
        el("div", { className: "nudge-say" }, nudge(52), el("div", { className: "bubble-box" }, el("strong", { text: t("act.nudge_says") }), el("p", { text: t(`decision.${r.decision}.message`) }))),
        el("div", { className: "head-row" },
          el("div", {}, el("h1", { className: "big-title", text: `${t(`decision.${r.decision}.title`)}${r.decision === "passed" ? " 🎉" : ""}` }), el("p", { className: "muted", text: t("act.result_sub", { activity: actName(), gap: step.name }) })),
          el("span", { className: "actions" }, ...act.badges.slice(-2).map((b) => chip(`${BADGE_ICONS[b.id]} ${t(`badge.${b.id}.name`)}`, "")), chip(`⭐ +${r.xp} XP`, "amber"))),
        el("div", { className: "card soft" },
          el("div", { className: "bar-row" }, el("strong", { text: t("act.gap_mastery") }),
            el("span", { text: t("act.before_after", { before: Math.round(r.score_before), after: Math.round(r.score_after) }) })),
          meter,
          el("div", { className: "head-row" }, el("span", { className: "hint", text: t("act.target", { n: r.target_score }) }), jump > 0 ? chip(`🎉 +${jump}% ${t("act.jump")}`, "cyan") : null)),
        el("div", { className: "stat-row" }, stat("check", t("act.final_score"), `${r.boss_percent}%`), stat("bulb", t("act.hints_used"), act.hints_used), stat("trophy", t("act.rank"), rankName(r.rank))),
        (r.behavior || []).length ? el("div", {}, el("h3", { text: t("act.what_noticed") }), el("ul", { className: "signal-list" }, ...r.behavior.map((s) =>
          el("li", {}, el("strong", { text: `${s.icon} ${t(`signal.${s.id}.title`)}: ` }), document.createTextNode(`${t(`signal.${s.id}.value`, s.params || {})} — ${t(`signal.${s.id}.decision`)}`))))) : null,
        el("div", { className: "actions" }, ...actions)),
      upNext() || "", passport());
  }

  init();
})();
