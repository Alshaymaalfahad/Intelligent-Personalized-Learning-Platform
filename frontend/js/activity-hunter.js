/* 🕵️ صياد الفجوات */
(() => {
  const { el, button, radioGroup } = ActivityKit;

  const foundError = (level, line) => level.errors.find((e) => e.line_index === line || e.related_lines.includes(line));

  function lineState(level, i) {
    if (level.false_alarm_lines.includes(i)) return "false";
    const e = foundError(level, i);
    if (e) return e.revealed && !e.found ? "revealed" : "found";
    return "";
  }

  function lineNode(level, i, node, ctx) {
    const state = lineState(level, i);
    node.classList.add("hunt-line");
    if (state) node.classList.add(`is-${state}`);
    if (i === ctx.state.selected) node.classList.add("is-selected");
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", `السطر ${i + 1}`);
    const pick = () => {
      if (state === "false" || level.finished) return;
      ctx.state.selected = i;
      ctx.rerender();
    };
    node.addEventListener("click", pick);
    node.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pick();
      }
    });
    return node;
  }

  function artifactView(level, ctx) {
    if (level.artifact_kind === "table") {
      const rows = level.lines.map((l) => l.split("|").map((c) => c.trim()));
      return el("div", { className: "table-wrap" },
        el("table", { className: "results hunt-table" },
          el("thead", {}, el("tr", {}, ...rows[0].map((c) => el("th", { text: c })))),
          el("tbody", {}, ...rows.slice(1).map((cells, k) => lineNode(level, k + 1, el("tr", {}, ...cells.map((c) => el("td", { text: c }))), ctx)))));
    }
    const isCode = level.artifact_kind !== "text";
    const list = el("ol", { className: `hunt-lines ${isCode ? "code-lines" : ""}`, dir: isCode ? "ltr" : undefined });
    level.lines.forEach((l, i) => list.append(lineNode(level, i, el("li", { text: l }), ctx)));
    return list;
  }

  function panel(level, ctx) {
    const line = ctx.state.selected;
    if (line === null || line === undefined) return null;
    const e = foundError(level, line);
    const title = el("h3", { text: `السطر ${line + (level.artifact_kind === "table" ? 0 : 1)}` });

    if (!e) {
      let category = null;
      const go = button("🎯 اصطياد", "", () =>
        ctx.send("mark", { line_index: line, category }, (o) => {
          if (o.result === "false_alarm") {
            ctx.state.selected = null;
            return `هذا السطر سليم (−${ctx.act.rules.false_alarm} XP). ${o.why_correct || "دقق أكثر قبل الضغط."}`;
          }
          ctx.state.selected = o.line_index;
          return o.category_ok
            ? `صيد موفق! +${o.xp_change} XP. الآن: لماذا هو خطأ، وما الإصلاح؟`
            : `اصطدت الخطأ (+${o.xp_change} XP)، لكن تصنيفه الأدق «${o.correct_category}». أكمل التبرير.`;
        }),
      );
      go.disabled = true;
      const chips = el("div", { className: "chips" }, ...level.categories.map((cat) => {
        const b = button(cat, "btn-small btn-secondary", () => {
          category = cat;
          chips.querySelectorAll("button").forEach((x) => x.classList.toggle("selected", x === b));
          go.disabled = false;
        });
        return b;
      }));
      return el("div", { className: "card" }, title, el("p", { text: "ما نوع الخطأ في هذا السطر؟" }), chips, el("div", { className: "actions" }, go));
    }

    if (e.revealed && !e.found) {
      return el("div", { className: "card" }, title, el("p", { text: `خطأ لم يُصطد: ${e.correct_category}` }),
        el("p", { text: `لماذا: ${e.explanation}` }), el("p", { text: `الإصلاح: ${e.fix}` }));
    }

    const cat = el("p", { className: e.category_ok ? "ok-text" : "warn-text", text: e.category_ok ? `✓ التصنيف صحيح: ${e.correct_category}` : `التصنيف الأدق: ${e.correct_category}` });
    if (!e.justified) {
      const why = radioGroup(`why-${line}`, e.explanation_options, "لماذا هو خطأ؟");
      const fix = radioGroup(`fix-${line}`, e.fix_options, "ما الإصلاح المناسب؟");
      const submit = button("تأكيد", "", () => {
        const [w] = why.values();
        const [f] = fix.values();
        if (w === undefined || f === undefined) return;
        ctx.send("justify", { line_index: line, explanation: w, fix: f }, (o) => {
          const remaining = ctx.level().total - ctx.level().found;
          const head = o.explanation_ok && o.fix_ok ? `ممتاز! تبرير وإصلاح صحيحان (+${o.xp_change} XP).` : `+${o.xp_change} XP. راجع الإجابة الصحيحة: السبب والإصلاح مكتوبان أدناه.`;
          return head + (remaining ? ` باقي ${remaining}.` : " اصطدت كل الأخطاء! أنهِ المرحلة.");
        });
      });
      return el("div", { className: "card" }, title, cat, why, fix, el("div", { className: "actions" }, submit));
    }
    return el("div", { className: "card" }, title, cat,
      el("p", { className: e.explanation_ok ? "ok-text" : "warn-text", text: `${e.explanation_ok ? "✓" : "✗"} السبب: ${e.explanation_options[e.correct_explanation]}` }),
      el("p", { className: e.fix_ok ? "ok-text" : "warn-text", text: `${e.fix_ok ? "✓" : "✗"} الإصلاح: ${e.fix_options[e.correct_fix]}` }));
  }

  ActivityKit.renderers.gap_hunter = {
    stat: (level) => `🎯 تم اصطياد ${level.found} من ${level.total}`,
    render(body, level, ctx) {
      if (ctx.state.selected === undefined) ctx.state.selected = null;
      body.replaceChildren(
        el("div", { className: "card" }, el("h2", { text: level.artifact_title }),
          el("p", { className: "hint", text: "اضغط على السطر الذي تشك أن فيه خطأ." }), el("div", { className: "artifact" }, artifactView(level, ctx))),
        panel(level, ctx) || "",
      );
    },
    finishConfirm(level) {
      const r = level.total - level.found;
      return r ? `باقي ${r} ${r === 1 ? "خطأ لم تصطده وسيُكشف" : "أخطاء لم تصطدها وستُكشف"} لك مع شرحها. هل تريد إنهاء المرحلة؟` : null;
    },
    summary(level) {
      const missed = level.errors.filter((e) => e.revealed && !e.found);
      if (!missed.length) return [];
      return [el("h2", { text: "أخطاء لم تصطدها" }), el("ul", { className: "missed-list" }, ...missed.map((e) =>
        el("li", {}, el("code", { text: level.lines[e.line_index], dir: level.artifact_kind === "text" ? undefined : "ltr" }),
          el("p", { text: `${e.correct_category} — ${e.explanation}` }), el("p", { className: "muted", text: `الإصلاح: ${e.fix}` }))))];
    },
  };
})();
