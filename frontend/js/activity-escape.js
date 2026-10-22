/* 🔐 Escape Room */
(() => {
  const { el, button, artifact, radioGroup, t } = ActivityKit;

  const codeDigits = (act) => act.levels.map((lv) => (lv.digit !== undefined ? String(lv.digit) : "_"));

  ActivityKit.renderers.escape_room = {
    stat: (level, act) => `🔑 ${t("escape.code")}: ${codeDigits(act).join(" ")}`,
    render(body, level, ctx) {
      const s = level.state;
      const done = s.solved || s.revealed;
      const parts = [
        el("div", { className: "card door" },
          el("h2", { text: `🚪 ${level.title}` }),
          el("p", { text: level.scenario }),
          artifact(level.artifact_lines, level.artifact_kind)),
      ];

      const decision = el("div", { className: "card" }, el("h3", { text: level.question }));
      if (!done) {
        const multi = level.challenge_type === "multi_select";
        const group = radioGroup(`door-${level.number}`, level.options, multi ? t("escape.select_all") : null, multi);
        decision.append(group, el("p", { className: "hint", text: t("escape.tries_left", { n: level.tries_left }) }),
          el("div", { className: "actions end" }, button(t("escape.decide"), "", () => {
            const selected = group.values();
            if (!selected.length) return;
            ctx.send("action", { action: "answer", payload: { selected } }, (o) =>
              o.result === "solved" ? t("escape.solved", { xp: o.xp_change, consequence: o.consequence })
                : o.result === "revealed" ? t("escape.revealed", { consequence: o.consequence })
                  : t("escape.retry", { consequence: o.consequence }));
          }, "arrow")));
      } else {
        decision.append(el("ul", { className: "review-options" }, ...level.options.map((o, i) => {
          const li = el("li", { text: `${level.correct.includes(i) ? "✓ " : ""}${o}` });
          if (level.correct.includes(i)) li.classList.add("correct");
          else if ((s.chosen || []).includes(i)) li.classList.add("wrong");
          return li;
        })));
      }
      if (s.consequence) decision.append(el("p", { className: s.solved ? "ok-text" : "warn-text", text: `${t("escape.result_of_decision")}: ${s.consequence}` }));
      parts.push(decision);

      if (level.clue_sheet && (s.clue_shown || done)) {
        parts.push(el("div", { className: "clue-sheet" }, el("strong", { text: `📜 ${t("escape.clue_sheet")}` }), el("p", { text: level.clue_sheet })));
      }
      if (done && !s.justified && !level.finished) {
        const why = radioGroup(`just-${level.number}`, level.justification_options, level.justification_question);
        parts.push(el("div", { className: "card" }, why, el("div", { className: "actions end" }, button(t("escape.justify_open"), "", () => {
          const [choice] = why.values();
          if (choice === undefined) return;
          ctx.send("action", { action: "justify", payload: { choice } }, (o) =>
            `${o.justification_ok ? t("escape.justify_ok", { xp: o.xp_change }) : t("escape.justify_better")} 🔢 ${t("escape.digit", { d: o.digit })}`);
        }, "door"))));
      }
      if (s.justified) {
        parts.push(el("div", { className: "card center" },
          el("p", { className: s.justification_ok ? "ok-text" : "warn-text", text: `${s.justification_ok ? "✓" : "✗"} ${level.justification_options[level.correct_justification]}` }),
          el("p", { className: "door-digit", text: `🔢 ${level.digit}` }),
          level.is_boss ? el("p", { className: "big-code", text: `🔐 ${codeDigits(ctx.act).join(" ")}` }) : null));
      }
      body.replaceChildren(...parts);
    },
    finishLabel: (level) => t(level.is_boss ? "escape.exit" : "escape.next_door"),
    finishConfirm: (level) => (level.state.justified ? null : t("escape.finish_confirm")),
    summary: (level) => [el("p", { text: `${t("escape.right_decision")}: ${level.correct.map((i) => level.options[i]).join(" · ")}` }),
      level.clue_sheet ? el("p", { className: "muted", text: level.clue_sheet }) : null],
  };
})();
