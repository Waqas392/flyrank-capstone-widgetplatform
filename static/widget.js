/* FlyRank embeddable widget bundle. Served as /assets/widget.<hash>.js with immutable caching. */
(function (global) {
  "use strict";

  var CSS =
    ":host{all:initial}" +
    ".card{box-sizing:border-box;font:14px/1.4 system-ui,sans-serif;color:#1a1a1a;background:#fff;border:1px solid #d9d9e3;border-radius:10px;padding:16px;max-width:380px;box-shadow:0 2px 8px rgba(0,0,0,.06)}" +
    ".popover{position:fixed;right:20px;bottom:20px;z-index:2147483000;box-shadow:0 8px 30px rgba(0,0,0,.2)}" +
    "h3{margin:0 0 4px;font-size:17px}p{margin:0 0 12px;color:#555}" +
    "label{display:block;margin:8px 0 2px;font-weight:600;font-size:13px}" +
    "input[type=text],input[type=email],input[type=tel],textarea{box-sizing:border-box;width:100%;padding:8px;border:1px solid #bbb;border-radius:6px;font:inherit}" +
    "button{margin-top:12px;padding:9px 14px;border:0;border-radius:6px;background:#4f46e5;color:#fff;font:inherit;cursor:pointer}" +
    "button[disabled]{opacity:.6;cursor:default}.close{position:absolute;top:6px;right:10px;margin:0;padding:0 4px;background:none;color:#666;font-size:18px}" +
    ".msg{margin-top:10px;font-size:13px}.err{color:#b00020}.ok{color:#0a7d33}" +
    ".hp{position:absolute;left:-10000px;top:auto;width:1px;height:1px;overflow:hidden}";

  function el(tag, props, text) {
    var n = document.createElement(tag);
    if (props) for (var k in props) n.setAttribute(k, props[k]);
    if (text != null) n.textContent = text; /* textContent only: server data is never parsed as markup */
    return n;
  }

  function uuid() {
    if (global.crypto && global.crypto.randomUUID) return global.crypto.randomUUID();
    return "k" + Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  function render(cfg, opts) {
    var host = el("div", { "data-flyrank-widget": cfg.id });
    var root = host.attachShadow({ mode: "open" });
    root.appendChild(el("style", null, CSS));

    var popover = cfg.display && cfg.display.mode === "popover";
    var card = el("div", { class: "card" + (popover ? " popover" : "") });
    if (popover) {
      var close = el("button", { class: "close", type: "button", "aria-label": "Close" }, "\u00d7");
      close.onclick = function () { host.remove(); };
      card.appendChild(close);
    }
    card.appendChild(el("h3", null, cfg.title));
    if (cfg.description) card.appendChild(el("p", null, cfg.description));

    var form = el("form", { novalidate: "novalidate" });
    var inputs = {};
    cfg.fields.forEach(function (f) {
      var id = "fw-" + cfg.id + "-" + f.name;
      var lab = el("label", { for: id }, f.label + (f.required ? " *" : ""));
      var inp = f.type === "textarea" ? el("textarea", { rows: "4" }) : el("input", { type: f.type === "checkbox" ? "checkbox" : f.type });
      inp.id = id; inp.name = f.name;
      if (f.placeholder) inp.setAttribute("placeholder", f.placeholder);
      if (f.type !== "checkbox") inp.setAttribute("maxlength", String(f.max_length));
      inputs[f.name] = inp;
      form.appendChild(lab); form.appendChild(inp);
    });

    /* Honeypot: invisible to humans, irresistible to form-filling bots. */
    var hpWrap = el("div", { class: "hp", "aria-hidden": "true" });
    var hp = el("input", { type: "text", name: cfg.honeypot_field, tabindex: "-1", autocomplete: "off" });
    hpWrap.appendChild(hp); form.appendChild(hpWrap);

    var btn = el("button", { type: "submit" }, cfg.button_text);
    var msg = el("div", { class: "msg", role: "status" });
    form.appendChild(btn); form.appendChild(msg);
    card.appendChild(form);
    root.appendChild(card);

    var shownAt = performance.now();
    var key = uuid(); /* one Idempotency-Key per form instance: double-clicks/retries store once */
    var sending = false;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (sending) return;
      var data = {};
      cfg.fields.forEach(function (f) {
        var i = inputs[f.name];
        data[f.name] = f.type === "checkbox" ? i.checked : i.value;
      });
      data[cfg.honeypot_field] = hp.value;
      sending = true; btn.disabled = true; msg.className = "msg"; msg.textContent = "Sending\u2026";
      fetch(opts.apiBase + "/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": key },
        body: JSON.stringify({ widget_id: cfg.id, data: data, elapsed_ms: Math.round(performance.now() - shownAt) })
      })
        .then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (body) { return { res: res, body: body }; });
        })
        .then(function (r) {
          if (r.res.ok) {
            form.reset();
            msg.className = "msg ok"; msg.textContent = "Thanks! We got your details.";
            btn.style.display = "none";
            return;
          }
          var m = (r.body && r.body.error && r.body.error.message) || "Something went wrong.";
          var d = r.body && r.body.error && r.body.error.details;
          if (d && d.length) m += " (" + d.map(function (x) { return x.field + ": " + x.problem; }).join("; ") + ")";
          if (r.res.status === 429) m = "Too many attempts - please wait a moment and try again.";
          msg.className = "msg err"; msg.textContent = m;
          sending = false; btn.disabled = false;
        })
        .catch(function () {
          msg.className = "msg err"; msg.textContent = "Network error - please try again.";
          sending = false; btn.disabled = false;
        });
    });

    function place() {
      if (popover) document.body.appendChild(host);
      else opts.anchor.parentNode.insertBefore(host, opts.anchor.nextSibling);
    }
    var delay = (cfg.display && cfg.display.delay_seconds) || 0;
    if (delay > 0) setTimeout(place, delay * 1000); else place();
  }

  function mount(opts) {
    fetch(opts.apiBase + "/widgets/" + encodeURIComponent(opts.id) + "/config") /* simple GET: no preflight, cacheable */
      .then(function (r) { if (!r.ok) throw new Error("config HTTP " + r.status); return r.json(); })
      .then(function (cfg) { render(cfg, opts); })
      .catch(function (e) { console.warn("[flyrank-widget]", e.message); });
  }

  global.FlyRankWidget = { mount: mount };
})(window);
