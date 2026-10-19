/* Activity page core: the briefing (lesson) → mission card → levels → summary → result.
   The level body is drawn by the activity's renderer (activity-*.js). */

(() => {
  const { el, button, api, artifact } = ActivityKit;
  const params = new URLSearchParams(location.search);
  let activityId = params.get("id");
  let assessmentId = params.get("assessment");
  let competencyId = params.get("competency");
  let activityType = params.get("type");
  const $ = (id) => document.getElementById(id);
  const VIEWS = ["loading", "error", "lesson", "intro", "level", "summary", "result"];

  let act = null;
  let step = null; // journey step (activity cards) from the report
  let lessonInfo = null; // GET lessons/{competency}
  let lesson = null;
  let levelState = {}; // renderer UI state per level number
  let retryAction = null;
  let showMissionFirst = false;

  /* ---------- Helpers ---------- */

  function show(name) {
    for (const v of VIEWS) $(`view-${v}`).classList.toggle("hidden", v !== name);
    window.scrollTo({ top: 0 });
  }

  function stations(current, done = []) {
    for (const li of $("stations").children) {
      li.classList.toggle("active", li.dataset.station === current);
      li.classList.toggle("done", done.includes(li.dataset.station));
    }
  }

  function loading(text, hint = "") {
    $("loading-text").textContent = text;
    $("loading-hint").textContent = hint;
    show("loading");
  }

  function fail(message, action) {
    $("error-text").textContent = message;
    retryAction = action || null;
    $("retry-btn").classList.toggle("hidden", !action);
    show("error");
  }

  function setBackLink() {
    if (assessmentId) $("back-link").href = `report.html?id=${encodeURIComponent(assessmentId)}#journey`;
  }

  const LESSON_DONE = ["why", "explain", "together", "check"];
  const card = () => (act && act.activity) || [step.activity, ...step.alternatives].find((a) => a.activity_type === activityType);

  /* ---------- Entry ---------- */

  async function init() {
    try {
      if (activityId) {
        act = await api("GET", `/api/activities/${encodeURIComponent(activityId)}`);
        assessmentId = act.assessment_id;
        competencyId = act.competency_id;
        activityType = act.activity.activity_type;
      }
      if (!assessmentId || !competencyId || !activityType) return fail("الرابط غير مكتمل.");
      setBackLink();
      const report = await api("GET", `/api/assessments/${encodeURIComponent(assessmentId)}/report`);
      step = (report.learning_journey || []).find((s) => s.competency_id === competencyId);
      if (!step) return fail("هذه الكفاءة ليست ضمن رحلتك التعليمية.");
      lessonInfo = await api("GET", `/api/assessments/${encodeURIComponent(assessmentId)}/lessons/${encodeURIComponent(competencyId)}`);
      lesson = lessonInfo.lesson;
    } catch (e) {
      return fail(e.message, init);
    }
    if (act) return render();
    if (lesson && lesson.completed) return showActivityIntro();
    if (lesson) return showLesson("why");
    showLessonStart();
  }

  /* ---------- 📖 Briefing (lesson) ---------- */

  function lessonShell(station, ...children) {
    stations(station, LESSON_DONE.slice(0, LESSON_DONE.indexOf(station)));
    const c = card();
    $("view-lesson").replaceChildren(
      el("div", { className: "card" },
        el("p", { className: "muted small", text: `${c.icon} إحاطة قبل مهمة «${c.name}» · الفجوة: ${step.name}` }),
        ...children),
    );
    show("lesson");
  }

  function next(label, onClick) {
    return el("div", { className: "actions" }, button(label, "", onClick));
  }

  function showLessonStart() {
    stations("why");
    const info = lessonInfo;
    const styles = el("div", { className: "solutions" }, ...info.styles.map((s) =>
      button(s.label + (s.id === info.suggested_style ? " ⭐ الأنسب لك" : ""), s.id === info.suggested_style ? "" : "btn-secondary", () => createLesson(s.id))));
    const c = card();
    $("view-lesson").replaceChildren(el("div", { className: "card" },
      el("div", { className: "activity-hero" }, el("span", { className: "activity-icon", text: "🧭" }),
        el("div", {}, el("p", { className: "muted", text: `الفجوة: ${step.name}` }), el("h1", { text: "إحاطة قبل المغامرة" }))),
      el("p", { text: `قبل مهمة «${c.icon} ${c.name}» نجهّزك: نشرح لك، ثم نحل مثالًا سوا، ثم تبدأ أنت.` }),
      el("div", { className: "mission" }, el("strong", { text: `نوع فجوتك: ${info.depth_label}` }), el("p", { text: info.depth_description })),
      el("h3", { text: "كيف تحب نشرح لك؟" }),
      el("p", { className: "hint", text: info.suggested_style ? "⭐ اقترحنا الأسلوب الذي نجح معك أكثر في الفجوات السابقة." : "اختر الأسلوب الأقرب لك؛ سنتذكر أي أسلوب ينجح معك." }),
      styles,
      info.can_skip ? el("div", { className: "actions" }, button("تخطَّ الشرح وابدأ التحدي مباشرة", "btn-secondary", showActivityIntro)) : null));
    show("lesson");
  }

  async function createLesson(style) {
    loading("المرشد يجهّز إحاطتك…", "شرح مخصص لفجوتك، قد يستغرق حتى دقيقة.");
    try {
      lesson = await api("POST", `/api/assessments/${encodeURIComponent(assessmentId)}/lessons/${encodeURIComponent(competencyId)}`, { style });
    } catch (e) {
      return fail(e.message, () => createLesson(style));
    }
    showLesson("why");
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
        const reveal = button("👀 اكشف", "btn-small btn-secondary", () => { answer.classList.remove("hidden"); reveal.remove(); });
        return el("div", { className: "lesson-section" }, el("h3", { text: s.heading }), el("p", { className: "sub-title", text: `🤔 ${s.reveal_question}` }), reveal, answer);
      }));
    }
    return el("div", { className: l.style === "story" ? "story" : "" }, ...sections.map((s) =>
      el("div", { className: "lesson-section" }, el("h3", { text: l.style === "story" || !s.emoji ? s.heading : `${s.emoji} ${s.heading}` }), el("p", { text: s.body }))));
  }

  function takeaways(l) {
    return el("div", { className: "takeaways" }, el("strong", { text: "📌 تذكّر" }), el("ul", {}, ...l.explanation.takeaways.map((t) => el("li", { text: t }))));
  }

  function showLesson(station) {
    const l = lesson;
    if (station === "why") {
      return lessonShell("why",
        el("h1", { text: `🎬 ${l.why.title}` }),
        el("p", { className: "story-card", text: l.why.story }),
        el("p", { className: "warn-text", text: `الأثر: ${l.why.impact}` }),
        next("📖 اشرح لي", () => showLesson("explain")));
    }
    if (station === "explain") {
      return lessonShell("explain",
        el("h1", { text: `📖 ${l.explanation.title}` }),
        el("p", { className: "muted small", text: `${l.depth_label} · ${l.style_label}` }),
        explanationBlocks(l), takeaways(l),
        next("🤝 نحل مثالًا سوا", () => showLesson("together")));
    }
    if (station === "together") {
      const ex = l.example;
      const steps = el("ol", { className: "expert-steps" });
      let shown = 0;
      const final = el("div", { className: "hidden" });
      const more = button("الخطوة التالية", "btn-secondary", () => {
        const s = ex.steps[shown++];
        steps.append(el("li", {}, el("strong", { text: s.step }), el("div", { className: "muted small", text: s.explanation })));
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
          final.append(
            el("p", { className: r.correct ? "ok-text" : "warn-text", text: `${r.correct ? "✓ صح! " : `الخطوة الصحيحة: «${ex.final_options[r.correct_index]}». `}${r.explanation}` }),
            next("✅ تأكد سريع", () => showLesson("check")));
        } catch (e) {
          final.append(el("p", { className: "error", text: e.message }));
        }
      })));
      final.append(el("h3", { text: `👉 دورك: ${ex.final_question}` }), options);
      return lessonShell("together",
        el("h1", { text: "🤝 نسوي سوا" }),
        el("p", { className: "muted", text: "المرشد يحل معك خطوة بخطوة، وأنت تكمل الخطوة الأخيرة." }),
        el("p", { text: ex.problem }), artifact(ex.lines), steps, el("div", { className: "actions" }, more), final);
    }
    if (station === "check") {
      let answered = 0;
      const done = el("div", { className: "hidden" }, next(`🎮 ابدأ مهمة «${card().name}»`, startActivity));
      const qs = l.check.map((q, idx) => {
        const fb = el("div", {});
        const opts = el("div", { className: "solutions" }, ...q.options.map((o, i) => button(o, "btn-secondary step-card", async () => {
          opts.querySelectorAll("button").forEach((b) => (b.disabled = true));
          try {
            const r = await api("POST", `/api/lessons/${encodeURIComponent(l.lesson_id)}/check`, { index: idx, choice: i });
            opts.children[r.correct_index].classList.add("selected");
            fb.append(el("p", { className: r.correct ? "ok-text" : "warn-text", text: `${r.correct ? "✓ " : "✗ "}${r.explanation}` }));
          } catch (e) {
            fb.append(el("p", { className: "error", text: e.message }));
          }
          if (++answered === l.check.length) done.classList.remove("hidden");
        })));
        return el("div", { className: "lesson-section" }, el("h3", { text: `${idx + 1}. ${q.question}` }), opts, fb);
      });
      return lessonShell("check", el("h1", { text: "✅ تأكد سريع" }),
        el("p", { className: "muted", text: "بدون درجات — فقط لتطمئن أنك فهمت." }), ...qs, done);
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

  /* ---------- Mission card / activity intro ---------- */

  const RULES = {
    common: [
      "💡 التلميح متاح دائمًا ويكلّف 5 XP، أما «📖 راجع الشرح» فمجاني في أي لحظة.",
      "المراحل تتدرج حسب أدائك، وآخرها 👑 التحدي النهائي: موقف جديد بلا تلميحات.",
      "الخطأ لا يُنهي اللعبة، والمرشد يشرح لك لماذا. ونقاطك لا تنزل تحت الصفر.",
      "نسجّل محاولاتك (نوع الخطأ، التلميحات، الزمن التقريبي، التبرير) لنختار خطوتك التالية ولنوجّه إعادة القياس.",
    ],
    gap_hunter: "اكتشاف الخطأ 10 XP، والتصنيف +5، والتبرير +5، والإصلاح +10. الإنذار الكاذب −5.",
    escape_room: "كل باب: القرار الصحيح من أول محاولة 20 XP (−5 لكل محاولة إضافية)، والتبرير +10، ورقم من رمز الخروج.",
    work_challenge: "المدير يراجع تسليمك على معايير القبول بالنجوم. تقدر تعدّل وتعيد التسليم، وأفضل تسليم هو المحسوب.",
    shadow: "التوقع الصحيح لخطوة الخبير 10 XP وبطاقة ممارسة ذهبية. في الظل العكسي: XP حسب تطابقك مع الخبير.",
    teach_others: "مقياس فهم سعود يرتفع فقط مع الشرح الواضح الصحيح. في النهاية يدخل سعود اختبارًا — إذا نجح، تنجح أنت.",
  };

  function fillIntro(c, competencyName) {
    $("intro-icon").textContent = c.icon;
    $("intro-name").textContent = c.name;
    $("intro-competency").textContent = `الفجوة: ${competencyName}`;
    $("intro-rules").replaceChildren(...[RULES[c.activity_type], ...RULES.common].map((t) => el("li", { text: t })));
    $("intro-review").classList.toggle("hidden", !lesson);
  }

  function showActivityIntro() {
    stations("play", LESSON_DONE);
    const c = card();
    fillIntro(c, step.name);
    $("intro-summary").textContent = c.summary;
    $("mission-card").classList.add("hidden");
    const start = $("intro-start");
    start.textContent = "🎮 ابدأ المهمة";
    start.onclick = createActivity;
    show("intro");
  }

  async function createActivity() {
    loading("المرشد يجهّز مهمتك…", "يُولَّد المحتوى حسب فجوتك، وقد يستغرق ذلك حتى دقيقة.");
    try {
      act = await api("POST", `/api/assessments/${encodeURIComponent(assessmentId)}/activities`, { competency_id: competencyId, activity_type: activityType });
    } catch (e) {
      return fail(e.message, createActivity);
    }
    activityId = act.activity_id;
    history.replaceState(null, "", `activity.html?id=${encodeURIComponent(activityId)}`);
    showMissionFirst = act.current_level === 1 && act.levels[0].xp === 0 && act.levels[0].hints_used === 0;
    levelState = {};
    render();
  }

  function showMission() {
    stations("play", LESSON_DONE);
    fillIntro(act.activity, act.competency_name);
    $("mission-card").classList.remove("hidden");
    $("mission-title").textContent = `بطاقة المهمة: ${act.mission.title}`;
    $("mission-story").textContent = act.mission.story;
    $("mission-goal").textContent = act.mission.goal;
    $("mission-win").textContent = act.mission.win_condition;
    $("intro-summary").textContent = "";
    const start = $("intro-start");
    start.textContent = "ابدأ المرحلة الأولى";
    start.onclick = () => {
      showMissionFirst = false;
      render();
    };
    show("intro");
  }

  /* ---------- Levels ---------- */

  function render() {
    document.title = act.activity.name;
    if (act.status === "completed") return showResult();
    if (act.status === "generating") {
      loading("المرشد يجهّز المرحلة التالية…");
      return setTimeout(reload, 3000);
    }
    if (showMissionFirst) return showMission();
    showLevel();
  }

  async function reload() {
    try {
      act = await api("GET", `/api/activities/${encodeURIComponent(activityId)}`);
      render();
    } catch (e) {
      fail(e.message, reload);
    }
  }

  const level = () => act.levels[act.levels.length - 1];
  const renderer = () => ActivityKit.renderers[act.activity.activity_type];

  function showLevel(mentorText) {
    const lv = level();
    stations(lv.is_boss ? "boss" : "play", LESSON_DONE.concat(lv.is_boss ? ["play"] : []));
    $("lv-title").textContent = lv.is_boss ? "👑 التحدي النهائي" : `المرحلة ${lv.number} من ${act.total_levels - 1}`;
    $("lv-xp").textContent = act.xp;
    $("lv-stat").textContent = renderer().stat(lv, act);
    const hint = $("lv-hint");
    hint.classList.toggle("hidden", lv.is_boss);
    hint.textContent = `💡 تلميح (−${act.rules.hint} XP)`;
    hint.disabled = !lv.can_hint;
    $("lv-review").classList.toggle("hidden", !lesson);
    $("lv-mentor").textContent = mentorText || lv.mentor_message;
    $("lv-hints").classList.toggle("hidden", !lv.hints.length);
    $("lv-hints").replaceChildren(...lv.hints.map((h) => el("li", { text: `💡 ${h}` })));
    $("lv-finish").textContent = (renderer().finishLabel && renderer().finishLabel(lv)) || "إنهاء المرحلة";
    $("lv-finish").disabled = false;
    $("view-level").setAttribute("aria-busy", "false");
    levelState[lv.number] = levelState[lv.number] || {};
    const ctx = {
      act,
      state: levelState[lv.number],
      level,
      rerender: (msg) => showLevel(msg || $("lv-mentor").textContent),
      mentor: (msg) => ($("lv-mentor").textContent = msg),
      send,
    };
    renderer().render($("lv-body"), lv, ctx);
    show("level");
  }

  function setBusy(text) {
    $("view-level").setAttribute("aria-busy", "true");
    $("view-level").querySelectorAll("button, textarea, input").forEach((n) => (n.disabled = true));
    if (text) $("lv-mentor").textContent = `⏳ ${text}`;
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
      showLevel(`تلميح (−${act.rules.hint} XP): ${res.outcome.hint}`);
    } catch (e) {
      showLevel(e.message);
    }
  }

  async function finishLevel() {
    const lv = level();
    const confirmText = renderer().finishConfirm && renderer().finishConfirm(lv);
    if (confirmText && !confirm(confirmText)) return;
    const number = lv.number;
    const badgesBefore = new Set(act.badges.map((b) => b.id));
    loading(lv.is_boss ? "نحسب نتيجتك…" : "المرشد يجهّز المرحلة التالية…", lv.is_boss ? "" : "قد يستغرق ذلك حتى دقيقة.");
    try {
      act = await api("POST", `/api/activities/${encodeURIComponent(activityId)}/finish-level`);
    } catch (e) {
      return fail(e.message, finishLevel);
    }
    showSummary(act.levels[number - 1], act.badges.filter((b) => !badgesBefore.has(b.id)));
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
    const ex = l.example;
    $("lesson-dialog-body").replaceChildren(
      el("h2", { text: `📖 ${l.explanation.title}` }),
      el("p", { className: "muted small", text: "مراجعة الشرح مجانية ولا تخصم نقاطًا." }),
      explanationBlocks(l, false),
      takeaways(l),
      el("h3", { text: "🤝 المثال المحلول" }),
      el("p", { text: ex.problem }),
      artifact(ex.lines),
      el("ol", { className: "expert-steps" }, ...ex.steps.map((s) => el("li", {}, el("strong", { text: s.step }), el("div", { className: "muted small", text: s.explanation })))));
    $("lesson-dialog").showModal();
  }

  /* ---------- Summary & result ---------- */

  function stat(label, value) {
    return el("div", { className: "stat" }, el("span", { className: "stat-label", text: label }), el("span", { className: "stat-value", text: String(value) }));
  }

  function badgeChip(b) {
    return el("div", { className: "earned-badge" }, el("span", { className: "badge-icon", text: b.icon }), el("strong", { text: b.name }), el("span", { className: "muted small", text: b.description }));
  }

  function showSummary(lv, newBadges) {
    $("sum-title").textContent = lv.is_boss ? "انتهى التحدي النهائي" : `انتهت المرحلة ${lv.number}`;
    $("sum-stats").replaceChildren(stat("نقاط المرحلة", `${Math.max(0, lv.xp)} / ${lv.max_xp} XP`), stat("تلميحات", lv.hints_used));
    $("sum-badges").replaceChildren(...newBadges.map(badgeChip));
    const r = renderer();
    $("sum-extra").replaceChildren(...((r.summary && r.summary(lv, act)) || []).filter(Boolean));
    const nextBtn = $("sum-next");
    nextBtn.textContent = act.status === "completed" ? "عرض النتيجة" : level().is_boss ? "👑 إلى التحدي النهائي" : "المرحلة التالية";
    nextBtn.onclick = render;
    show("summary");
  }

  function showResult() {
    stations("report", LESSON_DONE.concat(["play", "boss"]));
    const r = act.result;
    $("res-title").textContent = r.decision_title;
    $("res-message").textContent = r.decision_message;
    $("res-before").textContent = `قبل: ${Math.round(r.score_before)}%`;
    $("res-after").textContent = `الآن: ${Math.round(r.score_after)}%`;
    $("res-target").style.insetInlineStart = `${r.target_score}%`;
    $("res-target-label").textContent = `المستوى المطلوب ${r.target_score}% · نتيجة التحدي النهائي ${r.boss_percent}%`;
    const bar = $("res-bar");
    bar.classList.toggle("below", r.score_after < r.target_score);
    bar.style.width = `${r.score_before}%`;
    requestAnimationFrame(() => requestAnimationFrame(() => (bar.style.width = `${r.score_after}%`)));
    $("res-stats").replaceChildren(stat("نقاط الخبرة", `${r.xp} / ${r.max_xp}`), stat("رتبتك", r.rank));
    $("res-badges").replaceChildren(...act.badges.map(badgeChip));
    const signals = r.behavior || [];
    $("res-behavior").classList.toggle("hidden", !signals.length);
    $("res-behavior-list").replaceChildren(...signals.map((s) => el("li", {}, el("strong", { text: `${s.icon} ${s.title}: ` }), document.createTextNode(`${s.interpretation} ${s.decision}`))));

    const actions = [];
    const back = el("a", { className: r.decision === "passed" ? "btn" : "btn btn-secondary", text: "📊 العودة إلى الرحلة التعليمية" });
    back.href = `report.html?id=${encodeURIComponent(act.assessment_id)}#journey`;
    if (r.decision === "partial") actions.push(button("🔄 جولة أخرى", "", createActivity));
    if (r.decision === "persistent" && r.alternative) {
      const alt = el("a", { className: "btn", text: `🔀 جرّب: ${r.alternative.icon} ${r.alternative.name}` });
      alt.href = `activity.html?${new URLSearchParams({ assessment: act.assessment_id, competency: act.competency_id, type: r.alternative.activity_type })}`;
      actions.push(alt);
    }
    actions.push(back);
    $("res-actions").replaceChildren(...actions);
    show("result");
  }

  /* ---------- Init ---------- */

  $("lv-hint").addEventListener("click", useHint);
  $("lv-finish").addEventListener("click", finishLevel);
  $("lv-review").addEventListener("click", reviewLesson);
  $("intro-review").addEventListener("click", reviewLesson);
  $("retry-btn").addEventListener("click", () => retryAction && retryAction());
  init();
})();
