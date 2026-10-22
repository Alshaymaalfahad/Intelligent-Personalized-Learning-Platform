/* Report: skills overview, priorities, learning journey (stations → activities), reassessment,
   and the question review. Codes from the server are translated here; AI text uses textContent. */
(() => {
  const { el, button, svg, nudge, activityIcon, api, store, shell, bar, chip, loadingView, t } = App;
  const assessmentId = new URLSearchParams(location.search).get("id");
  shell(location.hash === "#journey" ? "journey" : "report");
  document.title = t("report.title");
  const page = document.getElementById("page");
  if (assessmentId) store.set("assessment_id", assessmentId);

  let report = null;
  let review = null;
  let progress = null;

  const STATUS_CHIP = {
    strength: ["green", "status.strength"],
    adequate: ["cyan", "status.adequate"],
    potential_gap: ["amber", "status.potential_gap"],
    likely_gap: ["red", "status.likely_gap"],
    insufficient_evidence: ["muted", "status.insufficient_evidence"],
  };
  const statusChip = (status) => chip(t(STATUS_CHIP[status][1]), STATUS_CHIP[status][0]);
  const kindIcon = (r) => (r.dimension === "knowledge" ? "book" : r.skill_kind === "soft" ? "chat" : "terminal");
  const kindLabel = (r) => t(r.dimension === "knowledge" ? "kind.knowledge" : r.skill_kind === "soft" ? "kind.soft" : "kind.hard");
  const activityUrl = (comp, type) => `activity.html?${new URLSearchParams({ assessment: assessmentId, competency: comp, type })}`;

  function reasonText(need) {
    if (!need.reasons) return need.reason || "";
    return need.reasons.map((r) => t(`reason.${r.code}`, { n: r.value })).join(" · ");
  }

  function signalText(s) {
    const p = s.params || {};
    return { title: t(`signal.${s.id}.title`), value: s.params ? t(`signal.${s.id}.value`, p) : s.value, decision: t(`signal.${s.id}.decision`) };
  }

  /* ---------- Hero + level ---------- */

  function hero() {
    const results = report.skill_results.concat(report.knowledge_results);
    const strong = results.filter((r) => ["strength", "adequate"].includes(r.status)).length;
    const lvl = progress || { level: 1, level_xp: 0, xp_per_level: 500 };
    const pct = Math.round((100 * lvl.level_xp) / lvl.xp_per_level);
    const ring = el("div", { className: "ring" }, el("div", {}, el("small", { text: t("report.current_tier") }), el("strong", { text: t("report.level", { n: lvl.level }) })));
    ring.style.setProperty("--p", pct);
    return el("section", { className: "report-hero" },
      el("div", {},
        el("span", { className: "chip-tag solid", text: t(report.kind === "reassessment" ? "report.reassessment_complete" : "report.assessment_complete") }),
        el("h1", { className: "big-title", text: t("report.headline") }),
        el("p", { text: t("report.subhead", { field: report.specialization }) }),
        el("div", { className: "nudge-say" }, nudge(52), el("div", { className: "bubble-box" }, el("strong", { text: t("coach.name") }),
          el("p", { text: t("report.nudge_summary", { strong, total: results.length }) })))),
      el("div", { className: "level-card" }, ring,
        el("div", { className: "bar-row" }, el("span", { text: t("report.to_level", { pct, n: lvl.level + 1 }) }), el("strong", { text: `${lvl.level_xp} / ${lvl.xp_per_level} XP` })),
        bar(pct),
        el("p", { className: "hint", text: t("report.xp_needed", { xp: lvl.xp_per_level - lvl.level_xp }) })));
  }

  /* ---------- Competency cards ---------- */

  function competencyCards() {
    const prog = report.learning_progress || {};
    const results = report.skill_results.concat(report.knowledge_results);
    return el("section", {},
      el("div", { className: "head-row" }, el("h2", { text: t("report.competencies") }), el("span", { className: "hint", text: t("report.target_note", { n: report.target_score }) })),
      el("div", { className: "grid grid-3" }, ...results.map((r) => {
        const p = prog[r.competency_id];
        return el("div", { className: "card comp-card" },
          el("div", { className: "top" }, el("span", { className: "icon-badge" }, svg(kindIcon(r), 20)), statusChip(r.status)),
          el("div", { className: "type", text: kindLabel(r) }),
          el("h3", { text: r.name }),
          el("div", { className: "bar-row" }, el("span", { text: t("report.score") }), el("strong", { text: `${Math.round(r.score)}%` })),
          bar(r.score, r.target_score),
          el("p", { className: "hint", text: t("report.evidence", { n: r.question_count }) + (r.low_confidence_count ? ` · ${t("report.low_confidence", { n: r.low_confidence_count })}` : "") }),
          p && p.current > r.score ? el("div", { className: "before-after" },
            el("span", { text: t("report.before_after", { before: Math.round(r.score), after: Math.round(p.current) }) }),
            chip(t(`progress.${p.status}`), p.status === "passed" ? "green" : "amber")) : null);
      })));
  }

  /* ---------- Reassessment comparison ---------- */

  const DECISION_CHIP = { closed: "green", partial: "cyan", persistent: "red", insufficient: "muted" };

  function comparison() {
    if (report.kind !== "reassessment") return null;
    return el("section", { className: "card" },
      el("h2", { text: t("report.compare_title") }),
      el("p", { className: "muted small", text: t("report.compare_note") }),
      ...report.comparison.map((c) => el("div", { className: "compare-row" },
        el("div", { className: "head-row" }, el("strong", { text: c.name }), chip(t(`decision.${c.decision}.title`), DECISION_CHIP[c.decision])),
        el("div", { className: "compare-nums" },
          el("span", { text: t("report.before", { n: Math.round(c.before) }) }),
          el("span", { className: "muted", text: t("report.after_training", { n: Math.round(c.after_training) }) }),
          el("strong", { text: t("report.after_reassessment", { n: Math.round(c.after) }) })),
        bar(c.after, c.target_score),
        el("p", { className: "small muted", text: t(`decision.${c.decision}.message`) + (c.needs_human ? ` ${t("decision.human")}` : "") }),
        c.behavior.length ? el("ul", { className: "signal-list" }, ...c.behavior.map((s) => {
          const x = signalText(s);
          return el("li", {}, el("strong", { text: `${s.icon} ${x.title}: ` }), document.createTextNode(`${x.value} — ${x.decision}`));
        })) : null)),
      ...(report.new_gaps || []).map((g) => el("div", { className: "compare-row" },
        el("div", { className: "head-row" }, el("strong", { text: g.name }), chip(t("report.new_gap"), "amber")),
        el("p", { className: "small muted", text: t(`origin.${g.origin}`) }))),
      el("a", { href: `report.html?id=${encodeURIComponent(report.parent_assessment_id)}`, text: t("report.first_report") }));
  }

  /* ---------- Priorities ---------- */

  function priorities() {
    const needs = report.prioritized_learning_needs.slice(0, 3);
    const prog = report.learning_progress || {};
    const steps = report.learning_journey || [];
    if (!needs.length) return el("section", { className: "card" }, el("h2", { text: t("report.priorities") }), el("p", { className: "muted", text: t("report.no_priorities") }));
    const activeIndex = steps.findIndex((s) => !prog[s.competency_id] || prog[s.competency_id].status !== "passed");
    return el("section", {},
      el("div", { className: "head-row" }, el("h2", {}, svg("flag", 20), el("span", { text: ` ${t("report.priorities")}` })), el("span", { className: "small", text: t("report.recommended_sequence") })),
      el("div", { className: "grid grid-3" }, ...needs.map((n, i) => {
        const stepIndex = steps.findIndex((s) => s.competency_id === n.competency_id);
        const step = steps[stepIndex];
        const isActive = stepIndex === activeIndex;
        const done = prog[n.competency_id] && prog[n.competency_id].status === "passed";
        const action = !step ? null : done ? chip(t("progress.passed"), "green", "check")
          : isActive ? el("a", { className: "btn", href: activityUrl(step.competency_id, step.activity.activity_type) }, el("span", { text: t("report.focus_now") }), svg("arrow", 18))
          : el("span", { className: "btn btn-secondary disabled-like" }, el("span", { text: t("report.queue_next") }), svg("lock", 16));
        return el("div", { className: "card priority-card" },
          el("div", { className: "top" }, el("span", { className: "num", text: String(i + 1) }), statusChip(n.status)),
          el("h3", { text: n.name }), el("p", { className: "why", text: reasonText(n) }), action);
      })));
  }

  /* ---------- Journey ---------- */

  function journey() {
    const steps = report.learning_journey || [];
    const prog = report.learning_progress || {};
    if (!steps.length) return el("section", { className: "card", id: "journey" }, el("h2", { text: t("report.journey") }), el("p", { className: "muted", text: t("report.no_journey") }));
    let activeIndex = steps.findIndex((s) => !prog[s.competency_id] || prog[s.competency_id].status !== "passed");
    const info = report.reassessment || {};
    const unlocked = activeIndex === -1 ? steps.length : activeIndex + 1;

    const stations = steps.map((s, i) => {
      const done = prog[s.competency_id] && prog[s.competency_id].status === "passed";
      const state = done ? "done" : i === activeIndex ? "active" : "locked";
      return el("div", { className: `station ${state}` },
        el("div", { className: "bubble-ico" }, svg(state === "done" ? "check" : state === "locked" ? "lock" : kindIcon(s), 28)),
        el("span", { className: "label", text: `${t("report.station", { n: i + 1 })}${state === "active" ? ` · ${t("report.active")}` : ""}` }),
        el("strong", { text: s.name }),
        state === "active" ? el("a", { className: "btn btn-small", href: activityUrl(s.competency_id, s.activity.activity_type) }, el("span", { text: t("report.start") }), svg("play", 14)) : null);
    });
    const capstone = el("div", { className: `station ${info.eligible ? "active" : info.reassessment_status === "completed" ? "done" : "locked"}` },
      el("div", { className: "bubble-ico" }, svg("trophy", 28)),
      el("span", { className: "label", text: t("report.capstone") }),
      el("strong", { text: t("report.reassessment") }),
      reassessButton());

    const active = steps[activeIndex];
    return el("section", { id: "journey" },
      el("div", { className: "card" },
        el("div", { className: "head-row" },
          el("div", {}, el("h2", { text: t("report.journey") }), el("p", { className: "muted small", text: t("report.journey_sub") })),
          chip(t("report.stations_unlocked", { n: Math.min(unlocked, steps.length), total: steps.length }), "", "compass")),
        el("div", { className: "journey-path" }, ...stations, capstone)),
      active ? modalities(active, activeIndex) : null);
  }

  function reassessButton() {
    const info = report.reassessment || {};
    if (!info.total_steps) return null;
    if (info.reassessment_id) {
      const done = info.reassessment_status === "completed";
      return el("a", { className: "btn btn-small", href: done ? `report.html?id=${info.reassessment_id}` : `assessment.html?id=${info.reassessment_id}`, text: t(done ? "report.view_reassessment" : "report.continue_reassessment") });
    }
    if (!info.eligible) return chip(t("report.reassess_locked", { done: info.done_steps, total: info.total_steps }), "muted", "lock");
    const b = button(t("report.start_reassessment"), "btn-small", async () => {
      b.disabled = true;
      try {
        const a = await api("POST", `/api/assessments/${encodeURIComponent(assessmentId)}/reassessment`);
        store.set("assessment_id", a.assessment_id);
        location.href = `assessment.html?id=${encodeURIComponent(a.assessment_id)}`;
      } catch (e) {
        b.disabled = false;
        alert(e.message);
      }
    });
    return b;
  }

  function modalities(step, index) {
    const cards = [step.activity, ...step.alternatives].map((a, i) =>
      el("div", { className: `card activity-card tone-${a.activity_type} ${i === 0 ? "recommended" : ""}` },
        el("div", { className: "top-row head-row" }, el("span", { className: "icon-badge" }, activityIcon(a.activity_type)), i === 0 ? chip(t("report.recommended"), "solid", "star") : null),
        el("h3", { text: t(`activity.${a.activity_type}.name`) }),
        el("p", { className: "muted small", text: t(`activity.${a.activity_type}.summary`) }),
        el("div", { className: "meta" }, el("span", { className: "hint", text: t(`activity.${a.activity_type}.best_for`) }),
          el("a", { className: `btn btn-small ${i === 0 ? "" : "btn-secondary"}`, href: activityUrl(step.competency_id, a.activity_type) }, el("span", { text: t("report.play") }), svg("play", 14)))));
    return el("section", { className: "modalities" },
      el("div", { className: "head-row" },
        el("div", {}, el("span", { className: "chip-tag", text: t("report.station_modalities") }), el("h2", { text: t("report.inside_station", { n: index + 1, name: step.name }) }),
          el("p", { className: "muted small", text: t("report.choose_format") })),
        chip(t("report.formats"), "", "sparkle")),
      el("div", { className: "grid grid-3" }, ...cards));
  }

  /* ---------- Insights ---------- */

  function insights() {
    const list = report.insights || [];
    if (!list.length) return null;
    return el("section", { className: "card" }, el("h2", { text: t("report.insights") }),
      el("ul", { className: "plain-list" }, ...list.map((i) => el("li", { text: i.text || t(`insight.${i.type}`, { skill: i.skill_name || "", knowledge: i.knowledge_name || "" }) }))));
  }

  /* ---------- Question review ---------- */

  const BLOOM = (b) => t(`bloom.${b}`);

  function reasonFor(q) {
    if (!q.adaptation_code) return q.adaptation_reason;
    const { code, params = {} } = q.adaptation_code;
    let text = t(`adapt.${code}`, { difficulty: params.difficulty, from: params.from ? BLOOM(params.from) : "", to: params.to ? BLOOM(params.to) : "" });
    if (params.extra) text = `${t("adapt.extra")} ${text}`;
    if (params.reassessment) text = `${t("adapt.reassessment")} ${text}`;
    return text;
  }

  function questionCard(q) {
    const correct = q.earned_score > 0 && q.earned_score >= q.max_score / 2;
    const body = el("div", { className: "review-body" },
      reasonFor(q) ? el("p", { className: "adaptive-note", text: `${t("report.why_question")}: ${reasonFor(q)}` }) : null,
      el("p", { className: "hint", text: `${BLOOM(q.bloom_level)} · ${t("report.difficulty", { n: q.difficulty })} · ${t("report.objective")}: ${q.learning_objective}` }),
      el("p", { className: "q-text", text: q.question_text }),
      q.code_snippet ? el("pre", { className: "code", dir: "ltr" }, el("code", { text: q.code_snippet })) : null);
    if (q.answer_format === "choice") {
      body.append(el("ul", { className: "review-options" }, ...q.options.map((o, i) => {
        const li = el("li", { text: `${i === q.correct_option_index ? "✓ " : ""}${o}${i === q.trainee_answer ? `  ← ${t("report.your_answer")}` : ""}` });
        if (i === q.correct_option_index) li.classList.add("correct");
        else if (i === q.trainee_answer) li.classList.add("wrong");
        return li;
      })));
    } else if (q.answer_format === "order") {
      body.append(el("div", { className: "side-by-side" },
        el("div", {}, el("strong", { text: t("report.correct_order") }), el("ol", {}, ...q.correct_order.map((i) => el("li", { text: App.plain(q.options[i]) })))),
        el("div", {}, el("strong", { text: t("report.your_order") }), el("ol", {}, ...(q.trainee_answer || []).map((i) => el("li", { text: App.plain(q.options[i]) }))))));
    } else {
      body.append(el("h3", { text: t("report.your_answer") }), el("p", { className: "card soft", text: q.trainee_answer || "—" }));
      if (q.grading_details) body.append(el("ul", { className: "plain-list" }, ...q.grading_details.map((d) =>
        el("li", {}, el("strong", { text: `${d.awarded}/${d.points} — ${d.criterion}` }), el("div", { className: "hint", text: d.justification })))));
      if (q.feedback) body.append(el("p", { text: q.feedback }));
    }
    body.append(el("h3", { text: t("report.reference") }), el("p", { text: q.reference_answer }), el("h3", { text: t("report.rationale") }), el("p", { text: q.rationale }), rating(q));
    return el("details", { className: "review-item" },
      el("summary", {}, el("span", { className: "chip-tag muted", text: q.question_id }), el("span", { text: q.competency_name }),
        chip(t(`qtype.${q.question_type}`), "cyan"), chip(correct ? t("report.correct") : t("report.incorrect"), correct ? "green" : "red", correct ? "check" : "x"),
        q.review_rating ? chip(t("report.rated"), "amber", "star") : null),
      body);
  }

  function rating(q) {
    const note = el("textarea", { attrs: { rows: "2", maxlength: "1000", placeholder: t("report.rating_note") } });
    note.value = q.review_note || "";
    const status = el("span", { className: "hint" });
    const options = [["good", "report.rate_good"], ["needs_work", "report.rate_needs_work"], ["bad", "report.rate_bad"]];
    const buttons = options.map(([value, key]) => {
      const b = button(t(key), `btn-small ${q.review_rating === value ? "" : "btn-secondary"}`, async () => {
        status.textContent = t("report.saving");
        try {
          const saved = await api("PUT", `/api/assessments/${encodeURIComponent(assessmentId)}/questions/${encodeURIComponent(q.question_id)}/review`, { rating: value, note: note.value.trim() || null });
          q.review_rating = saved.review_rating;
          buttons.forEach((x, i) => x.classList.toggle("btn-secondary", options[i][0] !== value));
          status.textContent = t("report.saved");
        } catch (e) {
          status.textContent = e.message;
        }
      });
      return b;
    });
    return el("div", {}, el("div", { className: "rating" }, el("span", { className: "small", text: t("report.was_clear") }), el("span", { className: "actions" }, ...buttons), status), note);
  }

  function reviewSection() {
    const download = button(t("report.download"), "btn-secondary btn-small", () => {
      const blob = new Blob([JSON.stringify({ report, review }, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = el("a", { href: url });
      a.download = `${assessmentId}.json`;
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }, "download");
    const total = review.questions.length;
    const correct = review.questions.filter((q) => q.earned_score > 0 && q.earned_score >= q.max_score / 2).length;
    return el("section", { className: "card" },
      el("div", { className: "head-row" },
        el("div", {}, el("h2", { text: t("report.review_title") }), el("p", { className: "muted small", text: t("report.review_sub", { n: total, correct }) })),
        download),
      ...["skill", "knowledge"].map((phase) => el("div", {},
        el("h3", { text: t(phase === "skill" ? "assess.section_skill" : "assess.section_knowledge") }),
        ...review.questions.filter((q) => q.phase === phase).map(questionCard))));
  }

  /* ---------- Load ---------- */

  async function load() {
    if (!assessmentId) return page.replaceChildren(el("div", { className: "card" }, el("p", { text: t("assess.no_id") })));
    page.replaceChildren(loadingView(t("report.loading")));
    try {
      [report, review] = await Promise.all([api("GET", `/api/assessments/${encodeURIComponent(assessmentId)}/report`), api("GET", `/api/assessments/${encodeURIComponent(assessmentId)}/review`)]);
    } catch (e) {
      if (e.status === 409) {
        return page.replaceChildren(el("div", { className: "card center" }, nudge(80), el("h2", { text: t("report.not_ready") }),
          el("a", { className: "btn", href: `assessment.html?id=${encodeURIComponent(assessmentId)}`, text: t("report.continue_assessment") })));
      }
      return page.replaceChildren(el("div", { className: "card" }, el("p", { className: "error", text: e.message })));
    }
    store.set("trainee_id", report.trainee_id);
    progress = await App.refreshProgress();
    page.replaceChildren(hero(), comparison() || "", competencyCards(), priorities(), journey(), insights() || "", reviewSection());
    if (location.hash === "#journey") document.getElementById("journey")?.scrollIntoView();
  }

  load();
})();
