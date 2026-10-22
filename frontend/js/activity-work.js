/* 🧩 Real-World Challenges */
(() => {
  const { el, button, artifact, chip, t } = ActivityKit;
  const STATUS = { met: ["✅", "ok-text"], partial: ["🟡", "warn-text"], missing: ["❌", "warn-text"] };
  const stars = (n) => "⭐".repeat(n) + "☆".repeat(5 - n);

  // Your own last attempt in this level (to revise it); a new level starts empty.
  function lastDraft(level) {
    const own = level.submissions[level.submissions.length - 1];
    return own ? own.text : "";
  }

  function review(sub) {
    return el("div", { className: "card" },
      el("div", { className: "head-row" }, el("strong", { text: t("work.review") }), el("span", { className: "stars", text: stars(sub.stars) }), chip(`${sub.percent}%`, "cyan")),
      el("ul", { className: "criteria-list" }, ...sub.criteria.map((c) =>
        el("li", {}, el("span", { className: STATUS[c.status][1], text: `${STATUS[c.status][0]} ${c.criterion}` }), el("div", { className: "hint", text: c.comment })))),
      el("blockquote", { className: "manager-note", text: sub.feedback }));
  }

  ActivityKit.renderers.work_challenge = {
    stat: (level) => `⭐ ${t("work.best")}: ${level.best_stars ? stars(level.best_stars) : "—"}`,
    render(body, level, ctx) {
      ctx.state.checked = ctx.state.checked || {};
      const email = el("div", { className: "card inbox" },
        level.surprise ? chip(`📨 ${t("work.surprise")}`, "amber") : null,
        el("p", { className: "hint", text: `${t("work.from")}: ${level.sender_name} — ${level.sender_role}` }),
        el("h2", { text: level.subject }),
        el("p", { className: "email-body", text: level.message }),
        level.input_lines.length ? el("div", {}, el("p", { className: "sub-title", text: `📎 ${level.input_title}` }), artifact(level.input_lines)) : null);

      const checklist = el("ul", { className: "checklist" }, ...level.criteria.map((c, i) => {
        const box = el("input", { type: "checkbox" });
        box.checked = !!ctx.state.checked[i];
        box.addEventListener("change", () => (ctx.state.checked[i] = box.checked));
        return el("li", {}, el("label", {}, box, el("span", { text: ` ${c.criterion}` })));
      }));

      const parts = [email, el("div", { className: "card" }, el("h3", { text: `✅ ${t("work.criteria")}` }),
        el("p", { className: "hint", text: t("work.criteria_hint") }), checklist,
        el("p", { className: "sub-title", text: t("work.deliver") }), el("p", { text: level.deliverable_instructions }))];

      if (!level.finished && level.submissions_left > 0) {
        const ta = el("textarea", { className: "deliverable", attrs: { rows: "10", maxlength: "3000", placeholder: t("work.placeholder") } });
        ta.value = ctx.state.draft ?? lastDraft(level);
        ta.addEventListener("input", () => (ctx.state.draft = ta.value));
        parts.push(el("div", { className: "card" },
          el("label", { className: "sub-title", text: t("work.your_answer") }),
          ta,
          el("div", { className: "actions end" }, button(t("work.submit", { n: level.submissions_left }), "", () => {
            if (ta.value.trim().length < 20) return ctx.mentor(t("work.too_short"));
            ctx.state.draft = ta.value;
            ctx.send("action", { action: "submit", payload: { text: ta.value } }, (o) =>
              o.submission.percent >= 80 ? t("work.happy", { name: level.sender_name, stars: stars(o.submission.stars), xp: o.xp_change })
                : t("work.revise", { stars: stars(o.submission.stars) }), t("work.reviewing"));
          }, "arrow"))));
      }
      if (level.submissions.length) parts.push(review(level.submissions[level.submissions.length - 1]));
      body.replaceChildren(...parts);
    },
    finishConfirm: (level) => (level.submissions.length ? null : t("work.finish_confirm")),
    summary: (level) => (level.model_answer ? [el("h2", { text: t("work.model") }), el("p", { className: "email-body", text: level.model_answer })] : []),
  };
})();
