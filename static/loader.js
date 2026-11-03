/* Tiny loader served at /widget.js (short cache). It pulls in the content-hashed bundle (cached forever). */
(function () {
  var s = document.currentScript;
  if (!s || !s.src) return;
  var u = new URL(s.src);
  var id = u.searchParams.get("id");
  if (!id) { console.warn("[flyrank-widget] missing ?id="); return; }
  var b = document.createElement("script");
  b.async = true;
  b.src = u.origin + "/assets/__BUNDLE__";
  b.onload = function () {
    if (window.FlyRankWidget) window.FlyRankWidget.mount({ id: id, apiBase: u.origin, anchor: s });
  };
  document.head.appendChild(b);
})();
