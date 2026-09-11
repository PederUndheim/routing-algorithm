/* The review page.
 *
 * One Leaflet map per model, built once and kept. Paging to another tour
 * swaps each map's corridor overlay and route line rather than tearing the
 * maps down - rebuilding four maps per keystroke drops every cached WMTS
 * tile and makes the whole thing feel like a slideshow.
 *
 * The models come from /api/session, so the panel count follows the config
 * and nothing here knows how many there are meant to be.
 */

const KARTVERKET = "https://cache.kartverket.no/v1/wmts/1.0.0";
const NVE = "https://gis3.nve.no/arcgis/rest/services/wmts";

const TILES = {
  base: `${KARTVERKET}/topo/default/webmercator/{z}/{y}/{x}.png`,
  slope: `${NVE}/Bratthet_2024/MapServer/WMTS/tile/1.0.0/wmts_Bratthet_2024/default/GoogleMapsCompatible/{z}/{y}/{x}.png`,
  runout: `${NVE}/Bratthet_med_utlop_2024/MapServer/WMTS/tile/1.0.0/wmts_Bratthet_med_utlop_2024/default/GoogleMapsCompatible/{z}/{y}/{x}.png`,
};

const OPACITY = { slope: 0.3, runout: 0.3 };

// The corridor sits on top of the slope ramp, and the slope underneath it is
// half of what you are judging - whether the band leans into ground NVE has
// already coloured red. Opaque enough to read its own shape, transparent
// enough to see through.
const CORRIDOR_OPACITY = 0.5;

// The track overlay already carries density in its own alpha channel (see
// render.TRACK_ALPHA_FLOOR), so this only scales the whole layer.
const TRACK_OPACITY = 0.55;

// Pixels of travel between pointerdown and click that still count as a click
// rather than a drag. A deliberate click moves one or two; a pan moves tens.
const DRAG_SLOP = 5;

const state = {
  session: null,
  tours: [],
  tour: null,
  panels: [],       // one per model, in config order
  shift: 0,
  syncing: false,   // guards the pan/zoom echo between locked maps
};

const $ = (id) => document.getElementById(id);

/* --- helpers ---------------------------------------------------------- */

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || `${path} -> ${response.status}`);
  return body;
}

let toastTimer = null;
function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 4000);
}

const metres = (v) => (v == null ? "-" : `${(v / 1000).toFixed(2)} km`);
const num = (v, digits = 1) => (v == null ? "-" : Number(v).toFixed(digits));

/* --- panels ----------------------------------------------------------- */

function buildPanels(models) {
  const host = $("panels");
  host.innerHTML = "";
  state.panels = models.map((model, index) => {
    const panel = document.createElement("article");
    panel.className = "panel";
    panel.innerHTML = `
      <div class="panel-head">
        <span class="key">${index + 1}</span>
        <span class="panel-label"></span>
        <span class="spacer"></span>
        <span class="chip"></span>
      </div>
      <div class="panel-map"></div>
      <div class="panel-foot"></div>`;
    host.appendChild(panel);

    const map = L.map(panel.querySelector(".panel-map"), {
      zoomControl: index === 0,
      attributionControl: index === models.length - 1,
    }).setView([65, 13], 5);

    L.tileLayer(TILES.base, { maxZoom: 18, attribution: "© Kartverket" }).addTo(map);
    const slope = L.tileLayer(TILES.slope, { maxZoom: 18, opacity: OPACITY.slope });
    const runout = L.tileLayer(TILES.runout, { maxZoom: 18, opacity: OPACITY.runout });
    if ($("show-slope").checked) slope.addTo(map);
    if ($("show-runout").checked) runout.addTo(map);

    const entry = {
      model: model.name, node: panel, map, slope, runout,
      corridor: null, route: null, tracks: null,
    };

    map.on("move zoom", () => syncFrom(entry));

    // Dragging the map to look around ends in a click event on the panel, so
    // a click on its own cannot mean "pick this one" - that is what made the
    // review pick a corridor whenever you panned. Anything that travelled
    // more than a few pixels between press and release was a drag.
    let pressed = null;
    panel.addEventListener("pointerdown", (event) => {
      pressed = { x: event.clientX, y: event.clientY };
    });
    panel.addEventListener("click", (event) => {
      // The zoom buttons and attribution links live inside the panel; a
      // click on those is not a verdict either.
      if (event.target.closest(".leaflet-control")) return;
      const moved = pressed
        ? Math.hypot(event.clientX - pressed.x, event.clientY - pressed.y)
        : 0;
      pressed = null;
      if (moved > DRAG_SLOP) return;
      choose(model.name);
    });

    return entry;
  });
}

function syncFrom(source) {
  if (state.syncing || !$("lock-maps").checked) return;
  state.syncing = true;
  const centre = source.map.getCenter();
  const zoom = source.map.getZoom();
  for (const other of state.panels) {
    if (other === source) continue;
    other.map.setView(centre, zoom, { animate: false });
  }
  state.syncing = false;
}

/* --- rendering one tour ----------------------------------------------- */

function renderTour(tour) {
  state.tour = tour;
  $("tour-name").textContent = tour.name;
  $("tour-fid").textContent = `fid ${tour.fid} · ${tour.position + 1} of ${tour.total}`;

  const byModel = new Map(tour.panels.map((p) => [p.model, p]));
  let fitted = null;

  for (const entry of state.panels) {
    const data = byModel.get(entry.model);
    const label = entry.node.querySelector(".panel-label");
    const chip = entry.node.querySelector(".chip");
    const foot = entry.node.querySelector(".panel-foot");

    if (entry.corridor) { entry.map.removeLayer(entry.corridor); entry.corridor = null; }
    if (entry.route) { entry.map.removeLayer(entry.route); entry.route = null; }
    if (entry.tracks) { entry.map.removeLayer(entry.tracks); entry.tracks = null; }

    if (!data) {
      entry.node.classList.add("missing");
      label.textContent = entry.model;
      chip.textContent = "no route";
      chip.className = "chip";
      foot.innerHTML = `<span class="muted">this model produced nothing for this tour</span>`;
      continue;
    }

    entry.node.classList.remove("missing");
    label.textContent = data.label;
    chip.textContent = data.colour;
    chip.className = `chip ${data.colour}`;

    if (data.png && data.bounds) {
      const b = data.bounds;
      entry.corridor = L.imageOverlay(
        `${data.png}?v=${tour.fid}`,
        [[b.south, b.west], [b.north, b.east]],
        { opacity: CORRIDOR_OPACITY, interactive: false },
      ).addTo(entry.map);
    }

    if (data.route && $("show-route").checked) {
      const latlngs = data.route.coordinates.map(([lng, lat]) => [lat, lng]);
      entry.route = L.polyline(latlngs, {
        color: "#ffffff", weight: 2, opacity: 0.9, interactive: false,
      }).addTo(entry.map);
      if (!fitted) fitted = entry.route.getBounds();
    } else if (data.bounds && !fitted) {
      const b = data.bounds;
      fitted = L.latLngBounds([b.south, b.west], [b.north, b.east]);
    }

    const m = data.metrics || {};
    foot.innerHTML = `
      <span>len <b>${metres(m.length_m)}</b></span>
      <span>cost <b>${num(m.cost_opt, 0)}</b></span>
      <span>exp <b>${num(m.exp_score)}</b></span>
      <span>/km <b>${num(m.exp_per_km, 2)}</b></span>`;
  }

  // One fit, then copied verbatim to the others.
  //
  // Every map used to run its own fitBounds on the same bounds, which looks
  // equivalent and is not: fitBounds picks the largest INTEGER zoom that fits
  // the bounds in that particular container, so two panels a few pixels apart
  // in width can land a whole zoom level apart. Fitting once and copying the
  // resulting centre and zoom makes identical views structural rather than
  // something that happens to hold while the panels happen to match.
  if (fitted && fitted.isValid()) {
    state.syncing = true;
    const first = state.panels[0];
    for (const entry of state.panels) entry.map.invalidateSize({ animate: false });
    first.map.fitBounds(fitted, { padding: [18, 18], animate: false });
    const centre = first.map.getCenter();
    const zoom = first.map.getZoom();
    for (const entry of state.panels) {
      if (entry === first) continue;
      entry.map.setView(centre, zoom, { animate: false });
    }
    state.syncing = false;
  }

  state.shift = tour.verdict ? tour.verdict.shift : 0;
  showVerdict(tour.verdict);

  showFix(tour.needs_fix);
  markListCurrent();
  applyTracks();
}

/* Which panel is picked, and what that made the class.
 *
 * Separate from renderTour because picking no longer reloads the tour: a
 * re-render refits every map to the route, which would throw away the pan
 * and zoom you were using to make the decision in the first place.
 */
function showVerdict(verdict) {
  setShiftButtons(state.shift);
  for (const entry of state.panels) {
    entry.node.classList.toggle("chosen", !!verdict && verdict.model === entry.model);
  }
  $("note").value = verdict ? (verdict.note || "") : "";
  $("verdict-state").textContent = verdict
    ? `picked ${verdict.model} · ${verdict.colour}${verdict.shift ? ` (shifted ${verdict.shift > 0 ? "up" : "down"} from ${verdict.colour_computed})` : ""}`
    : "not reviewed";
  updateShiftHint();
}

/* The GPS tracks, fetched only when the layer is on.
 *
 * Building the overlay warps a national raster, so a reviewer who never
 * turns this on never pays for one. The answer is cached server-side, both
 * the picture and the fact that a tour has no tracks near it at all.
 */
async function applyTracks() {
  const tour = state.tour;
  const wanted = $("show-tracks").checked;
  const label = $("tracks-state");

  for (const entry of state.panels) {
    if (entry.tracks) { entry.map.removeLayer(entry.tracks); entry.tracks = null; }
  }
  if (!tour || !wanted) { label.textContent = ""; return; }

  label.textContent = "…";
  // Paging faster than the warp completes would otherwise drop one tour's
  // tracks onto the next one's maps.
  const token = tour.fid;
  let data;
  try {
    data = await api(`/tracks/${tour.fid}.json`);
  } catch (problem) {
    label.textContent = "(failed)";
    toast(problem.message);
    return;
  }
  if (!state.tour || state.tour.fid !== token || !$("show-tracks").checked) return;

  if (data.empty || !data.bounds) {
    label.textContent = "(none here)";
    return;
  }
  label.textContent = "";

  const b = data.bounds;
  for (const entry of state.panels) {
    entry.tracks = L.imageOverlay(
      `${data.png}?v=${token}`,
      [[b.south, b.west], [b.north, b.east]],
      { opacity: TRACK_OPACITY, interactive: false, zIndex: 450 },
    ).addTo(entry.map);
    // Tracks go over the corridor - the question is whether the band follows
    // a line people actually took - but the route itself goes over both, or
    // a 2 px white line vanishes under the magenta wash.
    if (entry.route) entry.route.bringToFront();
  }
}

/* Set the class shift, and re-save if it changes one already recorded.
 *
 * Without the re-save, moving the shift after picking would leave the class
 * on screen and the class on disk disagreeing, with nothing to say which
 * one the export would use.
 */
function setShift(value) {
  state.shift = value;
  setShiftButtons(value);
  updateShiftHint();
  const verdict = state.tour && state.tour.verdict;
  if (verdict && verdict.shift !== value) choose(verdict.model);
}

function setShiftButtons(shift) {
  for (const button of $("shift").querySelectorAll("button")) {
    button.classList.toggle("on", Number(button.dataset.shift) === shift);
  }
}

function updateShiftHint() {
  const tour = state.tour;
  if (!tour || !tour.preview) { $("shift-hint").textContent = ""; return; }
  // Which colour the shift would produce, shown for the panel already
  // chosen, or the first one if nothing is picked yet.
  const model = (tour.verdict && tour.verdict.model) || (tour.panels[0] && tour.panels[0].model);
  const preview = model && tour.preview[model];
  $("shift-hint").textContent = preview ? `-> ${preview[String(state.shift)]}` : "";
}

/* --- actions ---------------------------------------------------------- */

async function load(fid) {
  try {
    renderTour(await api(`/api/tour/${fid}`));
  } catch (problem) {
    toast(problem.message);
  }
}

async function choose(model) {
  const tour = state.tour;
  if (!tour) return;
  const panel = tour.panels.find((p) => p.model === model);
  if (!panel) return;

  try {
    const result = await api("/api/verdict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fid: tour.fid, model, shift: state.shift, note: $("note").value.trim(),
      }),
    });
    // Stay on the tour. Advancing on a pick meant a stray click while
    // panning both recorded a verdict and moved you off the tour before you
    // saw it happen - so the pick was wrong and the tour it belonged to was
    // already gone. Moving on is now always something you ask for: the
    // arrows, the buttons, or Enter for the next unreviewed one.
    state.tour.verdict = result.verdict;
    showVerdict(result.verdict);
    await refreshProgress(result.reviewed);
    await refreshList();
  } catch (problem) {
    toast(problem.message);
  }
}

/* The "fix tour data" flag.
 *
 * Saved on its own, not with the verdict: it does not advance the tour and
 * picking a corridor does not touch it. The note is only enabled while the
 * box is ticked, so an unticked box cannot carry an orphaned reason.
 */
function showFix(entry) {
  const on = !!entry;
  $("needs-fix").checked = on;
  $("fix-note").disabled = !on;
  $("fix-note").value = on ? (entry.note || "") : "";
  document.querySelector(".fix-group").classList.toggle("on", on);
}

async function saveFix() {
  const tour = state.tour;
  if (!tour) return;
  const on = $("needs-fix").checked;
  $("fix-note").disabled = !on;
  document.querySelector(".fix-group").classList.toggle("on", on);
  try {
    const result = await api("/api/flag", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fid: tour.fid, on, note: $("fix-note").value.trim() }),
    });
    if (state.tour) state.tour.needs_fix = result.needs_fix;
    await refreshList();
  } catch (problem) {
    toast(problem.message);
  }
}

async function clearVerdict() {
  const tour = state.tour;
  if (!tour) return;
  try {
    const result = await api("/api/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fid: tour.fid }),
    });
    await refreshProgress(result.reviewed);
    await refreshList();
    load(tour.fid);
  } catch (problem) {
    toast(problem.message);
  }
}

async function refreshProgress(reviewed) {
  const total = state.session.total;
  if (reviewed == null) {
    const session = await api("/api/session");
    state.session = session;
    reviewed = session.reviewed;
  }
  state.session.reviewed = reviewed;
  $("progress-fill").style.width = `${total ? (reviewed / total) * 100 : 0}%`;
  $("progress-text").textContent = `${reviewed} / ${total} reviewed`;
}

/* --- tour list -------------------------------------------------------- */

async function refreshList() {
  state.tours = await api("/api/tours");
  drawList();
}

function drawList() {
  const scope = $("list-scope").value;
  const needle = $("list-filter").value.trim().toLowerCase();
  const body = $("list-body");
  body.innerHTML = "";

  for (const tour of state.tours) {
    if (scope === "todo" && tour.model) continue;
    if (scope === "done" && !tour.model) continue;
    if (scope === "shifted" && !tour.shift) continue;
    if (scope === "fix" && !tour.needs_fix) continue;
    if (needle && !`${tour.fid} ${tour.name}`.toLowerCase().includes(needle)) continue;

    const row = document.createElement("li");
    row.dataset.fid = String(tour.fid);
    row.innerHTML = `
      <span class="dot ${tour.colour || ""}"></span>
      <span class="li-fid">${tour.fid}</span>
      <span class="li-name">${tour.name}</span>
      <span class="li-model">${tour.model || ""}${tour.shift ? (tour.shift > 0 ? " ↑" : " ↓") : ""}</span>
      <span class="flag">${tour.needs_fix ? "⚑" : ""}</span>`;
    row.addEventListener("click", () => load(tour.fid));
    body.appendChild(row);
  }
  markListCurrent();
}

function markListCurrent() {
  const fid = state.tour && String(state.tour.fid);
  for (const row of $("list-body").children) {
    row.classList.toggle("current", row.dataset.fid === fid);
  }
}

function setList(open) {
  $("tour-list").hidden = !open;
  // The list is a layout column, so showing it narrows every panel. Leaflet
  // caches container size and would go on drawing at the old width - tiles
  // land offset and the corridor overlay with them. Next frame, so the new
  // widths have been laid out before anything measures them.
  requestAnimationFrame(() => {
    for (const panel of state.panels) panel.map.invalidateSize({ animate: false });
  });
}

/* --- wiring ----------------------------------------------------------- */

function overlayToggles() {
  $("show-slope").addEventListener("change", (event) => {
    for (const p of state.panels) {
      event.target.checked ? p.slope.addTo(p.map) : p.map.removeLayer(p.slope);
    }
  });
  $("show-runout").addEventListener("change", (event) => {
    for (const p of state.panels) {
      event.target.checked ? p.runout.addTo(p.map) : p.map.removeLayer(p.runout);
    }
  });
  $("show-route").addEventListener("change", () => {
    if (state.tour) renderTour(state.tour);
  });
  $("show-tracks").addEventListener("change", applyTracks);
}

function keyboard() {
  document.addEventListener("keydown", (event) => {
    if (event.target.tagName === "INPUT" || event.target.tagName === "SELECT") {
      if (event.key === "Escape") event.target.blur();
      return;
    }
    const tour = state.tour;

    if (event.key >= "1" && event.key <= "9") {
      const panel = state.panels[Number(event.key) - 1];
      if (panel) choose(panel.model);
      return;
    }

    switch (event.key.toLowerCase()) {
      case "arrowleft":
        if (tour && tour.prev != null) load(tour.prev);
        break;
      case "arrowright":
        if (tour && tour.next != null) load(tour.next);
        break;
      case "enter":
        $("skip").click();
        break;
      case "u":
        setShift(1);
        break;
      case "s":
        setShift(0);
        break;
      case "d":
        setShift(-1);
        break;
      case "l":
        $("toggle-list").click();
        break;
      case "f":
        $("needs-fix").checked = !$("needs-fix").checked;
        saveFix();
        break;
      case "backspace":
        event.preventDefault();
        clearVerdict();
        break;
      default:
        break;
    }
  });
}

async function main() {
  try {
    state.session = await api("/api/session");
  } catch (problem) {
    $("panels").innerHTML = `<p class="empty">${problem.message}</p>`;
    return;
  }

  $("round").textContent = `round ${state.session.round}`;
  if (state.session.note) $("round").title = state.session.note;
  $("classes").innerHTML = state.session.classes
    .map((c) => `<span class="chip ${c.colour}">${c.colour} ≥ ${c.from}</span>`)
    .join("");

  buildPanels(state.session.models);
  overlayToggles();
  keyboard();

  // Resizing the window changes every panel's width. Leaflet caches container
  // size, so without this the maps go on drawing at the old one and drift out
  // of agreement with each other. Debounced - a drag fires this continuously.
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      for (const panel of state.panels) panel.map.invalidateSize({ animate: false });
    }, 150);
  });

  for (const button of $("shift").querySelectorAll("button")) {
    button.addEventListener("click", () => setShift(Number(button.dataset.shift)));
  }

  $("prev").addEventListener("click", () => {
    if (state.tour && state.tour.prev != null) load(state.tour.prev);
  });
  $("next").addEventListener("click", () => {
    if (state.tour && state.tour.next != null) load(state.tour.next);
  });
  $("skip").addEventListener("click", () => {
    const todo = state.tours.find((t) => !t.model);
    if (todo) load(todo.fid);
    else toast("every tour has a verdict");
  });
  $("clear").addEventListener("click", clearVerdict);

  // The note used to be captured only at the moment of the pick, which was
  // survivable when picking advanced you and so had to be typed first. Now
  // that it does not, the natural order is pick then explain - so an edited
  // note re-saves the verdict it belongs to. Same model, same shift, so the
  // store treats it as an amendment rather than a change of mind.
  $("note").addEventListener("blur", () => {
    const verdict = state.tour && state.tour.verdict;
    if (verdict && $("note").value.trim() !== (verdict.note || "")) {
      choose(verdict.model);
    }
  });
  $("note").addEventListener("keydown", (event) => {
    if (event.key === "Enter") event.target.blur();
  });
  $("needs-fix").addEventListener("change", saveFix);
  // On blur rather than on every keystroke - one write per edit, not per
  // character, and the store rewrites the whole file each time.
  $("fix-note").addEventListener("blur", () => {
    if ($("needs-fix").checked) saveFix();
  });
  $("fix-note").addEventListener("keydown", (event) => {
    if (event.key === "Enter") event.target.blur();
  });

  $("toggle-list").addEventListener("click", () => {
    setList($("tour-list").hidden);
  });
  $("close-list").addEventListener("click", () => setList(false));
  $("list-filter").addEventListener("input", drawList);
  $("list-scope").addEventListener("change", drawList);

  await refreshProgress(state.session.reviewed);
  await refreshList();

  // Open on the first tour with no verdict, so reopening the page resumes
  // where the last session stopped rather than at fid 1.
  const todo = state.tours.find((t) => !t.model);
  load(todo ? todo.fid : (state.tours[0] && state.tours[0].fid));
}

main();
