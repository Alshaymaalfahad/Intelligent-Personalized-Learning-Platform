/* Journey map: the picked skills as stations in the lab's work order. The current
   station is open; the next ones unlock as each is played. Edit any time from the passport. */
(() => {
  const { el, svg, nudge, api, store, shell, chip, activityIcon, loadingView, t } = App;
  shell("journey");
  document.title = t("journey.title");
  const page = document.getElementById("page");
  const journeyId = new URLSearchParams(location.search).get("id") || store.get("journey_id");
  const DECISION_KIND = { passed: "green", partial: "amber", persistent: "amber" };

  const activityUrl = (s) => `activity.html?${new URLSearchParams({ assessment: journeyId, competency: s.skill_id, type: s.activity_type })}`;

  function station(s, i, stages) {
    const stage = stages.find((x) => x.id === s.stage);
    let action;
    if (s.state === "current") {
      action = el("a", { className: "btn", href: activityUrl(s) }, el("span", { text: s.started ? t("journey.continue") : t("journey.start") }), svg("arrow", 18));
    } else if (s.state === "done") {
      action = el("a", { className: "btn btn-secondary btn-small", href: activityUrl(s) }, svg("refresh", 16), el("span", { text: t("journey.revisit") }));
    } else {
      action = el("span", { className: "hint lock-note" }, svg("lock", 14), el("span", { text: ` ${t("journey.unlocks_after", { n: i })}` }));
    }
    return el("li", { className: `map-station ${s.state}` },
      el("span", { className: "map-dot", attrs: { "aria-hidden": "true" } }, s.state === "done" ? svg("check", 20) : el("span", { text: String(i + 1) })),
      el("div", { className: "card map-card" },
        el("div", { className: "status-row" },
          chip(stage ? stage.name : "", "muted", stage && stage.icon),
          chip(t("skills.min_short", { n: s.minutes }), "muted", "clock"),
          s.level ? chip(t(`level.${s.level}`), "cyan") : null,
          s.state === "done" ? chip(t(`progress.${s.decision}`), DECISION_KIND[s.decision] || "green", "check") : null),
        el("h3", { text: s.name }),
        el("p", { className: "muted small", text: s.can_do }),
        el("div", { className: "map-foot" },
          el("span", { className: "small activity-tag" }, activityIcon(s.activity_type, 18), el("span", { text: t(`activity.${s.activity_type}.name`) })),
          action)));
  }

  (async () => {
    if (!journeyId) return (location.href = "skills.html");
    page.replaceChildren(loadingView(t("journey.loading")));
    try {
      const [j, cat] = await Promise.all([api("GET", `/api/journeys/${encodeURIComponent(journeyId)}`), api("GET", "/api/skills")]);
      store.set("journey_id", j.journey_id);
      store.set("assessment_id", j.journey_id);
      store.set("trainee_id", j.trainee_id);
      const total = j.stations.length;
      const allDone = j.complete;
      page.replaceChildren(...[
        el("section", { className: "mission-banner journey-head" },
          el("div", {},
            el("span", { className: "chip-tag solid", text: t("journey.eyebrow") }),
            el("h1", { className: "big-title", text: allDone ? t("journey.all_done") : t("journey.headline") }),
            el("p", { text: t("journey.sub") }),
            el("div", { className: "status-row" },
              chip(t("journey.progress", { done: j.done, total }), "green", "check"),
              chip(t("skills.about_hours", { h: Math.round(j.total_minutes / 30) / 2 }), "white", "clock"),
              chip(t("journey.your_id", { id: j.trainee_id }), "white", "user"))),
          allDone ? el("a", { className: "btn", href: "skills.html" }, svg("plus", 18), el("span", { text: t("journey.next_round") }))
            : el("span", { className: "chip-tag white" }, svg("lock", 14), el("span", { text: t("journey.locked_note") }))),
        el("ol", { className: "journey-map" }, ...j.stations.map((s, i) => station(s, i, cat.stages))),
        j.later.length ? el("section", { className: "card" },
          el("h2", {}, svg("hourglass", 20), el("span", { text: ` ${t("skills.later")}` })),
          el("p", { className: "muted small", text: t("journey.later_sub") }),
          el("div", { className: "status-row" }, ...j.later.map((l) => chip(l.name, "muted"))),
          ) : null,
        allDone ? el("div", { className: "card nudge-say" }, nudge(56), el("div", {}, el("strong", { text: t("coach.name") }), el("p", { text: t("journey.done_tip") }))) : null,
      ].filter(Boolean));
    } catch (e) {
      page.replaceChildren(el("div", { className: "card center" }, nudge(64), el("p", { className: "error", text: e.status === 404 ? t("journey.not_found") : e.message }),
        el("a", { className: "btn", href: "skills.html", text: t("journey.pick_skills") })));
    }
  })();
})();
