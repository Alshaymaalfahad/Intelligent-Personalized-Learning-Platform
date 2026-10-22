/* Adaptive assessment: one question at a time; the server writes each next question from
   the previous answer. The trainee is never told what is being measured.
   AI-generated text is inserted with textContent (never innerHTML). */
(() => {
  const { el, button, svg, nudge, api, store, shell, chip, loadingView, t } = App;
  shell("assessment");
  document.title = t("assess.title");

  const assessmentId = new URLSearchParams(location.search).get("id");
  const page = document.getElementById("page");
  const POLL_MS = 3000;
  const TRANSIENT = /^(preparing|grading|generating)_/;
  const LETTERS = "ABCDE";

  let state = null;
  let selected = null;
  let order = [];

  if (assessmentId) store.set("assessment_id", assessmentId);
  const base = () => `/api/assessments/${encodeURIComponent(assessmentId)}`;

  /* ---------- Views ---------- */

  function header() {
    const sec = state.sections || { skill: { total: 10, answered: 0 }, knowledge: { total: 10, answered: 0 } };
    const dots = (total, done) => el("div", { className: "dots" }, ...Array.from({ length: total }, (_, i) => el("i", { className: i < done ? "on" : "" })));
    const segment = (n, name, label) => {
      const { total, answered } = sec[name];
      const text = el("div", {}, el("span", { className: "label", text: t("assess.segment", { n }) }), el("strong", { text: `${label} ${answered}/${total}` }));
      return el("div", { className: "segment" }, ...(n === 1 ? [text, dots(total, answered)] : [dots(total, answered), text]));
    };
    return el("div", { className: "card" },
      el("div", { className: "segments" },
        sec.skill.total ? segment(1, "skill", t("assess.skills")) : null,
        sec.knowledge.total ? segment(2, "knowledge", t("assess.knowledge")) : null),
      el("div", { className: "status-row", attrs: { "aria-hidden": "true" } },
        chip(t("assess.adapting"), "cyan", "sparkle"),
        state.kind === "reassessment" ? chip(t("assess.reassessment"), "", "refresh") : null));
  }

  function sectionTitle() {
    const title = t(state.phase === "skill" ? "assess.section_skill" : "assess.section_knowledge");
    return state.kind === "reassessment" ? `${t("assess.reassessment")} · ${title}` : title;
  }

  function showLoading(text, hint) {
    page.replaceChildren(loadingView(text, hint || t("assess.loading_hint")));
  }

  function showError(message, retry) {
    page.replaceChildren(el("div", { className: "card" }, el("h2", { text: t("error.title") }), el("p", { text: message }),
      retry ? el("div", { className: "actions" }, button(t("error.retry"), "", retry)) : null));
  }

  function showIntro() {
    page.replaceChildren(header(), el("div", { className: "card center" },
      nudge(90),
      el("h1", { text: sectionTitle() }),
      el("p", { className: "muted", text: t("assess.intro_count", { n: state.total }) }),
      el("p", { className: "muted", text: t("assess.intro_no_back") }),
      el("div", { className: "actions end" }, button(t("assess.start"), "btn-big", () => post("start", undefined, t("assess.preparing")), "arrow"))));
  }

  function showQuestion() {
    const q = state.question;
    const number = state.answered + 1;
    selected = null;
    const next = button(number === state.total ? t("assess.finish_section") : t("assess.next"), "btn-big", submitAnswer, "arrow");
    next.id = "next-btn";
    next.disabled = q.answer_format !== "order";
    const update = () => (next.disabled = currentAnswer() === null);

    let answerArea;
    if (q.answer_format === "order") {
      order = q.options.map((_, i) => i);
      answerArea = el("div", {}, el("p", { className: "hint", text: t("assess.order_hint") }), el("ol", { className: "order-list", id: "order-list" }));
    } else if (q.answer_format === "text") {
      const ta = el("textarea", { id: "q-answer", attrs: { rows: "6", maxlength: "3000", placeholder: t("assess.write_placeholder") } });
      try {
        ta.value = localStorage.getItem(`draft:${assessmentId}:${q.question_id}`) || "";
      } catch {
        /* storage unavailable */
      }
      ta.addEventListener("input", () => {
        try {
          localStorage.setItem(`draft:${assessmentId}:${q.question_id}`, ta.value);
        } catch {
          /* storage unavailable */
        }
        update();
      });
      answerArea = ta;
    } else {
      answerArea = el("fieldset", { className: "options" }, el("legend", { className: "sr-only", text: t("assess.choose") }),
        ...q.options.map((text, i) => {
          const input = el("input", { type: "radio" });
          input.name = `opt-${q.question_id}`;
          input.value = i;
          input.addEventListener("change", () => {
            selected = i;
            update();
          });
          return el("label", { className: "option" }, input, el("span", { className: "letter", text: LETTERS[i] || String(i + 1) }), el("span", { className: "text", text }));
        }));
    }

    page.replaceChildren(header(), el("div", { className: "card" },
      el("div", { className: "q-head" },
        el("div", {}, el("span", { className: "eyebrow", text: sectionTitle() }),
          el("h2", {}, el("span", { text: `${t("assess.question")} ${number} ` }), chip(t(`qtype.${q.question_type}`), "cyan"))),
        el("span", { className: "muted small", text: t("assess.of", { n: number, total: state.total }) })),
      el("p", { className: "q-text", text: q.question_text }),
      q.code_snippet ? el("pre", { className: "code", dir: "ltr" }, el("code", { text: q.code_snippet })) : null,
      answerArea,
      el("p", { className: "error", id: "q-error" })),
    el("div", { className: "q-footer" }, el("span", {}), el("span", { className: "calm-pill" }, nudge(34), el("span", { text: t("assess.calm") })), next));
    if (q.answer_format === "order") renderOrder();
    if (q.answer_format === "text") update();
  }

  function renderOrder() {
    const q = state.question;
    const list = document.getElementById("order-list");
    list.replaceChildren(...order.map((optionIndex, pos) => {
      const up = button("▲", "btn-secondary btn-small", () => move(pos, -1));
      const down = button("▼", "btn-secondary btn-small", () => move(pos, 1));
      up.disabled = pos === 0;
      down.disabled = pos === order.length - 1;
      up.setAttribute("aria-label", `${t("assess.move_up")}: ${q.options[optionIndex]}`);
      down.setAttribute("aria-label", `${t("assess.move_down")}: ${q.options[optionIndex]}`);
      return el("li", { className: "order-item" }, el("span", { text: App.plain(q.options[optionIndex]) }), el("span", { className: "order-controls" }, up, down));
    }));
  }

  function move(pos, delta) {
    [order[pos], order[pos + delta]] = [order[pos + delta], order[pos]];
    renderOrder();
  }

  function currentAnswer() {
    const q = state.question;
    if (q.answer_format === "order") return [...order];
    if (q.answer_format === "text") {
      const v = document.getElementById("q-answer").value.trim();
      return v || null;
    }
    return selected;
  }

  function submitAnswer() {
    const answer = currentAnswer();
    if (answer === null) return (document.getElementById("q-error").textContent = t("assess.need_answer"));
    const q = state.question;
    try {
      localStorage.removeItem(`draft:${assessmentId}:${q.question_id}`);
    } catch {
      /* ignore */
    }
    const last = state.answered + 1 === state.total;
    post("answer", { question_id: q.question_id, answer }, last ? t("assess.finishing") : t("assess.next_loading"));
  }

  /* ---------- Flow ---------- */

  async function refresh() {
    try {
      drive(await api("GET", base()));
    } catch (e) {
      showError(e.status === 404 ? t("assess.not_found") : e.message, e.status === 404 ? null : refresh);
    }
  }

  function drive(view) {
    state = view;
    if (view.trainee_id) store.set("trainee_id", view.trainee_id);
    const s = view.status;
    if (s === "completed") return (location.href = `report.html?id=${encodeURIComponent(assessmentId)}`);
    if (s === "created" || s === "skill_done") return showIntro();
    if (s.endsWith("_question") && view.question) return showQuestion();
    if (s.endsWith("_answered")) return post("next", undefined, t("assess.next_loading"));
    if (TRANSIENT.test(s)) {
      showLoading(s.startsWith("preparing") ? t("assess.preparing") : t("assess.next_loading"));
      return setTimeout(refresh, POLL_MS);
    }
    showError(t("assess.unknown_state"), refresh);
  }

  async function post(action, body, loadingText) {
    showLoading(loadingText);
    try {
      drive(await api("POST", `${base()}/${state.phase}/${action}`, body));
    } catch (e) {
      if (e.status === 409) return setTimeout(refresh, POLL_MS);
      showError(e.message, e.retryable ? refresh : null);
    }
  }

  if (!assessmentId) showError(t("assess.no_id"), null);
  else refresh();
})();
