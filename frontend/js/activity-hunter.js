/* 🕵️ Gap Hunter */
(() => {
  const { el, button, radioGroup, chip, t } = ActivityKit;

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
    node.setAttribute("aria-label", t("hunter.line", { n: i + 1 }));
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
        el("table", { className: "data-table hunt-table" },
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
    const title = el("h3", { text: t("hunter.line", { n: line + (level.artifact_kind === "table" ? 0 : 1) }) });

    if (!e) {
      let category = null;
      const go = button(t("hunter.check"), "", () =>
        ctx.send("mark", { line_index: line, category }, (o) => {
          if (o.result === "false_alarm") {
            ctx.state.selected = null;
            return `${t("hunter.false_alarm", { n: ctx.act.rules.false_alarm })} ${o.why_correct || ""}`;
          }
          ctx.state.selected = o.line_index;
          return o.category_ok ? t("hunter.caught", { xp: o.xp_change }) : t("hunter.caught_other_category", { xp: o.xp_change, category: o.correct_category });
        }), "arrow");
      go.disabled = true;
      const chips = el("div", { className: "chips" }, ...level.categories.map((cat) => {
        const b = el("button", { className: "chip-toggle", type: "button", text: cat, attrs: { "aria-pressed": "false" } });
        b.addEventListener("click", () => {
          category = cat;
          chips.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
          go.disabled = false;
        });
        return b;
      }));
      return el("div", { className: "card" }, el("div", { className: "head-row" }, el("h3", { text: t("hunter.what_kind") }), chip(t("hunter.target", { n: title.textContent }), "muted")),
        chips, el("div", { className: "actions end" }, el("span", { className: "hint", text: t("hunter.xp_hint") }), go));
    }

    if (e.revealed && !e.found) {
      return el("div", { className: "card soft" }, title, el("p", { text: `${t("hunter.missed")}: ${e.correct_category}` }),
        el("p", { text: `${t("hunter.why")}: ${e.explanation}` }), el("p", { text: `${t("hunter.fix")}: ${e.fix}` }));
    }

    const cat = el("p", { className: e.category_ok ? "ok-text" : "warn-text", text: e.category_ok ? `✓ ${t("hunter.category_ok")}: ${e.correct_category}` : `${t("hunter.category_better")}: ${e.correct_category}` });
    if (!e.justified) {
      const why = radioGroup(`why-${line}`, e.explanation_options, t("hunter.why_issue"));
      const fix = radioGroup(`fix-${line}`, e.fix_options, t("hunter.how_fix"));
      const submit = button(t("hunter.confirm"), "", () => {
        const [w] = why.values();
        const [f] = fix.values();
        if (w === undefined || f === undefined) return;
        ctx.send("justify", { line_index: line, explanation: w, fix: f }, (o) => {
          const remaining = ctx.level().total - ctx.level().found;
          const head = o.explanation_ok && o.fix_ok ? t("hunter.justified_ok", { xp: o.xp_change }) : t("hunter.justified_partial", { xp: o.xp_change });
          return `${head} ${remaining ? t("hunter.remaining", { n: remaining }) : t("hunter.all_caught")}`;
        });
      }, "check");
      return el("div", { className: "card" }, title, cat, el("div", { className: "grid grid-2" }, why, fix), el("div", { className: "actions end" }, submit));
    }
    return el("div", { className: "card" }, title, cat,
      el("p", { className: e.explanation_ok ? "ok-text" : "warn-text", text: `${e.explanation_ok ? "✓" : "✗"} ${t("hunter.why")}: ${e.explanation_options[e.correct_explanation]}` }),
      el("p", { className: e.fix_ok ? "ok-text" : "warn-text", text: `${e.fix_ok ? "✓" : "✗"} ${t("hunter.fix")}: ${e.fix_options[e.correct_fix]}` }));
  }

  ActivityKit.renderers.gap_hunter = {
    stat: (level) => `🎯 ${t("hunter.stat", { found: level.found, total: level.total })}`,
    render(body, level, ctx) {
      if (ctx.state.selected === undefined) ctx.state.selected = null;
      body.replaceChildren(
        el("div", { className: "card" },
          el("div", { className: "head-row" }, el("h2", { text: level.artifact_title }), chip(t("hunter.records", { n: level.lines.length - (level.artifact_kind === "table" ? 1 : 0) }), "muted")),
          el("p", { className: "hint", text: t("hunter.click_hint") }), el("div", { className: "artifact" }, artifactView(level, ctx))),
        panel(level, ctx) || "");
    },
    finishConfirm(level) {
      const r = level.total - level.found;
      return r ? t("hunter.finish_confirm", { n: r }) : null;
    },
    summary(level) {
      const missed = level.errors.filter((e) => e.revealed && !e.found);
      if (!missed.length) return [];
      return [el("h2", { text: t("hunter.missed_title") }), el("ul", { className: "missed-list" }, ...missed.map((e) =>
        el("li", {}, el("code", { text: level.lines[e.line_index], dir: level.artifact_kind === "text" ? undefined : "ltr" }),
          el("p", { text: `${e.correct_category} — ${e.explanation}` }), el("p", { className: "muted", text: `${t("hunter.fix")}: ${e.fix}` }))))];
    },
  };
})();
