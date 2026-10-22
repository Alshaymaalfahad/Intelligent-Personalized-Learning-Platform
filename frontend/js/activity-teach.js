/* 🎓 Teach Someone */
(() => {
  const { el, button, meter, t } = ActivityKit;

  function chat(level) {
    return el("div", { className: "chat" }, ...level.messages.map((m) =>
      el("div", { className: `bubble ${m.from === "saud" ? "from-saud" : "from-me"}` },
        el("span", { className: "bubble-name", text: m.from === "saud" ? `🧑‍🎓 ${t("teach.saud")}` : t("teach.you") }),
        el("p", { text: m.text }))));
  }

  function composer(ctx, placeholder, label, action, onDone, loadingText) {
    const ta = el("textarea", { attrs: { rows: "4", maxlength: "1500", placeholder } });
    ta.value = ctx.state.draft || "";
    ta.addEventListener("input", () => (ctx.state.draft = ta.value));
    return el("div", { className: "card" }, ta, el("div", { className: "actions end" }, button(label, "", () => {
      if (ta.value.trim().length < 15) return ctx.mentor(t("teach.too_short"));
      const text = ta.value;
      ctx.state.draft = "";
      ctx.send("action", { action, payload: { text } }, onDone, loadingText);
    }, "arrow")));
  }

  ActivityKit.renderers.teach_others = {
    stat: (level) => (level.is_boss ? `📝 ${t("teach.test")}` : `📊 ${t("teach.meter_stat", { n: level.meter })}`),
    render(body, level, ctx) {
      const head = el("div", { className: "card" },
        el("span", { className: "eyebrow", text: level.is_boss ? `👑 ${t("teach.test")}` : t("teach.round", { n: level.number }) }),
        el("h2", { text: level.concept }),
        level.is_boss ? el("p", { text: t("teach.test_intro", { n: level.quiz_size }) }) : meter(level.meter, t("teach.meter", { n: level.meter })));
      const parts = [head, el("div", { className: "card" }, chat(level))];

      if (!level.is_boss && !level.finished) {
        if (level.turns_left > 0 && level.meter < 100) {
          parts.push(composer(ctx, t("teach.placeholder"), t("teach.send", { n: level.turns_left }), "explain",
            (o) => (o.accurate === false ? t("teach.inaccurate") : o.meter_change > 0 ? t("teach.rose", { n: o.meter, xp: o.xp_change }) : t("teach.not_yet")),
            t("teach.reading")));
        } else {
          parts.push(el("p", { className: "ok-text", text: t(level.meter >= 80 ? "teach.understood" : "teach.round_over") }));
        }
      }
      if (level.is_boss && !level.quiz_result) {
        parts.push(composer(ctx, t("teach.final_placeholder"), t("teach.final_send"), "final_lesson",
          (o) => (o.saud_passed ? t("teach.passed", { n: o.correct, total: ctx.level().quiz_size }) : t("teach.failed", { n: o.correct, total: ctx.level().quiz_size })),
          t("teach.solving")));
      }
      if (level.quiz_result) {
        parts.push(el("div", { className: "card" },
          el("h3", { className: level.saud_passed ? "ok-text" : "warn-text", text: t(level.saud_passed ? "teach.result_passed" : "teach.result_failed") }),
          ...level.quiz_result.map((q, i) => el("div", { className: "quiz-item" },
            el("p", { className: "sub-title", text: `${i + 1}. ${q.question}` }),
            el("p", { className: q.saud_correct ? "ok-text" : "warn-text", text: `${q.saud_correct ? "✓" : "✗"} ${t("teach.saud_chose")}: ${q.options[q.saud_choice]}` }),
            q.saud_correct ? null : el("p", { className: "hint", text: `${t("teach.correct")}: ${q.options[q.correct]}` }),
            el("p", { className: "hint", text: `${t("teach.saud")}: “${q.reasoning}”` })))));
      }
      body.replaceChildren(...parts);
    },
    finishLabel: (level) => t(level.is_boss ? "teach.see_result" : "teach.finish_round"),
    finishConfirm: (level) => (level.is_boss && !level.quiz_result ? t("teach.finish_confirm") : null),
    summary: (level) => (level.key_points ? [el("h2", { text: t("teach.key_points") }), el("ul", { className: "plain-list" }, ...level.key_points.map((k) => el("li", { text: k })))] : []),
  };
})();
