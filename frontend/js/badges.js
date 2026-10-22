/* Badges & level: every badge (earned or locked), XP, level, streak — all from real activity. */
(() => {
  const { el, svg, nudge, store, shell, bar, chip, t } = App;
  shell("badges");
  document.title = t("badges.title");
  const page = document.getElementById("page");
  const ALL = ["hawk_eye", "zero_false_alarms", "escape_artist", "client_star", "golden_collector", "expert_shadow", "inspiring_teacher", "independent", "boss_slayer", "ready"];
  const ICONS = { hawk_eye: "🦅", zero_false_alarms: "🎯", boss_slayer: "👑", ready: "🏅", escape_artist: "🗝️", independent: "🧭", client_star: "⭐", golden_collector: "🃏", expert_shadow: "🥷", inspiring_teacher: "🎓" };

  (async () => {
    if (!store.get("trainee_id")) {
      return page.replaceChildren(el("div", { className: "card center" }, nudge(80), el("h2", { text: t("badges.no_profile") }),
        el("a", { className: "btn", href: "skills.html", text: t("landing.start") })));
    }
    const p = await App.refreshProgress();
    if (!p) return page.replaceChildren(el("div", { className: "card" }, el("p", { className: "error", text: t("error.generic") })));
    const earned = Object.fromEntries(p.badges.map((b) => [b.id, b.count]));
    const pct = Math.round((100 * p.level_xp) / p.xp_per_level);
    const ring = el("div", { className: "ring" }, el("div", {}, el("small", { text: t("report.current_tier") }), el("strong", { text: t("report.level", { n: p.level }) })));
    ring.style.setProperty("--p", pct);
    page.replaceChildren(
      el("section", { className: "report-hero" },
        el("div", {}, el("span", { className: "chip-tag solid", text: t("badges.eyebrow") }), el("h1", { className: "big-title", text: t("badges.headline") }),
          el("p", { text: t("badges.sub") }),
          el("div", { className: "status-row" }, chip(`🔥 ${t("shell.streak", { n: p.streak_days })}`, "amber"), chip(t("badges.activities", { n: p.activities_completed }), "cyan"),
            chip(t("badges.gaps", { n: p.gaps_passed }), "green"))),
        el("div", { className: "level-card" }, ring, el("div", { className: "bar-row" }, el("span", { text: t("report.to_level", { pct, n: p.level + 1 }) }), el("strong", { text: `${p.level_xp} / ${p.xp_per_level} XP` })), bar(pct))),
      el("div", { className: "grid grid-3" }, ...ALL.map((id) =>
        el("div", { className: `card badge-tile ${earned[id] ? "" : "locked"}` },
          el("div", { className: "medal", text: ICONS[id] }),
          el("h3", { text: t(`badge.${id}.name`) }),
          el("p", { className: "hint", text: t(`badge.${id}.desc`) }),
          earned[id] ? chip(t("badges.earned", { n: earned[id] }), "green", "check") : chip(t("badges.locked"), "muted", "lock")))));
  })();
})();
