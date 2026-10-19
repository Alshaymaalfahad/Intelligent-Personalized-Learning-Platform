/* 🔐 غرفة الهروب المهنية */
(() => {
  const { el, button, artifact, radioGroup } = ActivityKit;

  function codeDigits(act) {
    return act.levels.map((lv) => (lv.digit !== undefined ? String(lv.digit) : "_"));
  }

  ActivityKit.renderers.escape_room = {
    stat: (level, act) => `🔑 الرمز: ${codeDigits(act).join(" ")}`,
    render(body, level, ctx) {
      const s = level.state;
      const done = s.solved || s.revealed;
      const parts = [
        el("div", { className: "card door" },
          el("h2", { text: `${level.is_boss ? "🚪 الباب الأخير" : "🚪"} ${level.title}` }),
          el("p", { text: level.scenario }),
          artifact(level.artifact_lines, level.artifact_kind)),
      ];

      // Decision
      const decision = el("div", { className: "card" }, el("h3", { text: level.question }));
      if (!done) {
        const group = radioGroup(`door-${level.number}`, level.options, level.challenge_type === "multi_select" ? "اختر كل ما ينطبق" : null, level.challenge_type === "multi_select");
        decision.append(group, el("p", { className: "hint", text: `المحاولات المتبقية: ${level.tries_left}` }),
          el("div", { className: "actions" }, button("قرّر", "", () => {
            const selected = group.values();
            if (!selected.length) return;
            ctx.send("action", { action: "answer", payload: { selected } }, (o) =>
              o.result === "solved"
                ? `🔓 قرار صحيح! +${o.xp_change} XP. ${o.consequence} الآن: لماذا هذا هو القرار الصحيح؟`
                : o.result === "revealed"
                  ? `نتيجة قرارك: ${o.consequence} لا بأس، هذا هو القرار الصحيح، وفي ورقة الدليل السبب. برّر الآن.`
                  : `نتيجة قرارك: ${o.consequence} اقرأ ورقة الدليل وجرّب مرة أخرى.`);
          })));
      } else {
        decision.append(el("ul", { className: "review-options" }, ...level.options.map((o, i) => {
          const li = el("li", { text: o });
          if (level.correct.includes(i)) li.classList.add("correct");
          if ((s.chosen || []).includes(i) && !level.correct.includes(i)) li.classList.add("wrong");
          return li;
        })));
      }
      if (s.consequence) decision.append(el("p", { className: s.solved ? "ok-text" : "warn-text", text: `نتيجة قرارك: ${s.consequence}` }));
      parts.push(decision);

      if (level.clue_sheet && (s.clue_shown || done)) {
        parts.push(el("div", { className: "clue-sheet" }, el("strong", { text: "📜 ورقة دليل من المرشد" }), el("p", { text: level.clue_sheet })));
      }

      // Justification → digit
      if (done && !s.justified && !level.finished) {
        const why = radioGroup(`just-${level.number}`, level.justification_options, level.justification_question);
        parts.push(el("div", { className: "card" }, why, el("div", { className: "actions" }, button("برّر وافتح الباب", "", () => {
          const [choice] = why.values();
          if (choice === undefined) return;
          ctx.send("action", { action: "justify", payload: { choice } }, (o) =>
            `${o.justification_ok ? `تبرير صحيح (+${o.xp_change} XP).` : "التبرير الأدق موضّح أدناه."} 🔢 حصلت على رقم: ${o.digit}`);
        }))));
      }
      if (s.justified) {
        parts.push(el("div", { className: "card center" },
          el("p", { className: s.justification_ok ? "ok-text" : "warn-text", text: `${s.justification_ok ? "✓" : "✗"} ${level.justification_options[level.correct_justification]}` }),
          el("p", { className: "door-digit", text: `🔢 ${level.digit}` }),
          level.is_boss ? el("p", { className: "big-code", text: `🔐 ${codeDigits(ctx.act).join(" ")}` }) : null));
      }
      body.replaceChildren(...parts);
    },
    finishLabel: (level) => (level.is_boss ? "🔓 افتح باب الخروج" : "🚪 إلى الباب التالي"),
    finishConfirm: (level) => (level.state.justified ? null : "لم تفتح هذا الباب بعد؛ سيُكشف الحل. متابعة؟"),
    summary(level) {
      return [el("p", { text: `القرار الصحيح: ${level.correct.map((i) => level.options[i]).join("، ")}` }),
        level.clue_sheet ? el("p", { className: "muted", text: level.clue_sheet }) : null];
    },
  };
})();
