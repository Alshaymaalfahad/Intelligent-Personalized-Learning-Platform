/* 👥 الظل والظل العكسي */
(() => {
  const { el, button, artifact } = ActivityKit;

  function watch(body, level, ctx) {
    const expert = (ctx.act.mission && ctx.act.mission.expert_name) || "الخبير";
    const steps = el("ol", { className: "expert-steps" }, ...level.visible_steps.map((s) =>
      el("li", {}, el("strong", { text: s.step }), el("div", { className: "muted small", text: s.why }))));
    const parts = [
      el("div", { className: "card" }, el("p", { className: "muted small", text: "🎥 المرحلة الأولى: الظل — شاهد الخبير وتوقّع خطوته" }),
        el("h2", { text: level.title }), el("p", { text: level.situation }), artifact(level.artifact_lines)),
      el("div", { className: "card" }, el("h3", { text: `خطوات ${expert}` }), steps),
    ];
    if (level.current_pause) {
      const p = level.current_pause;
      parts.push(el("div", { className: "card pause-card" },
        el("p", { className: "sub-title", text: `⏸️ نقطة توقف ${p.number} من ${p.of}` }),
        el("h3", { text: `${expert}: «وش تتوقع خطوتي الجاية؟»` }),
        el("div", { className: "solutions" }, ...p.options.map((o, i) => button(o, "btn-secondary step-card", () =>
          ctx.send("action", { action: "predict", payload: { choice: i } }, (out) =>
            out.result === "correct"
              ? `توقّع صحيح! +${out.xp_change} XP 🃏 بطاقة ممارسة ذهبية: «${out.card}»`
              : `الخبير اختار: «${out.expert_step}» — لأن ${out.why}`))))));
    } else {
      parts.push(el("p", { className: "ok-text", text: "شاهدت الحل كاملًا. أنهِ المرحلة لتجرّب بنفسك." }));
    }
    if (level.cards.length) {
      parts.push(el("div", { className: "card" }, el("h3", { text: "🃏 بطاقات الممارسات الذهبية" }),
        el("div", { className: "golden-cards" }, ...level.cards.map((c) => el("div", { className: "golden-card", text: c })))));
    }
    body.replaceChildren(...parts);
  }

  function doMode(body, level, ctx) {
    const intro = el("div", { className: "card" },
      el("p", { className: "muted small", text: level.is_boss ? "👑 الزعيم: موقف جديد، نفّذه بنفسك" : "🔁 الظل العكسي — نفّذ أنت والخبير يراقب" }),
      el("h2", { text: level.title }), el("p", { text: level.situation }), artifact(level.artifact_lines));

    if (level.submitted) {
      const c = level.comparison;
      const LABEL = { match: ["✓ في مكانها", "ok-text"], out_of_order: ["↕ ترتيبها مختلف", "warn-text"], extra: ["✗ خطوة زائدة", "warn-text"] };
      body.replaceChildren(intro, el("div", { className: "card" },
        el("h3", { text: `نسبة التطابق مع الخبير: ${level.match}%` }),
        el("div", { className: "side-by-side" },
          el("div", {}, el("p", { className: "sub-title", text: "خطواتك" }), el("ol", { className: "expert-steps" }, ...c.trainee.map((t) =>
            el("li", {}, el("span", { text: t.text }), el("div", { className: `small ${LABEL[t.status][1]}`, text: LABEL[t.status][0] }))))),
          el("div", {}, el("p", { className: "sub-title", text: "خطوات الخبير" }), el("ol", { className: "expert-steps" }, ...c.expert.map((e) =>
            el("li", { className: e.missed ? "missed" : "" }, el("strong", { text: e.step }), el("div", { className: "muted small", text: e.missed ? `فاتتك — ${e.why}` : e.why }))))))));
      return;
    }

    ctx.state.order = ctx.state.order || [];
    const order = ctx.state.order;
    const mine = el("ol", { className: "order-list" }, ...order.map((poolIndex, pos) => {
      const li = el("li", { className: "order-item" }, el("span", { text: level.pool[poolIndex] }));
      const ctrls = el("span", { className: "order-controls" },
        button("▲", "btn-small btn-secondary", () => { [order[pos - 1], order[pos]] = [order[pos], order[pos - 1]]; ctx.rerender(); }),
        button("▼", "btn-small btn-secondary", () => { [order[pos + 1], order[pos]] = [order[pos], order[pos + 1]]; ctx.rerender(); }),
        button("✕", "btn-small btn-secondary", () => { order.splice(pos, 1); ctx.rerender(); }));
      ctrls.children[0].disabled = pos === 0;
      ctrls.children[1].disabled = pos === order.length - 1;
      li.append(ctrls);
      return li;
    }));
    const pool = el("div", { className: "solutions" }, ...level.pool.map((text, i) => {
      const b = button(`＋ ${text}`, "btn-secondary step-card", () => { order.push(i); ctx.rerender(); });
      b.disabled = order.includes(i);
      return b;
    }));
    const submit = button("📤 قارن مع الخبير", "", () =>
      ctx.send("action", { action: "submit_steps", payload: { order: [...order] } }, (o) =>
        `التطابق مع الخبير ${o.match}% (+${o.xp_change} XP). قارن خطواتك بخطواته أدناه.`));
    submit.disabled = order.length < 2;
    body.replaceChildren(intro,
      el("div", { className: "card" }, el("h3", { text: "بطاقات الخطوات" }), el("p", { className: "hint", text: "اختر الخطوات اللازمة فقط (بعضها فخ)، ثم رتّبها." }), pool),
      el("div", { className: "card" }, el("h3", { text: "خطواتك بالترتيب" }), order.length ? mine : el("p", { className: "muted", text: "لم تختر خطوات بعد." }), el("div", { className: "actions" }, submit)));
  }

  ActivityKit.renderers.shadow = {
    stat: (level) => (level.mode === "watch" ? `🃏 بطاقات: ${level.cards.length}` : `🎯 التطابق: ${level.match ?? "—"}${level.match != null ? "%" : ""}`),
    render: (body, level, ctx) => (level.mode === "watch" ? watch(body, level, ctx) : doMode(body, level, ctx)),
    finishConfirm(level) {
      if (level.mode === "watch") return level.current_pause ? "لم تكمل نقاط التوقف؛ ستُكشف بقية الخطوات. متابعة؟" : null;
      return level.submitted ? null : "لم تسلّم خطواتك بعد. متابعة؟";
    },
  };
})();
