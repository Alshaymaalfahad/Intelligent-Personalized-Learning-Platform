/* 🎓 علّم غيرك */
(() => {
  const { el, button, meter } = ActivityKit;

  function chat(level) {
    return el("div", { className: "chat" }, ...level.messages.map((m) =>
      el("div", { className: `bubble ${m.from === "saud" ? "from-saud" : "from-me"}` },
        el("span", { className: "bubble-name", text: m.from === "saud" ? "🧑‍🎓 سعود" : "أنت" }),
        el("p", { text: m.text }))));
  }

  function composer(ctx, level, placeholder, label, action, onDone, loadingText) {
    const ta = el("textarea", {});
    ta.rows = 4;
    ta.maxLength = 1500;
    ta.placeholder = placeholder;
    ta.value = ctx.state.draft || "";
    ta.addEventListener("input", () => (ctx.state.draft = ta.value));
    return el("div", { className: "card" }, ta, el("div", { className: "actions" }, button(label, "", () => {
      if (ta.value.trim().length < 15) return ctx.mentor("اكتب شرحًا أوضح (15 حرفًا على الأقل).");
      const text = ta.value;
      ctx.state.draft = "";
      ctx.send("action", { action, payload: { text } }, onDone, loadingText);
    })));
  }

  ActivityKit.renderers.teach_others = {
    stat: (level) => (level.is_boss ? "📝 اختبار سعود" : `📊 فهم سعود: ${level.meter}%`),
    render(body, level, ctx) {
      const head = el("div", { className: "card" },
        el("p", { className: "muted small", text: level.is_boss ? "👑 الزعيم: اختبار سعود" : `الجولة ${level.number}: المفهوم` }),
        el("h2", { text: level.concept }),
        level.is_boss ? el("p", { text: `سعود سيدخل اختبارًا من ${level.quiz_size} أسئلة، ويجيب فقط بما علّمته إياه. إذا نجح سعود، تنجح أنت.` })
          : meter(level.meter, `مقياس فهم سعود: ${level.meter}%`));
      const parts = [head, el("div", { className: "card" }, chat(level))];

      if (!level.is_boss && !level.finished) {
        if (level.turns_left > 0 && level.meter < 100) {
          parts.push(composer(ctx, level, "اشرح لسعود بأسلوبك… (المثال يساعده كثيرًا)", `أرسل (${level.turns_left} ردود متبقية)`, "explain",
            (o) => (o.accurate === false ? "انتبه: في شرحك معلومة غير دقيقة، فلم يتقدم فهم سعود." : o.meter_change > 0 ? `فهم سعود ارتفع إلى ${o.meter}% (+${o.xp_change} XP).` : "سعود ما زال غير مقتنع؛ وضّح أكثر أو أعطه مثالًا."),
            "سعود يقرأ شرحك…"));
        } else {
          parts.push(el("p", { className: "ok-text", text: level.meter >= 80 ? "سعود فهم المفهوم! أنهِ الجولة." : "انتهت ردود هذه الجولة. أنهِ الجولة." }));
        }
      }

      if (level.is_boss && !level.quiz_result) {
        parts.push(composer(ctx, level, "ملخص أخير لسعود قبل الاختبار (بدون تلميحات)…", "📝 أرسل الملخص وابدأ اختبار سعود", "final_lesson",
          (o) => (o.saud_passed ? `🎉 نجح سعود (${o.correct} من ${ctx.level().quiz_size})! شرحك وصل.` : `سعود أجاب ${o.correct} من ${ctx.level().quiz_size}. راجع أين لم يصله الشرح.`),
          "سعود يحل الاختبار…"));
      }
      if (level.quiz_result) {
        parts.push(el("div", { className: "card" },
          el("h3", { className: level.saud_passed ? "ok-text" : "warn-text", text: level.saud_passed ? "✅ نجح سعود في اختباره" : "❌ لم ينجح سعود هذه المرة" }),
          ...level.quiz_result.map((q, i) => el("div", { className: "quiz-item" },
            el("p", { className: "sub-title", text: `${i + 1}. ${q.question}` }),
            el("p", { className: q.saud_correct ? "ok-text" : "warn-text", text: `${q.saud_correct ? "✓" : "✗"} سعود اختار: ${q.options[q.saud_choice]}` }),
            q.saud_correct ? null : el("p", { className: "muted small", text: `الصحيح: ${q.options[q.correct]}` }),
            el("p", { className: "muted small", text: `سعود: «${q.reasoning}»` })))));
      }
      body.replaceChildren(...parts);
    },
    finishLabel: (level) => (level.is_boss ? "عرض النتيجة" : "إنهاء الجولة"),
    finishConfirm: (level) => (level.is_boss && !level.quiz_result ? "لم يدخل سعود الاختبار بعد. متابعة؟" : null),
    summary(level) {
      return level.key_points ? [el("h2", { text: "النقاط التي يحتاجها شرح قوي" }), el("ul", { className: "plain-list" }, ...level.key_points.map((k) => el("li", { text: k })))] : [];
    },
  };
})();
