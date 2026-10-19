/* Shared helpers for the activity page and the per-activity renderers.
   Renderers register themselves in ActivityKit.renderers[activity_type] = {
     stat(level, act)            → text for the game bar
     render(body, level, ctx)    → draws the level into `body`
     summary?(level, act)        → extra elements for the level summary
     finishLabel?(level)         → label of the finish button
     finishConfirm?(level)       → confirmation text (or null) before finishing early
   }
   All AI-generated text is inserted with textContent, never innerHTML. */

window.ActivityKit = (() => {
  function el(tag, opts = {}, ...children) {
    const node = document.createElement(tag);
    if (opts.className) node.className = opts.className;
    if (opts.text !== undefined && opts.text !== null) node.textContent = opts.text;
    if (opts.dir) node.dir = opts.dir;
    if (opts.type) node.type = opts.type;
    for (const c of children) if (c !== null && c !== undefined && c !== false) node.append(c);
    return node;
  }

  function button(text, className, onClick) {
    const b = el("button", { className: `btn ${className || ""}`.trim(), text, type: "button" });
    if (onClick) b.addEventListener("click", onClick);
    return b;
  }

  async function api(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try {
      data = await res.json();
    } catch {
      /* empty body */
    }
    if (!res.ok) {
      const err = new Error((data && typeof data.detail === "string" && data.detail) || "حدث خطأ غير متوقع.");
      err.status = res.status;
      throw err;
    }
    return data;
  }

  /* Artifact: table ("a | b" cells, first line header), code/log/config (monospace), or text lines. */
  function artifact(lines, kind) {
    if (!lines || !lines.length || kind === "none") return null;
    const looksTable = kind === "table" || (!kind && lines[0].includes("|"));
    if (looksTable) {
      const rows = lines.map((l) => l.split("|").map((c) => c.trim()));
      return el(
        "div",
        { className: "table-wrap" },
        el("table", { className: "results hunt-table" },
          el("thead", {}, el("tr", {}, ...rows[0].map((c) => el("th", { text: c })))),
          el("tbody", {}, ...rows.slice(1).map((r) => el("tr", {}, ...r.map((c) => el("td", { text: c })))))),
      );
    }
    if (kind === "text") return el("ul", { className: "plain-list" }, ...lines.map((l) => el("li", { text: l })));
    return el("pre", { className: "code", dir: "ltr" }, el("code", { text: lines.join("\n") }));
  }

  function radioGroup(name, options, title, multi = false) {
    const fs = el("fieldset", { className: "options" }, title ? el("legend", { className: "sub-title", text: title }) : null);
    options.forEach((text, i) => {
      const input = el("input", { type: multi ? "checkbox" : "radio" });
      input.name = name;
      input.value = i;
      fs.append(el("label", { className: "option" }, input, el("span", { text })));
    });
    fs.values = () => [...fs.querySelectorAll("input:checked")].map((x) => Number(x.value));
    return fs;
  }

  function card(...children) {
    return el("div", { className: "card" }, ...children);
  }

  function meter(percent, label) {
    const fill = el("div", { className: "bar-fill" });
    fill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    return el("div", { className: "meter" }, el("span", { className: "small", text: label }), el("div", { className: "bar" }, fill));
  }

  return { el, button, api, artifact, radioGroup, card, meter, renderers: {} };
})();
