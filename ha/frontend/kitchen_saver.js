// Screen saver for the Lenovo Smart Display. Registered as a dashboard resource by
// ha/screen_saver.py and used by the "saver" view of the smart-display dashboard. Home
// Assistant decides when it is shown (the "Smart Display - Screen saver" automation) and
// whether the room is dark (dark_entity); this file only draws.
//
// Two parts:
//  1. <kitchen-saver-card>, with two faces:
//     - room bright: crossfades the pictures listed in /local/kitchen_display/photos.json
//       (kept up to date by ha/album_sync.py) with a clock over them. The clock moves to
//       another corner with every picture so it cannot burn in either.
//     - room dark: no pictures, a dim clock on black that shifts to a new spot every minute.
//     A touch presses the activity button, which makes the automation give the screen back.
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

  const CORNERS = [["4%", "", "", "4%"], ["4%", "4%", "", ""], ["", "4%", "5%", ""], ["", "", "5%", "4%"]]; // top right bottom left
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const BLANK = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";

  class KitchenSaverCard extends HTMLElement {
    setConfig(config) {
      this.c = Object.assign({ photos: "/local/kitchen_display/photos.json", interval: 20, fade: 2,
        clock: true, activity: ACTIVITY, dark_entity: null, device: null, home: "/smart-display/home" }, config);
    }
    set hass(hass) {
      this._hass = hass;
      const st = this.c.dark_entity && hass.states[this.c.dark_entity];
      const dark = !!st && st.state === "on";
      if (dark !== this._dark) { this._dark = dark; if (this._wrap) this._face(); }
    }
    getCardSize() { return 10; }

    connectedCallback() {
      const root = this.shadowRoot || this.attachShadow({ mode: "open" });
      root.innerHTML = `<style>
        .wrap { position: fixed; inset: 0; z-index: 9999; background: #000; overflow: hidden; touch-action: none;
                font-family: Roboto, sans-serif; }
        img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: 0;
              transition: opacity ${this.c.fade}s ease-in-out; will-change: opacity; }
        img.tall { object-fit: contain; }
        img.show { opacity: 1; }
        .dark img { opacity: 0 !important; }
        /* Clock over a photo: white with a soft dark halo, so it reads on any picture. */
        .clock { position: absolute; color: #fff; padding: 14px 26px; border-radius: 24px;
                 background: radial-gradient(closest-side, rgba(0,0,0,.4), rgba(0,0,0,0));
                 text-shadow: 0 2px 10px rgba(0,0,0,.9), 0 0 3px rgba(0,0,0,.7); }
        .time { font-weight: 300; font-size: 76px; line-height: 1; letter-spacing: 1px; }
        .date { font-weight: 400; font-size: 22px; margin-top: 6px; opacity: .92; }
        /* Clock in a dark room: big, dim, no halo, placed by translate so it can drift. */
        .dark .clock { top: 50% !important; left: 50% !important; right: auto !important; bottom: auto !important;
                       background: none; text-shadow: none; color: #6b6f76; text-align: center;
                       transition: transform 4s ease-in-out; }
        .dark .time { font-size: 150px; font-weight: 200; }
        .dark .date { font-size: 28px; color: #4b4f55; }
      </style><div class="wrap"><img src="${BLANK}" alt=""><img src="${BLANK}" alt=""><div class="clock"><div class="time"></div><div class="date"></div></div></div>`;
      this._wrap = root.querySelector(".wrap");
      this._imgs = [...root.querySelectorAll("img")];
      this._clock = root.querySelector(".clock");
      this._time = root.querySelector(".time");
      this._date = root.querySelector(".date");
      this._front = 0; this._i = 0; this._corner = 0; this._list = []; this._minute = -1;
      this._clock.style.display = this.c.clock ? "" : "none";
      this._wrap.addEventListener("pointerdown", () => this._touched());
      this._tick();
      this._clockTimer = setInterval(() => this._tick(), 5000);
      this._listTimer = setInterval(() => this._load(), 3600000);
      this._load().then(() => this._face());
    }
    disconnectedCallback() {
      clearInterval(this._clockTimer); clearInterval(this._listTimer); clearTimeout(this._timer); clearTimeout(this._leave);
      this._wrap = null;
    }

    _tick() {
      const d = new Date(), h = d.getHours() % 12 || 12;
      this._time.textContent = `${h}:${String(d.getMinutes()).padStart(2, "0")}`;
      this._date.textContent = `${DAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`;
      if (this._dark && d.getMinutes() !== this._minute) { this._minute = d.getMinutes(); this._drift(); }
    }
    // Dark face: a new spot each minute, anywhere the clock still fits on the screen.
    _drift() {
      const x = Math.round((Math.random() - 0.5) * 2 * 26), y = Math.round((Math.random() - 0.5) * 2 * 28);
      this._clock.style.transform = `translate(-50%, -50%) translate(${x}vw, ${y}vh)`;
    }
    _moveClock() {
      this._corner = (this._corner + 1 + Math.floor(Math.random() * 3)) % 4;
      const [top, right, bottom, left] = CORNERS[this._corner];
      Object.assign(this._clock.style, { top, right, bottom, left });
    }
    // Switch between the two faces.
    _face() {
      clearTimeout(this._timer);
      this._wrap.classList.toggle("dark", !!this._dark);
      if (this._dark) { this._minute = -1; this._tick(); }
      else { this._clock.style.transform = ""; this._next(); }
    }
    async _load() {
      try {
        const r = await fetch(`${this.c.photos}?t=${Date.now()}`, { cache: "no-store" });
        const list = ((await r.json()).photos || []).slice();
        for (let i = list.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [list[i], list[j]] = [list[j], list[i]]; }
        this._list = list; this._i = 0;
      } catch (e) { /* keep the list we have */ }
    }
    _next() {
      clearTimeout(this._timer);
      if (this._dark || !this._wrap) return;
      this._moveClock();
      const again = () => { clearTimeout(this._timer); this._timer = setTimeout(() => this._next(), this.c.interval * 1000); };
      if (!this._list.length) { this._load().then(again); return; }
      const photo = this._list[this._i++ % this._list.length];
      const back = this._imgs[1 - this._front], front = this._imgs[this._front];
      const pre = new Image();
      pre.onload = () => {
        if (this._dark || !this._wrap) return;
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
