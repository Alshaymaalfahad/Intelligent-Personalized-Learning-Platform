/* Renders the gap report and the question review. AI text is always set via textContent. */

const assessmentId = new URLSearchParams(location.search).get("id");
const $ = (id) => document.getElementById(id);

const TYPE_LABELS = {
  multiple_choice: "اختيار من متعدد",
  true_false: "صح أو خطأ",
  scenario: "سيناريو عملي",
  error_detection: "اكتشاف الخطأ",
  ordering: "ترتيب",
  open_ended: "إجابة مكتوبة",
};
const KIND_LABELS = { hard: "مهارة تقنية (Hard)", soft: "مهارة ناعمة (Soft)" };
const BLOOM_LABELS = {
  remembering: "التذكر",
  understanding: "الفهم",
  applying: "التطبيق",
  analyzing: "التحليل",
  evaluating: "التقييم",
  creating: "الابتكار",
};
const DIMENSION_LABELS = { skill: "مهارة", knowledge: "معرفة" };
const RATINGS = [
  ["good", "جيد"],
  ["needs_work", "يحتاج تحسين"],
  ["bad", "سيئ"],
];

let report = null;
let review = null;

/* ---------- DOM helpers ---------- */

function el(tag, opts = {}, ...children) {
  const node = document.createElement(tag);
  if (opts.className) node.className = opts.className;
  if (opts.text !== undefined) node.textContent = opts.text;
  if (opts.dir) node.dir = opts.dir;
  for (const c of children) if (c) node.append(c);
  return node;
}

function statusBadge(status, label) {
  return el("span", { className: `status status-${status}`, text: label });
}

function scoreBar(score, target) {
  const wrap = el("div", { className: "bar" });
  const fill = el("div", { className: "bar-fill" });
  fill.style.width = `${Math.max(0, Math.min(100, score))}%`;
  fill.classList.toggle("below", score < target);
  const mark = el("div", { className: "bar-target" });
  mark.style.insetInlineStart = `${target}%`;
  wrap.append(fill, mark);
  return el("div", { className: "score-cell" }, el("span", { text: `${Math.round(score)}%` }), wrap);
}

function showError(message, link) {
  $("view-loading").classList.add("hidden");
  $("error-text").textContent = message;
  if (link) {
    $("error-link").href = link.href;
    $("error-link").textContent = link.text;
  }
  $("view-error").classList.remove("hidden");
}

/* ---------- Report ---------- */

function renderSummary() {
  $("r-meta").textContent = `${report.specialization} · المتدرب ${report.trainee_id} · التقييم ${report.assessment_id}`;
  const s = report.skill_summary;
  const k = report.knowledge_summary;
  $("r-skill-score").textContent = `${Math.round(s.score)}%`;
  $("r-skill-gaps").textContent = `${s.gap_count} فجوة من ${s.competency_count} مهارات`;
  $("r-knowledge-score").textContent = `${Math.round(k.score)}%`;
  $("r-knowledge-gaps").textContent = `${k.gap_count} فجوة من ${k.competency_count} مجالات`;
  $("r-target").textContent =
    `المستوى المطلوب لكل كفاءة: ${report.target_score}%. نتيجتا المهارات والمعرفة منفصلتان عمدًا، ولا يُحكم على أي كفاءة بسؤال واحد.`;
}

function renderPriorities() {
  const list = $("r-priorities");
  const needs = report.prioritized_learning_needs;
  $("r-no-priorities").classList.toggle("hidden", needs.length > 0);
  list.replaceChildren(
    ...needs.map((n) =>
      el(
        "li",
        {},
        el(
          "div",
          { className: "priority-head" },
          el("strong", { text: n.name }),
          el("span", { className: "badge badge-soft", text: DIMENSION_LABELS[n.dimension] }),
          statusBadge(n.status, n.status_label),
        ),
        el("p", { className: "muted", text: `النتيجة ${Math.round(n.score)}% — ${n.reason}` }),
      ),
    ),
  );
}

const PROGRESS_LABELS = {
  passed: ["✅ جاهز للتحقق", "status-strength"],
  partial: ["🔄 تحسّن جزئي", "status-adequate"],
  persistent: ["🔀 الفجوة مستمرة", "status-potential_gap"],
};

function activityLink(step, card, primary) {
  const params = new URLSearchParams({ assessment: assessmentId, competency: step.competency_id, type: card.activity_type });
  const a = el(
    "a",
    { className: `solution ${primary ? "primary" : ""}` },
    el("strong", { text: `${card.icon} ${card.name}` }),
    el("span", { className: "muted small", text: primary ? card.summary : card.best_for }),
  );
  a.href = `activity.html?${params}`;
  return a;
}

function renderJourney() {
  const steps = report.learning_journey || [];
  const progress = report.learning_progress || {};
  $("r-no-journey").classList.toggle("hidden", steps.length > 0);
  let unlocked = true; // a step opens once every earlier step is closed
  $("r-journey").replaceChildren(
    ...steps.map((step) => {
      const p = progress[step.competency_id];
      const current = p ? p.current : step.baseline_score;
      const open = unlocked;
      if (!p || p.status !== "passed") unlocked = false;

      const head = el(
        "div",
        { className: "priority-head" },
        el("strong", { text: step.name }),
        el("span", { className: "badge badge-soft", text: step.skill_kind ? KIND_LABELS[step.skill_kind] : DIMENSION_LABELS[step.dimension] }),
        p ? el("span", { className: `status ${PROGRESS_LABELS[p.status][1]}`, text: PROGRESS_LABELS[p.status][0] }) : null,
      );
      const lessonDone = (report.lessons || {})[step.competency_id]?.completed;
      const played = p && p.activities && p.activities.length;
      const chips = el("div", { className: "step-chips" },
        el("span", { className: lessonDone ? "done" : "", text: "📖 الإحاطة" }),
        el("span", { className: played ? "done" : "", text: "🎮 النشاط" }),
        el("span", { className: p && p.status === "passed" ? "done" : "", text: "🏆 التحدي النهائي" }));
      const li = el("li", { className: `journey-step ${open ? "" : "locked"}` }, head, scoreBar(current, report.target_score), chips);
      if (!open) {
        li.append(el("p", { className: "muted small", text: "🔒 تُفتح بعد اجتياز الخطوة السابقة." }));
        return li;
      }
      if (p && p.status === "passed") return li;
      const others = el("details", { className: "alternatives" }, el("summary", { text: "طرق أخرى لنفس الفجوة" }),
        el("div", { className: "solutions" }, ...step.alternatives.map((a) => activityLink(step, a, false))));
      li.append(el("div", { className: "solutions" }, activityLink(step, step.activity, true)), others);
      return li;
    }),
  );
}

function renderReassessment() {
  const info = report.reassessment;
  const box = $("r-reassess");
  if (!info || !info.total_steps) return box.classList.add("hidden");
  box.classList.remove("hidden");
  const title = el("h3", { text: "🔁 إعادة القياس" });
  if (info.reassessment_id) {
    const done = info.reassessment_status === "completed";
    const a = el("a", { className: "btn", text: done ? "عرض تقرير إعادة القياس" : "متابعة إعادة القياس" });
    a.href = done ? `report.html?id=${encodeURIComponent(info.reassessment_id)}` : `assessment.html?id=${encodeURIComponent(info.reassessment_id)}`;
    return box.replaceChildren(title, a);
  }
  const text = info.eligible
    ? "أكملت رحلتك التعليمية. إعادة القياس تتحقق بمواقف جديدة من إغلاق كل فجوة، وتستفيد من طريقة أدائك في الأنشطة."
    : `تُفتح بعد إكمال خطوات الرحلة: ${info.done_steps} من ${info.total_steps}.`;
  const btn = el("button", { className: "btn", text: "ابدأ إعادة القياس" });
  btn.type = "button";
  btn.disabled = !info.eligible;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const res = await fetch(`/api/assessments/${encodeURIComponent(assessmentId)}/reassessment`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      location.href = `assessment.html?id=${encodeURIComponent(data.assessment_id)}`;
    } catch (e) {
      btn.disabled = false;
      box.append(el("p", { className: "error", text: e.message || "تعذّر بدء إعادة القياس." }));
    }
  });
  box.replaceChildren(title, el("p", { className: "muted", text }), btn);
}

const DECISION_CLASSES = {
  closed: "status-strength",
  partial: "status-adequate",
  persistent: "status-likely_gap",
  insufficient: "status-insufficient_evidence",
};

function renderComparison() {
  if (report.kind !== "reassessment") return;
  $("r-title").textContent = "تقرير إعادة القياس";
  $("r-compare-card").classList.remove("hidden");
  const rows = report.comparison.map((c) => {
    const nums = el(
      "div",
      { className: "compare-nums" },
      el("span", { text: `قبل: ${Math.round(c.before)}%` }),
      el("span", { className: "muted", text: `بعد التدريب: ${Math.round(c.after_training)}%` }),
      el("strong", { text: `إعادة القياس: ${Math.round(c.after)}%` }),
    );
    const signals = c.behavior.length
      ? el(
          "ul",
          { className: "signal-list" },
          ...c.behavior.map((sig) => el("li", {}, el("strong", { text: `${sig.icon} ${sig.title}: ` }), document.createTextNode(`${sig.value} — ${sig.decision}`))),
        )
      : null;
    return el(
      "div",
      { className: "compare-row" },
      el(
        "div",
        { className: "priority-head" },
        el("strong", { text: c.name }),
        el("span", { className: "badge badge-soft", text: c.skill_kind ? KIND_LABELS[c.skill_kind] : DIMENSION_LABELS[c.dimension] }),
        el("span", { className: `status ${DECISION_CLASSES[c.decision]}`, text: c.decision_title }),
      ),
      nums,
      scoreBar(c.after, c.target_score),
      el("p", { className: "muted small", text: c.decision_message }),
      signals ? el("p", { className: "small sub-title", text: "ما لاحظناه من سلوكك أثناء التدريب:" }) : null,
      signals,
    );
  });
  const extra = (report.new_gaps || []).map((g) =>
    el("div", { className: "compare-row new-gap" }, el("div", { className: "priority-head" }, el("strong", { text: g.name }), el("span", { className: "status status-potential_gap", text: "🆕 فجوة جديدة" })), el("p", { className: "muted small", text: g.origin })),
  );
  const back = el("a", { className: "back", text: "→ التقرير الأول" });
  back.href = `report.html?id=${encodeURIComponent(report.parent_assessment_id)}`;
  $("r-compare").replaceChildren(...rows, ...extra, back);
}

function renderInsights() {
  if (!report.insights.length) return;
  $("r-insights-card").classList.remove("hidden");
  $("r-insights").replaceChildren(...report.insights.map((i) => el("li", { text: i.text })));
}

function renderResultsTable(table, results) {
  const head = el("tr", {}, ...["الكفاءة", "النتيجة", "الحالة", "الأدلة"].map((t) => el("th", { text: t })));
  const rows = results.map((r) => {
    const evidence = `${r.question_count} أسئلة (${r.question_types.map((t) => TYPE_LABELS[t] || t).join("، ")})` +
      (r.low_confidence_count ? ` — ${r.low_confidence_count} بثقة تصحيح منخفضة` : "");
    const cells = [
      el("td", {}, el("strong", { text: r.name }), r.skill_kind ? el("div", { className: "muted small", text: KIND_LABELS[r.skill_kind] }) : null),
      el("td", {}, scoreBar(r.score, r.target_score)),
      el("td", {}, statusBadge(r.status, r.status_label)),
      el("td", { className: "small", text: evidence }),
    ];
    return el("tr", {}, ...cells);
  });
  table.replaceChildren(el("thead", {}, head), el("tbody", {}, ...rows));
}

/* ---------- Question review ---------- */

function answerSummary(q) {
  if (q.earned_score === null || q.earned_score === undefined) return "—";
  if (q.answer_format === "choice") return q.earned_score > 0 ? "✓ صحيحة" : "✗ خاطئة";
  if (q.answer_format === "order") return q.earned_score === q.max_score ? "✓ ترتيب صحيح" : `${Math.round((q.earned_score / q.max_score) * 100)}%`;
  return `${q.earned_score} من ${q.max_score}`;
}

function renderReviewStats() {
  const counts = { good: 0, needs_work: 0, bad: 0 };
  let rated = 0;
  for (const q of review.questions) {
    if (q.review_rating) {
      counts[q.review_rating] += 1;
      rated += 1;
    }
  }
  $("review-stats").textContent =
    `قُيّم ${rated} من ${review.questions.length} سؤالًا — جيد: ${counts.good}، يحتاج تحسين: ${counts.needs_work}، سيئ: ${counts.bad}` +
    (review.ai_model ? ` · النموذج: ${review.ai_model}` : "");
}

function ratingBox(q) {
  const box = el("div", { className: "rating" });
  const status = el("span", { className: "hint" });
  const note = el("textarea", { className: "rating-note" });
  note.rows = 2;
  note.maxLength = 1000;
  note.placeholder = "ملاحظة على جودة السؤال (اختياري): غموض، مشتتات ضعيفة، إجابة خاطئة…";
  note.value = q.review_note || "";

  const buttons = RATINGS.map(([value, label]) => {
    const b = el("button", { className: "btn btn-small btn-secondary", text: label });
    b.type = "button";
    b.classList.toggle("selected", q.review_rating === value);
    b.addEventListener("click", () => save(value));
    return b;
  });

  async function save(rating) {
    status.textContent = "جارٍ الحفظ…";
    try {
      const res = await fetch(
        `/api/assessments/${encodeURIComponent(assessmentId)}/questions/${encodeURIComponent(q.question_id)}/review`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rating, note: note.value.trim() || null }),
        },
      );
      if (!res.ok) throw new Error(res.status);
      const saved = await res.json();
      q.review_rating = saved.review_rating;
      q.review_note = saved.review_note;
      buttons.forEach((b, i) => b.classList.toggle("selected", RATINGS[i][0] === rating));
      status.textContent = "✓ حُفظ";
      renderReviewStats();
    } catch {
      status.textContent = "تعذّر الحفظ";
    }
  }

  box.append(el("span", { className: "small", text: "جودة السؤال:" }), ...buttons, status);
  return el("div", {}, box, note);
}

function questionCard(q) {
  const details = el("details", { className: "q-review" });
  const summary = el(
    "summary",
    {},
    el("span", { className: "q-id", text: q.question_id }),
    el("span", { text: q.competency_name }),
    el("span", { className: "badge badge-soft", text: TYPE_LABELS[q.question_type] || q.question_type }),
    el("span", { className: `q-result ${q.earned_score > 0 ? "ok" : "bad"}`, text: answerSummary(q) }),
    q.review_rating ? el("span", { className: "small muted", text: "● مُقيَّم" }) : null,
  );
  details.append(summary);

  const body = el(
    "div",
    { className: "q-review-body" },
    el(
      "p",
      { className: "small muted" },
      document.createTextNode(
        `${BLOOM_LABELS[q.bloom_level] || q.bloom_level} · الصعوبة ${q.difficulty}/5 · الهدف: ${q.learning_objective}`,
      ),
    ),
    q.adaptation_reason ? el("p", { className: "adaptive-note", text: `لماذا هذا السؤال: ${q.adaptation_reason}` }) : null,
    el("p", { className: "q-text", text: q.question_text }),
  );
  if (q.code_snippet) body.append(el("pre", { className: "code", dir: "ltr" }, el("code", { text: q.code_snippet })));

  if (q.answer_format === "choice") {
    const ul = el("ul", { className: "review-options" });
    q.options.forEach((opt, i) => {
      const li = el("li", { text: opt });
      if (i === q.correct_option_index) li.classList.add("correct");
      if (i === q.trainee_answer) li.classList.add("chosen");
      if (i === q.trainee_answer && i !== q.correct_option_index) li.classList.add("wrong");
      ul.append(li);
    });
    body.append(ul, el("p", { className: "hint", text: "✓ الإجابة الصحيحة · ◉ إجابة المتدرب" }));
  } else if (q.answer_format === "order") {
    const correct = el("ol", { className: "rubric" }, ...q.correct_order.map((i) => el("li", { text: q.options[i] })));
    const given = el("ol", { className: "rubric" }, ...(q.trainee_answer || []).map((i) => el("li", { text: q.options[i] })));
    body.append(el("h4", { text: "الترتيب الصحيح" }), correct, el("h4", { text: "ترتيب المتدرب" }), given);
  } else {
    body.append(
      el("h4", { text: "إجابة المتدرب" }),
      el("p", { className: "answer-text", text: q.trainee_answer || "—" }),
    );
    if (q.grading_details) {
      const ul = el("ul", { className: "rubric" });
      for (const d of q.grading_details) {
        ul.append(el("li", {}, el("strong", { text: `${d.awarded}/${d.points} — ${d.criterion}` }), el("div", { className: "muted small", text: d.justification })));
      }
      body.append(el("h4", { text: "التصحيح حسب المعايير" }), ul);
    }
    if (q.feedback) body.append(el("p", { text: `ملاحظة المصحح: ${q.feedback}` }));
    if (q.grading_confidence !== null) {
      body.append(el("p", { className: "hint", text: `ثقة التصحيح: ${Math.round(q.grading_confidence * 100)}%` }));
    }
  }

  body.append(
    el("h4", { text: "الإجابة المرجعية" }),
    el("p", { text: q.reference_answer }),
    el("h4", { text: "التبرير" }),
    el("p", { text: q.rationale }),
    ratingBox(q),
  );
  details.append(body);
  return details;
}

function renderQuestions() {
  const container = $("r-questions");
  const groups = [
    ["skill", "أسئلة قياس المهارة"],
    ["knowledge", "أسئلة قياس المعرفة"],
  ];
  container.replaceChildren(
    ...groups.map(([phase, title]) =>
      el("div", { className: "q-group" }, el("h3", { text: title }), ...review.questions.filter((q) => q.phase === phase).map(questionCard)),
    ),
  );
  renderReviewStats();
}

function download() {
  const blob = new Blob([JSON.stringify({ report, review }, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = el("a");
  a.href = url;
  a.download = `${assessmentId}.json`;
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ---------- Init ---------- */

async function load() {
  if (!assessmentId) return showError("لم يُحدَّد رقم التقييم.");
  try {
    const [r1, r2] = await Promise.all([
      fetch(`/api/assessments/${encodeURIComponent(assessmentId)}/report`),
      fetch(`/api/assessments/${encodeURIComponent(assessmentId)}/review`),
    ]);
    if (r1.status === 404) return showError("التقييم غير موجود.");
    if (r1.status === 409) {
      return showError("لم يكتمل هذا التقييم بعد.", { href: `assessment.html?id=${encodeURIComponent(assessmentId)}`, text: "إكمال التقييم" });
    }
    if (!r1.ok || !r2.ok) throw new Error();
    report = await r1.json();
    review = await r2.json();
  } catch {
    return showError("تعذّر تحميل التقرير. تأكد من تشغيل الخادم.");
  }

  renderSummary();
  renderComparison();
  renderReassessment();
  renderPriorities();
  renderInsights();
  renderJourney();
  renderResultsTable($("r-skills"), report.skill_results);
  renderResultsTable($("r-knowledge"), report.knowledge_results);
  renderQuestions();
  $("download-btn").addEventListener("click", download);

  $("view-loading").classList.add("hidden");
  $("view-report").classList.remove("hidden");
}

load();
