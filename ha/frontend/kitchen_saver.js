// Screen saver for the Lenovo Smart Display: a full-screen photo slideshow with a small clock.
// Registered as a dashboard resource by ha/screen_saver.py and used by the "saver" view of
// the smart-display dashboard. Home Assistant decides when it is shown and when the screen
// goes dark (the "Smart Display - Screen saver" automation); this file only draws.
//
// Two parts:
//  1. <kitchen-saver-card>: crossfades the pictures listed in /local/kitchen_display/photos.json
//     (kept up to date by ha/album_sync.py). The clock moves to another corner with every
//     picture so it cannot burn in either. A touch presses the activity button, which makes
//     the automation give the screen back.
//  2. On the display only (user agent check): any touch on any view presses the same button,
//     at most once every 20 seconds, so the automation knows someone is using the screen.
(() => {
  if (window.__kitchenSaver) return;
  window.__kitchenSaver = true;
  const ACTIVITY = "input_button.kitchen_display_activity";
  const hassNow = () => { const el = document.querySelector("home-assistant"); return el && el.hass; };
  const press = (entity) => {
    const hass = hassNow();
    if (hass) hass.callService("input_button", "press", { entity_id: entity }).catch(() => {});
  };

  if (/mt8167s/i.test(navigator.userAgent)) {
    let last = 0;
    document.addEventListener("pointerdown", () => {
      if (Date.now() - last < 20000) return;
      last = Date.now();
      press(ACTIVITY);
    }, { capture: true, passive: true });
  }

  const CORNERS = [["4%", "", "", "5%"], ["4%", "5%", "", ""], ["", "5%", "6%", ""], ["", "", "6%", "5%"]]; // top right bottom left

  class KitchenSaverCard extends HTMLElement {
    setConfig(config) {
      this.c = Object.assign({ photos: "/local/kitchen_display/photos.json", interval: 20, fade: 2,
        clock: true, activity: ACTIVITY, pause_entity: null, device: null, home: "/smart-display/home" }, config);
    }
    set hass(hass) {
      this._hass = hass;
      const st = this.c.pause_entity && hass.states[this.c.pause_entity];
      const paused = !!st && (st.state === "on" || Number(st.state) === 0);   // a switch that is on, or a brightness of 0
      if (paused !== this._paused) { this._paused = paused; if (this.isConnected) this._schedule(paused ? null : 1000); }
    }
    getCardSize() { return 10; }

    connectedCallback() {
      const root = this.shadowRoot || this.attachShadow({ mode: "open" });
      root.innerHTML = `<style>
        .wrap { position: fixed; inset: 0; z-index: 9999; background: #000; overflow: hidden; touch-action: none; }
        img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: 0;
              transition: opacity ${this.c.fade}s ease-in-out; will-change: opacity; }
        img.tall { object-fit: contain; }
        img.show { opacity: 1; }
        .clock { position: absolute; font: 300 46px/1 Roboto, sans-serif; color: rgba(255,255,255,.88);
                 text-shadow: 0 1px 6px rgba(0,0,0,.85), 0 0 2px rgba(0,0,0,.6); letter-spacing: 1px; }
      </style><div class="wrap"><img><img><div class="clock"></div></div>`;
      this._imgs = [...root.querySelectorAll("img")];
      this._clock = root.querySelector(".clock");
      this._front = 0; this._i = 0; this._corner = 0; this._list = [];
      this._clock.style.display = this.c.clock ? "" : "none";
      root.querySelector(".wrap").addEventListener("pointerdown", () => this._touched());
      this._tick();
      this._clockTimer = setInterval(() => this._tick(), 10000);
      this._listTimer = setInterval(() => this._load(), 3600000);
      this._load().then(() => this._next());
    }
    disconnectedCallback() {
      clearInterval(this._clockTimer); clearInterval(this._listTimer); clearTimeout(this._timer); clearTimeout(this._leave);
    }

    _tick() {
      const d = new Date(), h = d.getHours() % 12 || 12;
      this._clock.textContent = `${h}:${String(d.getMinutes()).padStart(2, "0")}`;
    }
    _moveClock() {
      this._corner = (this._corner + 1 + Math.floor(Math.random() * 3)) % 4;
      const [top, right, bottom, left] = CORNERS[this._corner];
      Object.assign(this._clock.style, { top, right, bottom, left });
    }
    async _load() {
      try {
        const r = await fetch(`${this.c.photos}?t=${Date.now()}`, { cache: "no-store" });
        const list = ((await r.json()).photos || []).slice();
        for (let i = list.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [list[i], list[j]] = [list[j], list[i]]; }
        this._list = list; this._i = 0;
      } catch (e) { /* keep the list we have */ }
    }
    _schedule(ms) {
      clearTimeout(this._timer);
      if (ms !== null) this._timer = setTimeout(() => this._next(), ms);
    }
    _next() {
      if (this._paused) return;
      this._moveClock();
      const again = () => this._schedule(this.c.interval * 1000);
      if (!this._list.length) { this._load().then(again); return; }
      const photo = this._list[this._i++ % this._list.length];
      const back = this._imgs[1 - this._front], front = this._imgs[this._front];
      const pre = new Image();
      pre.onload = () => {
        back.src = photo.src;
        back.classList.toggle("tall", photo.h > photo.w);
        back.classList.add("show"); front.classList.remove("show");
        this._front = 1 - this._front;
        again();
      };
      pre.onerror = again;
      pre.src = photo.src;
    }
    _touched() {
      press(this.c.activity);
      // If the automation does not answer (it was reloaded mid-run, Home Assistant is busy),
      // leave anyway: through View Assist so it knows where the display is, else on our own.
      clearTimeout(this._leave);
      this._leave = setTimeout(() => {
        if (!this.isConnected) return;
        const local = () => {
          history.pushState(null, "", this.c.home);
          window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
        };
        const hass = hassNow();
        if (!hass || !this.c.device) return local();
        hass.callService("view_assist", "navigate", { device: this.c.device, path: this.c.home }).catch(local);
      }, 4000);
    }
  }
  customElements.define("kitchen-saver-card", KitchenSaverCard);
})();
