/* Adaptive assessment: one question at a time; the server writes each next question
   from the previous answer. The trainee is never told what is being measured.
   All AI-generated text is inserted with textContent (never innerHTML). */

const assessmentId = new URLSearchParams(location.search).get("id");
const POLL_MS = 3000;

const SECTION_TITLES = {
  skill: "القسم الأول: قياس المهارة",
  knowledge: "القسم الثاني: قياس المعرفة",
};
const TRANSIENT = /^(preparing|grading|generating)_/;

const $ = (id) => document.getElementById(id);
const views = ["loading", "error", "intro", "question"];

let state = null;
let selected = null; // chosen option index for the current choice question
let order = []; // current order (displayed option indices) for an ordering question
let retryAction = null;

/* ---------- Helpers ---------- */

function show(name) {
  for (const v of views) $(`view-${v}`).classList.toggle("hidden", v !== name);
  window.scrollTo({ top: 0 });
}

function setTrack(phase) {
  const order = ["skill", "knowledge", "report"];
  const idx = order.indexOf(phase);
  order.forEach((p, i) => {
    $(`track-${p}`).classList.toggle("done", i < idx);
    $(`track-${p}`).classList.toggle("active", i === idx);
  });
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  return { ok: res.ok, status: res.status, data };
}

const base = () => `/api/assessments/${encodeURIComponent(assessmentId)}`;

function errorMessage(res) {
  const detail = res.data && res.data.detail;
  return typeof detail === "string" ? detail : "حدث خطأ غير متوقع. حاول مرة أخرى.";
}

function showLoading(text) {
  $("loading-text").textContent = text;
  show("loading");
}

function showError(message, action) {
  $("error-text").textContent = message;
  retryAction = action;
  $("retry-btn").classList.toggle("hidden", !action);
  show("error");
}

const draftKey = (qid) => `draft:${assessmentId}:${qid}`;

function storage(fn) {
  try {
    return fn(localStorage);
  } catch {
    return null; // storage unavailable — the answer just isn't kept across reloads
  }
}

/* ---------- Flow ---------- */

async function refresh() {
  try {
    const res = await api("GET", base());
    if (!res.ok) {
      return res.status === 404 ? showError("التقييم غير موجود.", null) : showError(errorMessage(res), refresh);
    }
    drive(res.data);
  } catch {
    showError("تعذّر الاتصال بالخادم.", refresh);
  }
}

function drive(view) {
  state = view;
  const s = view.status;
  if (s === "completed") {
    setTrack("report");
    location.href = `report.html?id=${encodeURIComponent(assessmentId)}`;
    return;
  }
  setTrack(view.phase);
  if (s === "created" || s === "skill_done") return showIntro();
  if (s.endsWith("_question") && view.question) return showQuestion();
  if (s.endsWith("_answered")) return post("next", undefined, "جارٍ تجهيز السؤال التالي…");
  if (TRANSIENT.test(s)) {
    showLoading(s.startsWith("preparing") ? "جارٍ تجهيز الأسئلة…" : "جارٍ تجهيز السؤال التالي…");
    return setTimeout(refresh, POLL_MS);
  }
  showError("حالة غير معروفة للتقييم.", refresh);
}

async function post(action, body, loadingText) {
  showLoading(loadingText);
  try {
    const res = await api("POST", `${base()}/${state.phase}/${action}`, body);
    if (res.ok) return drive(res.data);
    if (res.status === 409) return setTimeout(refresh, POLL_MS); // already in progress, or state moved on
    const retryable = !res.data || res.data.retryable !== false;
    // After an answer is graded, a failure only concerns the next question: retry with /next.
    showError(errorMessage(res), retryable ? refresh : null);
  } catch {
    showError("انقطع الاتصال بالخادم. حاول مرة أخرى.", refresh);
  }
}

/* ---------- Intro ---------- */

function sectionTitle() {
  const title = SECTION_TITLES[state.phase];
  return state.kind === "reassessment" ? `إعادة القياس · ${title}` : title;
}

function showIntro() {
  $("intro-title").textContent = sectionTitle();
  $("intro-count").textContent = `عدد الأسئلة: ${state.total}`;
  show("intro");
}

/* ---------- Question ---------- */

function showQuestion() {
  const q = state.question;
  const number = state.answered + 1;
  $("q-section").textContent = sectionTitle();
  $("q-counter").textContent = `السؤال ${number} من ${state.total}`;
  $("q-progress").style.width = `${((number - 1) / state.total) * 100}%`;
  $("q-text").textContent = q.question_text;
  $("q-error").textContent = "";

  const pre = $("q-code").parentElement;
  pre.classList.toggle("hidden", !q.code_snippet);
  $("q-code").textContent = q.code_snippet || "";

  selected = null;
  const isText = q.answer_format === "text";
  const isOrder = q.answer_format === "order";
  $("q-open").classList.toggle("hidden", !isText);
  $("q-order-box").classList.toggle("hidden", !isOrder);
  $("q-options").classList.toggle("hidden", isText || isOrder);

  if (isOrder) {
    order = q.options.map((_, i) => i);
    renderOrder();
  } else if (isText) {
    const ta = $("q-answer");
    ta.value = storage((s) => s.getItem(draftKey(q.question_id))) || "";
    $("q-answer-count").textContent = ta.value.length;
  } else {
    const legend = $("q-options").querySelector("legend");
    $("q-options").replaceChildren(
      legend,
      ...q.options.map((text, i) => {
        const label = document.createElement("label");
        label.className = "option";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = `opt-${q.question_id}`;
        input.value = i;
        input.addEventListener("change", () => {
          selected = i;
          updateSubmit();
        });
        const span = document.createElement("span");
        span.textContent = text;
        label.append(input, span);
        return label;
      }),
    );
  }
  $("q-submit").textContent = number === state.total ? "إنهاء القسم" : "التالي";
  updateSubmit();
  show("question");
}

function renderOrder() {
  const q = state.question;
  const list = $("q-order");
  list.replaceChildren(
    ...order.map((optionIndex, pos) => {
      const li = document.createElement("li");
      li.className = "order-item";
      const text = document.createElement("span");
      text.textContent = q.options[optionIndex];
      const controls = document.createElement("span");
      controls.className = "order-controls";
      for (const [label, delta, aria] of [["▲", -1, "تحريك لأعلى"], ["▼", 1, "تحريك لأسفل"]]) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn btn-small btn-secondary";
        b.textContent = label;
        b.setAttribute("aria-label", `${aria}: ${q.options[optionIndex]}`);
        b.disabled = pos + delta < 0 || pos + delta >= order.length;
        b.addEventListener("click", () => {
          [order[pos], order[pos + delta]] = [order[pos + delta], order[pos]];
          renderOrder();
          list.children[pos + delta].querySelectorAll("button")[delta < 0 ? 0 : 1]?.focus();
        });
        controls.append(b);
      }
      li.append(text, controls);
      return li;
    }),
  );
}

function currentAnswer() {
  const q = state.question;
  if (q.answer_format === "order") return [...order];
  if (q.answer_format === "text") {
    const text = $("q-answer").value.trim();
    return text ? text : null;
  }
  return selected;
}

function updateSubmit() {
  $("q-submit").disabled = currentAnswer() === null;
}

function submitAnswer() {
  const answer = currentAnswer();
  if (answer === null) {
    $("q-error").textContent = "اختر إجابة أو اكتبها قبل المتابعة.";
    return;
  }
  const q = state.question;
  storage((s) => s.removeItem(draftKey(q.question_id)));
  const last = state.answered + 1 === state.total;
  post("answer", { question_id: q.question_id, answer }, last ? "جارٍ إنهاء القسم…" : "جارٍ تجهيز السؤال التالي…");
}

/* ---------- Init ---------- */

$("intro-start").addEventListener("click", () => post("start", undefined, "جارٍ تجهيز الأسئلة…"));
$("q-submit").addEventListener("click", submitAnswer);
$("q-answer").addEventListener("input", (e) => {
  $("q-answer-count").textContent = e.target.value.length;
  storage((s) => s.setItem(draftKey(state.question.question_id), e.target.value));
  updateSubmit();
});
$("retry-btn").addEventListener("click", () => retryAction && retryAction());

if (!assessmentId) {
  showError("لم يُحدَّد رقم التقييم. ابدأ من صفحة ملف المتدرب.", null);
} else {
  refresh();
}
