/* 🧩 تحديات من واقع العمل */
(() => {
  const { el, button, artifact } = ActivityKit;
  const STATUS = { met: ["✅", "ok-text"], partial: ["🟡", "warn-text"], missing: ["❌", "warn-text"] };
  const stars = (n) => "⭐".repeat(n) + "☆".repeat(5 - n);

  function lastDraft(level, act) {
    const own = level.submissions[level.submissions.length - 1];
    if (own) return own.text;
    if (level.surprise) {
      const prev = act.levels[level.number - 2];
      const best = prev && [...prev.submissions].sort((a, b) => b.percent - a.percent)[0];
      return best ? best.text : "";
    }
    return "";
  }

  function review(sub) {
    return el("div", { className: "card review" },
      el("div", { className: "priority-head" }, el("strong", { text: "مراجعة المدير" }), el("span", { className: "stars", text: stars(sub.stars) }), el("span", { className: "muted", text: `${sub.percent}%` })),
      el("ul", { className: "criteria-list" }, ...sub.criteria.map((c) =>
        el("li", {}, el("span", { className: STATUS[c.status][1], text: `${STATUS[c.status][0]} ${c.criterion}` }), el("div", { className: "muted small", text: c.comment })))),
      el("blockquote", { className: "manager-note", text: sub.feedback }));
  }

  ActivityKit.renderers.work_challenge = {
    stat: (level) => `⭐ أفضل تقييم: ${level.best_stars ? stars(level.best_stars) : "—"}`,
    render(body, level, ctx) {
      ctx.state.checked = ctx.state.checked || {};
      const email = el("div", { className: "card inbox" },
        level.surprise ? el("span", { className: "status status-potential_gap", text: "📨 تحديث مفاجئ!" }) : null,
        el("p", { className: "muted small", text: `من: ${level.sender_name} — ${level.sender_role}` }),
        el("h2", { text: level.subject }),
        el("p", { className: "email-body", text: level.message }),
        level.input_lines.length ? el("div", {}, el("p", { className: "sub-title", text: `📎 ${level.input_title}` }), artifact(level.input_lines)) : null);

      const checklist = el("ul", { className: "checklist" }, ...level.criteria.map((c, i) => {
        const box = el("input", { type: "checkbox" });
        box.checked = !!ctx.state.checked[i];
        box.addEventListener("change", () => (ctx.state.checked[i] = box.checked));
        return el("li", {}, el("label", {}, box, el("span", { text: ` ${c.criterion}` })));
      }));

      const parts = [email, el("div", { className: "card" }, el("h3", { text: "✅ معايير القبول" }),
        el("p", { className: "hint", text: "اشطب كل معيار بعد ما تغطيه في تسليمك." }), checklist,
        el("p", { className: "sub-title", text: "المطلوب تسليمه:" }), el("p", { text: level.deliverable_instructions }))];

      if (!level.finished && level.submissions_left > 0) {
        const ta = el("textarea", { className: "deliverable" });
        ta.rows = 10;
        ta.maxLength = 3000;
        ta.placeholder = "اكتب مخرجك هنا…";
        ta.value = ctx.state.draft ?? lastDraft(level, ctx.act);
        ta.addEventListener("input", () => (ctx.state.draft = ta.value));
        parts.push(el("div", { className: "card" }, ta,
          el("div", { className: "actions" }, button(`📤 تسليم (${level.submissions_left} متبقية)`, "", () => {
            if (ta.value.trim().length < 20) return ctx.mentor("اكتب مخرجًا أوضح قبل التسليم (20 حرفًا على الأقل).");
            ctx.state.draft = ta.value;
            ctx.send("action", { action: "submit", payload: { text: ta.value } }, (o) =>
              o.submission.percent >= 80
                ? `${level.sender_name} راضٍ عن التسليم ${stars(o.submission.stars)} (+${o.xp_change} XP). تقدر تنهي المرحلة.`
                : `${stars(o.submission.stars)} — اقرأ ملاحظات المراجعة، عدّل، وأعد التسليم.`,
              "المدير يراجع تسليمك…");
          }))));
      }
      if (level.submissions.length) parts.push(review(level.submissions[level.submissions.length - 1]));
      body.replaceChildren(...parts);
    },
    finishConfirm: (level) => (level.submissions.length ? null : "لم تسلّم بعد. إنهاء المرحلة دون تسليم؟"),
    summary(level) {
      return level.model_answer ? [el("h2", { text: "ما الذي يميز التسليم القوي؟" }), el("p", { className: "email-body", text: level.model_answer })] : [];
    },
  };
})();
