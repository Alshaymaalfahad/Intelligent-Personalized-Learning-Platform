/* 👥 Shadow & Reverse Shadow */
(() => {
  const { el, button, artifact, t } = ActivityKit;

  function watch(body, level, ctx) {
    const expert = (ctx.act.mission && ctx.act.mission.expert_name) || t("shadow.expert");
    const parts = [
      el("div", { className: "card" }, el("span", { className: "eyebrow", text: `🎥 ${t("shadow.watch_label")}` }),
        el("h2", { text: level.title }), el("p", { text: level.situation }), artifact(level.artifact_lines)),
      el("div", { className: "card" }, el("h3", { text: t("shadow.steps_of", { name: expert }) }),
        el("ol", { className: "expert-steps" }, ...level.visible_steps.map((s) => el("li", {}, el("strong", { text: App.plain(s.step) }), el("div", { className: "hint", text: s.why }))))),
    ];
    if (level.current_pause) {
      const p = level.current_pause;
      parts.push(el("div", { className: "card pause-card" },
        el("span", { className: "eyebrow", text: `⏸️ ${t("shadow.pause", { n: p.number, of: p.of })}` }),
        el("h3", { text: `${expert}: “${t("shadow.predict")}”` }),
        el("div", { className: "solutions" }, ...p.options.map((o, i) => button(App.plain(o), "btn-secondary step-card", () =>
          ctx.send("action", { action: "predict", payload: { choice: i } }, (out) =>
            out.result === "correct" ? t("shadow.correct", { xp: out.xp_change, card: out.card }) : t("shadow.wrong", { step: out.expert_step, why: out.why })))))));
    } else {
      parts.push(el("p", { className: "ok-text", text: t("shadow.watched") }));
    }
    if (level.cards.length) {
      parts.push(el("div", { className: "card" }, el("h3", { text: `🃏 ${t("shadow.cards")}` }),
        el("div", { className: "golden-cards" }, ...level.cards.map((c) => el("div", { className: "golden-card", text: c })))));
    }
    body.replaceChildren(...parts);
  }

  function doMode(body, level, ctx) {
    const intro = el("div", { className: "card" },
      el("span", { className: "eyebrow", text: level.is_boss ? `👑 ${t("shadow.boss_label")}` : `🔁 ${t("shadow.do_label")}` }),
      el("h2", { text: level.title }), el("p", { text: level.situation }), artifact(level.artifact_lines));

    if (level.submitted) {
      const c = level.comparison;
      const LABEL = { match: ["shadow.in_place", "ok-text"], out_of_order: ["shadow.out_of_order", "warn-text"], extra: ["shadow.extra", "warn-text"] };
      body.replaceChildren(intro, el("div", { className: "card" },
        el("h3", { text: t("shadow.match", { n: level.match }) }),
        el("div", { className: "side-by-side" },
          el("div", {}, el("p", { className: "sub-title", text: t("shadow.your_steps") }), el("ol", { className: "expert-steps" }, ...c.trainee.map((x) =>
            el("li", {}, el("span", { text: App.plain(x.text) }), el("div", { className: `small ${LABEL[x.status][1]}`, text: t(LABEL[x.status][0]) }))))),
          el("div", {}, el("p", { className: "sub-title", text: t("shadow.expert_steps") }), el("ol", { className: "expert-steps" }, ...c.expert.map((e) =>
            el("li", { className: e.missed ? "missed" : "" }, el("strong", { text: App.plain(e.step) }), el("div", { className: "hint", text: e.missed ? `${t("shadow.missed")} — ${e.why}` : e.why }))))))));
      return;
    }

    ctx.state.order = ctx.state.order || [];
    const order = ctx.state.order;
    const mine = el("ol", { className: "order-list" }, ...order.map((poolIndex, pos) => {
      const up = button("▲", "btn-small btn-secondary", () => { [order[pos - 1], order[pos]] = [order[pos], order[pos - 1]]; ctx.rerender(); });
      const down = button("▼", "btn-small btn-secondary", () => { [order[pos + 1], order[pos]] = [order[pos], order[pos + 1]]; ctx.rerender(); });
      const remove = button("✕", "btn-small btn-secondary", () => { order.splice(pos, 1); ctx.rerender(); });
      up.disabled = pos === 0;
      down.disabled = pos === order.length - 1;
      return el("li", { className: "order-item" }, el("span", { text: App.plain(level.pool[poolIndex]) }), el("span", { className: "order-controls" }, up, down, remove));
    }));
    const pool = el("div", { className: "solutions" }, ...level.pool.map((text, i) => {
      const b = button(`＋ ${App.plain(text)}`, "btn-secondary step-card", () => { order.push(i); ctx.rerender(); });
      b.disabled = order.includes(i);
      return b;
    }));
    const submit = button(t("shadow.compare"), "", () =>
      ctx.send("action", { action: "submit_steps", payload: { order: [...order] } }, (o) => t("shadow.compared", { n: o.match, xp: o.xp_change })), "arrow");
    submit.disabled = order.length < 2;
    body.replaceChildren(intro,
      el("div", { className: "card" }, el("h3", { text: t("shadow.step_cards") }), el("p", { className: "hint", text: t("shadow.pick_hint") }), pool),
      el("div", { className: "card" }, el("h3", { text: t("shadow.your_order") }), order.length ? mine : el("p", { className: "muted", text: t("shadow.none_yet") }), el("div", { className: "actions end" }, submit)));
  }

  ActivityKit.renderers.shadow = {
    stat: (level) => (level.mode === "watch" ? `🃏 ${t("shadow.cards_stat", { n: level.cards.length })}` : `🎯 ${t("shadow.match_stat")}: ${level.match != null ? `${level.match}%` : "—"}`),
    render: (body, level, ctx) => (level.mode === "watch" ? watch(body, level, ctx) : doMode(body, level, ctx)),
    finishConfirm(level) {
      if (level.mode === "watch") return level.current_pause ? t("shadow.finish_watch_confirm") : null;
      return level.submitted ? null : t("shadow.finish_do_confirm");
    },
  };
})();
