/* The review page.
 *
 * One Leaflet map per model, built once and kept. Paging to another tour
 * swaps each map's corridor overlay and route line rather than tearing the
 * maps down - rebuilding four maps per keystroke drops every cached WMTS
 * tile and makes the whole thing feel like a slideshow.
 *
 * The models come from /api/session, so the panel count follows the config
 * and nothing here knows how many there are meant to be.
 *
 * They arrive grouped. A group is a bench of panels - "main" is the set the
 * review opens on, and any other is a second bench built for a subset of the
 * tours, which the switch in the header swaps the whole screen to. Only one
 * bench is on screen at a time, and each keeps its own maps once built: a
 * switch is a show/hide plus an invalidateSize, not a rebuild, so switching
 * back and forth does not drop every cached WMTS tile.
 *
 * While a non-main bench is up, the arrows and Enter move within ITS tours
 * rather than through all 817 - stepping off the end of a 27-tour set into
 * three empty maps is not a thing anybody wants to do twice.
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

const MAIN_GROUP = "main";

const state = {
  session: null,
  tours: [],
  tour: null,
  group: MAIN_GROUP,
  benches: {},      // group name -> its panel entries, built on first use
  panels: [],       // the active bench: one entry per model, in config order
  // The class the reviewer has asked for, or null for "whatever the model
  // you pick computed". Absolute, not a shift: two models can compute
  // different classes for one tour, so the same wanted class is a different
  // shift per panel - and which panel it is is not known until the pick. The
  // store still records the shift; see choose().
  colour: null,
  syncing: false,   // guards the pan/zoom echo between locked maps
};

const groupSpec = (name) =>
  (state.session.groups || []).find((g) => g.name === name) || null;

/* The tours the active bench can show, in fid order. `main` is all of them;
 * a group built for a subset is only the subset, which is what the arrows,
 * Enter and the greyed switch all read. */
const inGroup = (tour, group) =>
  group === MAIN_GROUP || (tour.groups || []).includes(group);

/* Every panel of every bench built so far. For the things that must not go
 * stale while a bench is hidden - the overlay toggles and the resize. */
const allPanels = () => Object.values(state.benches).flat();

const $ = (id) => document.getElementById(id);

/* --- helpers ---------------------------------------------------------- */

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || `${path} -> ${response.status}`);
  return body;
}

let toastTimer = null;
/* `kind` is "info" unless something actually failed. Defaulting to info
 * rather than error because almost every message here is a statement about
 * where you are, not a fault - and the handful that are faults all come from
 * a catch block, which is a place you remember to say so. */
function toast(message, kind = "info") {
  const node = $("toast");
  node.textContent = message;
  node.className = kind === "error" ? "error" : "";
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 4000);
}

const metres = (v) => (v == null ? "-" : `${(v / 1000).toFixed(2)} km`);
const num = (v, digits = 1) => (v == null ? "-" : Number(v).toFixed(digits));

/* --- panels ----------------------------------------------------------- */

/* One bench of panels for one group, appended to #panels and returned.
 *
 * Kept after it is built, hidden rather than destroyed when another group is
 * on screen. Leaflet caches container size, so a hidden bench measures zero
 * and has to be told to look again on the way back - see setGroup.
 */
function buildPanels(models, group) {
  // The "loading" placeholder the page ships with. Benches are appended
  // rather than assigned over, so it has to go explicitly or it sits in the
  // grid cell under every one of them.
  const placeholder = $("panels").querySelector(".empty");
  if (placeholder) placeholder.remove();

  const bench = document.createElement("div");
  bench.className = "bench";
  bench.dataset.group = group;
  $("panels").appendChild(bench);

  return models.map((model, index) => {
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
    bench.appendChild(panel);

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

/* --- switching between groups ----------------------------------------- */

/* Put a group's bench on screen, building it the first time.
 *
 * Everything downstream reads state.panels, so pointing that at the new
 * bench is the whole switch - renderTour, the number keys, the overlay
 * toggles and the pan/zoom lock all follow without knowing a group exists.
 */
function setGroup(group) {
  const spec = groupSpec(group);
  if (!spec) return;
  if (!state.benches[group]) {
    state.benches[group] = buildPanels(spec.models, group);
  }
  state.group = group;

  for (const bench of $("panels").querySelectorAll(".bench")) {
    bench.hidden = bench.dataset.group !== group;
  }
  state.panels = state.benches[group];
  drawGroupSwitch();

  // The bench was display:none until a moment ago, so every map in it still
  // believes its container is zero-sized. Next frame, once the new widths
  // have been laid out. renderTour refits from there.
  requestAnimationFrame(() => {
    for (const entry of state.panels) entry.map.invalidateSize({ animate: false });
    if (state.tour) renderTour(state.tour);
  });
}

/* The switch itself: one button per group, the ones with nothing for this
 * tour greyed rather than hidden. Greyed, because a button that comes and
 * goes as you page is harder to aim at than one that is simply off - and
 * "this tour has no such model" is itself worth seeing. */
function drawGroupSwitch() {
  const groups = (state.session && state.session.groups) || [];
  const host = $("groups");
  host.hidden = groups.length < 2;
  if (host.hidden) return;

  const tour = state.tours.find((t) => state.tour && t.fid === state.tour.fid);
  host.innerHTML = "";
  for (const spec of groups) {
    const button = document.createElement("button");
    button.textContent = spec.label;
    button.className = spec.name === state.group ? "group-button on" : "group-button";
    const available = !tour || inGroup(tour, spec.name);
    button.disabled = !available;
    button.title = available
      ? `Show the ${spec.label} models - ${spec.tours} tours (G cycles)`
      : `No ${spec.label} models for this tour`;
    button.addEventListener("click", () => setGroup(spec.name));
    host.appendChild(button);
  }
}

/* G, and the fallback when paging leaves a group behind.
 *
 * Only groups that have something for the current tour are cycled through,
 * so G can never land the screen on a bench of empty maps. */
function cycleGroup() {
  const tour = state.tours.find((t) => state.tour && t.fid === state.tour.fid);
  const usable = (state.session.groups || [])
    .filter((spec) => !tour || inGroup(tour, spec.name));
  if (usable.length < 2) {
    toast("no other model set for this tour");
    return;
  }
  const at = usable.findIndex((spec) => spec.name === state.group);
  setGroup(usable[(at + 1) % usable.length].name);
}

/* Paging within the active group.
 *
 * The server's prev/next walk all 817 tours, which is right for main and
 * wrong for a group built for 27 of them: the arrows would leave the set
 * after one press. Inside a group the step is to the next tour that group
 * actually has, so the arrows walk the subset and stop at its ends.
 */
function step(direction) {
  const tour = state.tour;
  if (!tour) return;
  if (state.group === MAIN_GROUP) {
    const fid = direction < 0 ? tour.prev : tour.next;
    if (fid != null) load(fid);
    return;
  }
  const at = state.tours.findIndex((t) => t.fid === tour.fid);
  if (at < 0) return;
  for (let i = at + direction; i >= 0 && i < state.tours.length; i += direction) {
    if (inGroup(state.tours[i], state.group)) {
      load(state.tours[i].fid);
      return;
    }
  }
  toast(`${groupSpec(state.group).label}: no more tours this way`);
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

  // Only a verdict that actually disagreed with classify() carries an
  // explicit class forward. An unshifted one left the class alone, so the
  // picker stays on "follow the computed one" - otherwise picking a second
  // model would silently force it the first model's class.
  state.colour = (tour.verdict && tour.verdict.shift) ? tour.verdict.colour : null;
  showVerdict(tour.verdict);

  showFix(tour.needs_fix);
  markListCurrent();
  drawGroupSwitch();
  applyTracks();
}

/* Which panel is picked, and what that made the class.
 *
 * Separate from renderTour because picking no longer reloads the tour: a
 * re-render refits every map to the route, which would throw away the pan
 * and zoom you were using to make the decision in the first place.
 */
function showVerdict(verdict) {
  drawClassButtons();
  for (const entry of state.panels) {
    entry.node.classList.toggle("chosen", !!verdict && verdict.model === entry.model);
  }
  $("note").value = verdict ? (verdict.note || "") : "";
  $("verdict-state").textContent = verdict
    ? `picked ${verdict.model} · ${verdict.colour}${verdict.shift ? ` (shifted ${verdict.shift > 0 ? "up" : "down"} from ${verdict.colour_computed})` : ""}`
    : "not reviewed";
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
    toast(problem.message, "error");
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

/* One button per class, in the ladder's order, each wearing its own colour.
 *
 * Built from session.ladder rather than written into the HTML, so the
 * classes stay config.EXPOSURE_CLASSES' business: add one there and a button
 * appears, with no colour named anywhere in the front end.
 */
function buildClassButtons() {
  const host = $("class-pick");
  host.innerHTML = "";
  for (const colour of state.session.ladder) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `class-button ${colour}`;
    button.dataset.colour = colour;
    button.textContent = colour;
    button.addEventListener("click", () => setClass(colour));
    host.appendChild(button);
  }
}

/* The panel whose computed class the picker is read against.
 *
 * The chosen model if it is on screen, else the first panel of the bench
 * that is. ON SCREEN, not first in the config: in a non-main group the
 * chosen model is often in the other bench, and marking a class computed
 * against a panel nobody is looking at is worse than marking none.
 */
function referencePanel() {
  const tour = state.tour;
  if (!tour) return null;
  const visible = state.panels.map((entry) => entry.model);
  const chosen = tour.verdict && tour.verdict.model;
  if (chosen && visible.includes(chosen)) {
    return tour.panels.find((panel) => panel.model === chosen) || null;
  }
  return tour.panels.find((panel) => visible.includes(panel.model)) || null;
}

/* The class on screen: what was asked for, or what the reference computed. */
function currentClass() {
  if (state.colour) return state.colour;
  const panel = referencePanel();
  return panel ? panel.colour : null;
}

/* Choose a class outright, and re-save if it changes one already recorded.
 *
 * Any class, from any class - the point of the colour buttons. The old
 * control only stepped one rung and could not say "this green corridor is
 * actually black"; now that is one click, and the store still records it as
 * the shift from what classify() said, so the disagreement remains the
 * thing being measured.
 *
 * Without the re-save, changing the class after picking would leave the
 * class on screen and the class on disk disagreeing, with nothing to say
 * which one the export would use.
 */
function setClass(colour) {
  state.colour = colour;
  drawClassButtons();
  const verdict = state.tour && state.tour.verdict;
  if (verdict && verdict.colour !== colour) choose(verdict.model);
}

/* Move `delta` rungs along the ladder from wherever the picker is now,
 * stopping at either end. What U and D do. */
function stepClass(delta) {
  const ladder = state.session.ladder;
  const at = ladder.indexOf(currentClass());
  if (at < 0) return;
  setClass(ladder[Math.max(0, Math.min(ladder.length - 1, at + delta))]);
}

/* Back to whatever classify() said about the reference panel. What S does. */
function resetClass() {
  state.colour = null;
  drawClassButtons();
  const verdict = state.tour && state.tour.verdict;
  if (verdict && verdict.shift) choose(verdict.model);
}

function drawClassButtons() {
  const wanted = currentClass();
  const panel = referencePanel();
  const computed = panel ? panel.colour : null;
  for (const button of $("class-pick").querySelectorAll("button")) {
    button.classList.toggle("on", button.dataset.colour === wanted);
    button.classList.toggle("computed", button.dataset.colour === computed);
    button.title = button.dataset.colour === computed
      ? `${button.dataset.colour} - what classify() said`
      : `Record this corridor as ${button.dataset.colour}`;
  }
  const ladder = state.session.ladder;
  if (!computed || !wanted || wanted === computed) {
    $("shift-hint").textContent = computed ? "as computed" : "";
    return;
  }
  const shift = ladder.indexOf(wanted) - ladder.indexOf(computed);
  $("shift-hint").textContent =
    `${computed} -> ${wanted} (${shift > 0 ? "+" : ""}${shift})`;
}

/* --- actions ---------------------------------------------------------- */

async function load(fid) {
  try {
    const tour = await api(`/api/tour/${fid}`);
    // Reached from the list, or from a link, rather than by stepping - so
    // it can be a tour the active group was never built for. Falling back
    // beats three panels saying "no route" three different ways.
    if (state.group !== MAIN_GROUP && !(tour.groups || []).includes(state.group)) {
      const spec = groupSpec(state.group);
      state.tour = tour;
      toast(`fid ${tour.fid} has no ${spec.label} models - back to main`);
      setGroup(MAIN_GROUP);
      return;
    }
    renderTour(tour);
  } catch (problem) {
    toast(problem.message, "error");
  }
}

async function choose(model) {
  const tour = state.tour;
  if (!tour) return;
  const panel = tour.panels.find((p) => p.model === model);
  if (!panel) return;

  // The store keeps a shift, and a shift is relative to what classify() said
  // about THIS model's corridor. Two panels can compute different classes for
  // one tour, so the same wanted class is a different shift depending on
  // which one you pick - which is why it is worked out here, at the pick,
  // and not when the class was chosen. No explicit class means no shift:
  // take whatever this model computed.
  const ladder = state.session.ladder;
  const from = ladder.indexOf(panel.colour);
  const to = state.colour ? ladder.indexOf(state.colour) : -1;
  const shift = (from >= 0 && to >= 0) ? to - from : 0;

  try {
    const result = await api("/api/verdict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fid: tour.fid, model, shift, note: $("note").value.trim(),
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
    toast(problem.message, "error");
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
    toast(problem.message, "error");
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
    toast(problem.message, "error");
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

/* The next tour with no verdict AFTER this one, wrapping once.
 *
 * After, not the first in the list - and that distinction is the whole
 * function. Scanning from the top returns the tour you are already standing
 * on whenever it is the earliest unreviewed one, so the button did nothing,
 * looked broken, and was most obviously broken exactly when you had just
 * arrived at the first gap and wanted to move past it.
 *
 * Restricted to the active group, so inside a 27-tour bench it walks those
 * 27 - the same rule the arrows follow.
 */
function nextUnreviewed() {
  const tours = state.tours.filter((t) => inGroup(t, state.group));
  if (!tours.length) return null;
  const at = state.tour ? tours.findIndex((t) => t.fid === state.tour.fid) : -1;
  for (let step = 1; step <= tours.length; step += 1) {
    const candidate = tours[(at + step + tours.length) % tours.length];
    if (!candidate.model) return candidate.fid;
  }
  return null;
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
    // "group:<name>" - the tours one non-main bench was built for. The way
    // to walk a 27-tour set without hunting for its fids in a list of 817.
    if (scope.startsWith("group:") && !inGroup(tour, scope.slice(6))) continue;
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
  // Every bench, not just the one on screen. A hidden bench that missed a
  // toggle comes back showing the layers you turned off two tours ago.
  $("show-slope").addEventListener("change", (event) => {
    for (const p of allPanels()) {
      event.target.checked ? p.slope.addTo(p.map) : p.map.removeLayer(p.slope);
    }
  });
  $("show-runout").addEventListener("change", (event) => {
    for (const p of allPanels()) {
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

    if (event.key >= "1" && event.key <= "9") {
      const panel = state.panels[Number(event.key) - 1];
      if (panel) choose(panel.model);
      return;
    }

    switch (event.key.toLowerCase()) {
      case "arrowleft":
        step(-1);
        break;
      case "arrowright":
        step(1);
        break;
      case "enter":
        $("skip").click();
        break;
      case "u":
        stepClass(1);
        break;
      case "s":
        resetClass();
        break;
      case "d":
        stepClass(-1);
        break;
      case "g":
        cycleGroup();
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

  // The main bench, and a scope per extra group so its tours can be walked
  // as a list as well as with the arrows.
  const extra = (state.session.groups || []).filter((g) => g.name !== MAIN_GROUP);
  for (const spec of extra) {
    const option = document.createElement("option");
    option.value = `group:${spec.name}`;
    option.textContent = `${spec.label} (${spec.tours})`;
    $("list-scope").appendChild(option);
  }
  buildClassButtons();
  setGroup(MAIN_GROUP);
  overlayToggles();
  keyboard();

  // Resizing the window changes every panel's width. Leaflet caches container
  // size, so without this the maps go on drawing at the old one and drift out
  // of agreement with each other. Debounced - a drag fires this continuously.
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      for (const panel of allPanels()) panel.map.invalidateSize({ animate: false });
    }, 150);
  });

  $("prev").addEventListener("click", () => step(-1));
  $("next").addEventListener("click", () => step(1));
  $("skip").addEventListener("click", () => {
    const todo = nextUnreviewed();
    if (todo != null && state.tour && todo === state.tour.fid) {
      toast("this is the only tour left without a verdict");
    } else if (todo != null) {
      load(todo);
    } else if (state.group === MAIN_GROUP) {
      toast("every tour has a verdict");
    } else {
      toast(`${groupSpec(state.group).label}: every tour has a verdict`);
    }
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
