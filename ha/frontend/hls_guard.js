// Temporary guard for Home Assistant 2026.10.0 (core issue 184775) on the Lenovo Smart Display.
// On that release the HLS playlist request for a UniFi Protect camera never answers. The
// frontend starts HLS and WebRTC side by side for every live camera view and does not cancel
// the HLS request when the view closes, so each live view leaves two requests hanging. A
// browser allows six connections per server, so after three live views nothing else loads
// (camera snapshots stay blank). WebRTC works on this display, so refuse HLS here and let the
// frontend carry on with WebRTC. Only acts on the display; every other browser is untouched.
(() => {
  if (!/mt8167s/i.test(navigator.userAgent) || window.__hlsGuard) return;
  window.__hlsGuard = true;
  const isHls = (u) => /\/api\/hls\//.test(String((u && u.url) || u));
  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    if (isHls(input)) return Promise.reject(new TypeError("HLS disabled on this display (HA 2026.10.0 workaround)"));
    return origFetch.call(this, input, init);
  };
  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    if (isHls(url)) { this.__hlsBlocked = true; return origOpen.call(this, method, "data:text/plain,", ...rest); }
    return origOpen.call(this, method, url, ...rest);
  };
})();
