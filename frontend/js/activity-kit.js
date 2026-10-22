/* Shared helpers for the activity renderers (built on App from core.js).
   Renderers register themselves in ActivityKit.renderers[activity_type] = {
     stat(level, act)            → text for the status row
     render(body, level, ctx)    → draws the level into `body`
     summary?(level, act)        → extra elements for the level summary
     finishLabel?(level)         → label of the finish button
     finishConfirm?(level)       → confirmation text (or null) before finishing early
   }
   ctx = { act, state, level(), send(endpoint, body, onOutcome, loadingText), mentor(text), rerender(text?) }
   All AI-generated text is inserted with textContent, never innerHTML. */

window.ActivityKit = (() => {
  const { el, button, api, artifact, svg, bar, chip, t } = App;

  function radioGroup(name, options, title, multi = false) {
    const fs = el("fieldset", { className: "options" }, title ? el("legend", { className: "sub-title", text: title }) : null);
    options.forEach((text, i) => {
      const input = el("input", { type: multi ? "checkbox" : "radio" });
      input.name = name;
      input.value = i;
      fs.append(el("label", { className: "option" }, input, el("span", { className: "letter", text: "ABCDE"[i] || String(i + 1) }), el("span", { className: "text", text })));
    });
    fs.values = () => [...fs.querySelectorAll("input:checked")].map((x) => Number(x.value));
    return fs;
  }

  function card(...children) {
    return el("div", { className: "card" }, ...children);
  }

  function meter(percent, label) {
    return el("div", { className: "meter" }, el("span", { className: "small", text: label }), bar(percent));
  }

  return { el, button, api, artifact, svg, bar, chip, t, radioGroup, card, meter, renderers: {} };
})();
