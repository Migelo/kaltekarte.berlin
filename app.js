/* Kalte Karte - air-conditioned places in Berlin.
 *
 * Renders the points from points.geojson on a Leaflet map (OpenStreetMap
 * tiles, no API key needed) and lets you filter the markers by category
 * (supermarket, cafe, restaurant, ...). Replaces the old Google My Maps
 * iframe, which could not be filtered.
 */

// Category definitions: order = display order. Each has a colour (used for the
// marker and the legend chip) and an emoji glyph shown inside the marker.
// Strings are kept pure-ASCII with \u escapes so rendering does not depend on
// the charset the server happens to label this file with.
var CATEGORIES = [
  { key: 'supermarket', label: 'Supermarket',              color: '#2e9e3e', emoji: '\u{1F6D2}' }, // shopping cart
  { key: 'cafe',        label: 'Caf\u{00E9} & Bakery',     color: '#b5651d', emoji: '\u{2615}' }, // hot beverage
  { key: 'restaurant',  label: 'Restaurant & Bar',         color: '#e23b3b', emoji: '\u{1F37D}' }, // fork & knife plate
  { key: 'shopping',    label: 'Shopping',                 color: '#8e44ad', emoji: '\u{1F6CD}' }, // shopping bags
  { key: 'drugstore',   label: 'Drugstore & Pharmacy',     color: '#1f8fff', emoji: '\u{1F48A}' }, // pill
  { key: 'fitness',     label: 'Fitness',                  color: '#ff8c1a', emoji: '\u{1F3CB}' }, // weight lifter
  { key: 'cinema',      label: 'Cinema',                   color: '#d6336c', emoji: '\u{1F3AC}' }, // clapper board
  { key: 'culture',     label: 'Culture',                  color: '#16a3b3', emoji: '\u{1F3DB}' }, // classical building
  { key: 'office',      label: 'Office & Coworking',       color: '#6c7a89', emoji: '\u{1F3E2}' }, // office building
  { key: 'hotel',       label: 'Hotel',                    color: '#c9a227', emoji: '\u{1F3E8}' }, // hotel
  { key: 'transport',   label: 'Transport',                color: '#34495e', emoji: '\u{1F689}' }, // station
  { key: 'gas_station', label: 'Gas Station',              color: '#7f8c8d', emoji: '\u{26FD}' }, // fuel pump
  { key: 'other',       label: 'Other',                    color: '#95a5a6', emoji: '\u{1F4CD}' }  // round pushpin
];

var CATEGORY_BY_KEY = {};
CATEGORIES.forEach(function (c) { CATEGORY_BY_KEY[c.key] = c; });

// Which categories are currently visible. Starts with all enabled.
var active = {};
CATEGORIES.forEach(function (c) { active[c.key] = true; });

var map, cluster;
var allMarkers = [];      // [{ category, marker, name, lat, lon, id }]
var counts = {};          // category -> number of points
var userLatLng = null;    // set once geolocation succeeds
var userMarker = null;    // "you are here" marker
var query = '';           // current text search (lowercased)

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, function (ch) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
  });
}

// Google Maps link for an entry. Combining the business name with the exact
// coordinates makes Google resolve to the real listing (hours, reviews,
// directions) at that spot rather than a generic pin.
function gmapsUrl(name, lat, lon) {
  var query = encodeURIComponent(name + ' ' + lat + ',' + lon);
  return 'https://www.google.com/maps/search/?api=1&query=' + query;
}

function markerIcon(cat) {
  var c = CATEGORY_BY_KEY[cat] || CATEGORY_BY_KEY.other;
  return L.divIcon({
    className: '',
    html: '<div class="cat-marker" style="background:' + c.color + '"><span>' + c.emoji + '</span></div>',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -16]
  });
}

// Recompute which markers are visible (category filters + text search), push
// them into the cluster, update the count, and refresh the results list.
function rebuild() {
  cluster.clearLayers();
  var visible = [];
  for (var i = 0; i < allMarkers.length; i++) {
    var m = allMarkers[i];
    if (!active[m.category]) continue;
    if (query && m.name.toLowerCase().indexOf(query) === -1) continue;
    visible.push(m);
  }
  cluster.addLayers(visible.map(function (m) { return m.marker; }));
  var countEl = document.getElementById('result-count');
  if (countEl) countEl.textContent = visible.length + ' / ' + allMarkers.length;
  renderList(visible);
}

// Render the (optional) results list, sorted by distance when located else by
// name. Capped so a huge unfiltered list stays responsive.
function renderList(visible) {
  var listEl = document.getElementById('results-list');
  if (!listEl) return;
  var items = visible.slice();
  if (userLatLng) {
    items.forEach(function (m) { m._d = map.distance(userLatLng, m.marker.getLatLng()); });
    items.sort(function (a, b) { return a._d - b._d; });
  } else {
    items.sort(function (a, b) { return a.name.localeCompare(b.name); });
  }
  var MAX = 120;
  var html = items.slice(0, MAX).map(function (m) {
    var c = CATEGORY_BY_KEY[m.category];
    var dist = (userLatLng && typeof m._d === 'number')
      ? '<span class="li-dist">' + formatDistance(m._d) + '</span>' : '';
    return '<button class="result-row" type="button" data-id="' + m.id + '">' +
      '<span class="dot" style="background:' + c.color + '"><span class="ic">' + c.emoji + '</span></span>' +
      '<span class="li-name">' + escapeHtml(m.name) + '</span>' + dist + '</button>';
  }).join('');
  if (items.length > MAX) {
    html += '<div class="list-more">+' + (items.length - MAX) + ' more \u{2014} zoom in or search</div>';
  }
  listEl.innerHTML = html || '<div class="list-empty">No places match.</div>';
}

function buildFilterUI() {
  var container = document.getElementById('filter-chips');
  CATEGORIES.forEach(function (c) {
    var n = counts[c.key] || 0;
    if (n === 0) return; // hide categories that have no points
    var btn = document.createElement('button');
    btn.className = 'filter-chip active';
    btn.setAttribute('data-cat', c.key);
    btn.setAttribute('type', 'button');
    btn.innerHTML =
      '<span class="dot" style="background:' + c.color + '"><span class="ic">' + c.emoji + '</span></span>' +
      '<span class="lbl">' + c.label + '</span>' +
      '<span class="cnt">' + n + '</span>';
    btn.addEventListener('click', function () {
      active[c.key] = !active[c.key];
      btn.classList.toggle('active', active[c.key]);
      rebuild();
      writeHash();
    });
    container.appendChild(btn);
  });

  function setAll(state) {
    CATEGORIES.forEach(function (c) { active[c.key] = state; });
    var chips = container.querySelectorAll('.filter-chip');
    for (var i = 0; i < chips.length; i++) chips[i].classList.toggle('active', state);
    rebuild();
    writeHash();
  }
  document.getElementById('filter-all').addEventListener('click', function () { setAll(true); });
  document.getElementById('filter-none').addEventListener('click', function () { setAll(false); });

  var panel = document.getElementById('filters');
  var toggleBtn = document.getElementById('filter-toggle');
  toggleBtn.addEventListener('click', function () {
    var collapsed = panel.classList.toggle('collapsed');
    toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  });

  // Start collapsed on small screens so the panel doesn't cover the map.
  if (window.matchMedia && window.matchMedia('(max-width: 600px)').matches) {
    panel.classList.add('collapsed');
  }
}

// Reflect the `active` object onto the chip .active classes (used after a hash
// restore sets state programmatically).
function applyActiveToChips() {
  var chips = document.querySelectorAll('#filter-chips .filter-chip');
  for (var i = 0; i < chips.length; i++) {
    var k = chips[i].getAttribute('data-cat');
    chips[i].classList.toggle('active', !!active[k]);
  }
}

// Serialize current filters/search/view into the URL hash (shareable links).
// replaceState avoids polluting history and firing hashchange.
function writeHash() {
  var on = CATEGORIES.filter(function (c) { return active[c.key]; })
                     .map(function (c) { return c.key; });
  var parts = [];
  if (on.length !== CATEGORIES.length) parts.push('cat=' + on.join(','));
  if (query) parts.push('q=' + encodeURIComponent(query));
  if (map) {
    var ctr = map.getCenter();
    parts.push('z=' + map.getZoom());
    parts.push('c=' + ctr.lat.toFixed(5) + ',' + ctr.lng.toFixed(5));
  }
  var hash = parts.length ? '#' + parts.join('&') : location.pathname + location.search;
  history.replaceState(null, '', hash);
}

// Apply a hash on load. Returns true if it set an explicit map view.
function readHash() {
  var h = location.hash.replace(/^#/, '');
  if (!h) return false;
  var params = {};
  h.split('&').forEach(function (kv) {
    var i = kv.indexOf('=');
    if (i > 0) params[kv.slice(0, i)] = kv.slice(i + 1);
  });
  if (params.cat !== undefined) {
    var set = {};
    decodeURIComponent(params.cat).split(',').forEach(function (k) { if (k) set[k] = true; });
    CATEGORIES.forEach(function (c) { active[c.key] = !!set[c.key]; });
  }
  if (params.q) {
    query = decodeURIComponent(params.q).toLowerCase();
    var inp = document.getElementById('filter-search');
    if (inp) inp.value = decodeURIComponent(params.q);
  }
  var hadView = false;
  if (params.c && params.z) {
    var cc = params.c.split(',');
    var lat = parseFloat(cc[0]), lng = parseFloat(cc[1]), z = parseInt(params.z, 10);
    if (!isNaN(lat) && !isNaN(lng) && !isNaN(z)) { map.setView([lat, lng], z); hadView = true; }
  }
  return hadView;
}

// Wire the search box, results list, and about dialog.
function initDiscovery() {
  var search = document.getElementById('filter-search');
  if (search) {
    search.addEventListener('input', function () {
      query = this.value.trim().toLowerCase();
      rebuild();
      writeHash();
    });
  }

  var listToggle = document.getElementById('list-toggle');
  var results = document.getElementById('results');
  if (listToggle && results) {
    listToggle.addEventListener('click', function () {
      var open = results.classList.toggle('open');
      listToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    var closeList = document.getElementById('results-close');
    if (closeList) closeList.addEventListener('click', function () { results.classList.remove('open'); });
  }

  var resultsList = document.getElementById('results-list');
  if (resultsList) {
    resultsList.addEventListener('click', function (e) {
      var row = e.target.closest ? e.target.closest('.result-row') : null;
      if (!row) return;
      var rec = allMarkers[parseInt(row.getAttribute('data-id'), 10)];
      if (!rec) return;
      cluster.zoomToShowLayer(rec.marker, function () { rec.marker.openPopup(); });
      if (window.matchMedia && window.matchMedia('(max-width: 600px)').matches) {
        results.classList.remove('open');
      }
    });
  }

  var about = document.getElementById('about');
  var aboutBtn = document.getElementById('about-btn');
  if (about && aboutBtn) {
    aboutBtn.addEventListener('click', function () { about.hidden = false; });
    var aboutClose = document.getElementById('about-close');
    if (aboutClose) aboutClose.addEventListener('click', function () { about.hidden = true; });
    about.addEventListener('click', function (e) { if (e.target === about) about.hidden = true; });
  }
}

function addPoints(geojson) {
  geojson.features.forEach(function (f, idx) {
    var cat = (f.properties && f.properties.category) || 'other';
    if (!CATEGORY_BY_KEY[cat]) cat = 'other';
    counts[cat] = (counts[cat] || 0) + 1;
    var coords = f.geometry.coordinates; // [lon, lat]
    var lat = coords[1], lon = coords[0];
    var name = f.properties.name;
    var marker = L.marker([lat, lon], { icon: markerIcon(cat) });
    var c = CATEGORY_BY_KEY[cat];
    var walkUrl = 'https://www.google.com/maps/dir/?api=1&destination=' +
      lat + ',' + lon + '&travelmode=walking';
    marker.bindPopup(
      '<div class="popup">' +
      '<strong>' + escapeHtml(name) + '</strong>' +
      '<div class="popup-cat"><span class="dot" style="background:' + c.color + '"><span class="ic">' +
      c.emoji + '</span></span>' + c.label + '</div>' +
      '<div class="popup-dist" hidden></div>' +
      '<div class="popup-links">' +
      '<a class="popup-link" href="' + gmapsUrl(name, lat, lon) +
      '" target="_blank" rel="noopener noreferrer">View on Google Maps &#8599;</a>' +
      '<a class="popup-link popup-link-walk" href="' + walkUrl +
      '" target="_blank" rel="noopener noreferrer">Walk here &#8599;</a>' +
      '</div>' +
      '</div>'
    );
    allMarkers.push({ category: cat, marker: marker, name: name, lat: lat, lon: lon, id: idx });
  });
}

function setUserLocation(lat, lon) {
  userLatLng = L.latLng(lat, lon);
  if (userMarker) {
    userMarker.setLatLng(userLatLng);
  } else {
    userMarker = L.circleMarker(userLatLng, {
      radius: 8, color: '#1f6feb', weight: 3, fillColor: '#1f6feb', fillOpacity: 0.4
    }).addTo(map).bindPopup('You are here');
  }
}

// Ask the browser for location once and cache it. cb(latlng) on success,
// cbErr(reason) on failure.
function requestLocation(cb, cbErr) {
  if (userLatLng) { if (cb) cb(userLatLng); return; }
  if (!navigator.geolocation) { if (cbErr) cbErr('no-geo'); return; }
  navigator.geolocation.getCurrentPosition(function (pos) {
    setUserLocation(pos.coords.latitude, pos.coords.longitude);
    if (cb) cb(userLatLng);
  }, function () { if (cbErr) cbErr('denied'); },
     { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 });
}

// On load: locate silently. Recenter only if `recenter` (no shared view in the
// URL) and the user is near Berlin. Refresh the list to sort by distance.
function autoLocate(recenter) {
  requestLocation(function (ll) {
    if (recenter && ll.lat > 52.0 && ll.lat < 53.0 && ll.lng > 12.8 && ll.lng < 13.9) {
      map.setView(ll, 14);
    }
    rebuild();
  });
}

// Straight-line distance + rough walking time (~5 km/h).
function formatDistance(metres) {
  var mins = Math.max(1, Math.round(metres / 83));
  var dist = metres < 1000
    ? Math.round(metres / 10) * 10 + ' m'
    : (metres / 1000).toFixed(1) + ' km';
  return dist + ' \u{00B7} ~' + mins + ' min walk';
}

// Fly to the closest currently-visible (filter-respecting) place and open it.
function findNearest() {
  requestLocation(function (ll) {
    var best = null, bestD = Infinity;
    for (var i = 0; i < allMarkers.length; i++) {
      var m = allMarkers[i];
      if (!active[m.category]) continue;
      var dd = map.distance(ll, m.marker.getLatLng());
      if (dd < bestD) { bestD = dd; best = m; }
    }
    if (!best) { toast('No places match the current filters.'); return; }
    cluster.zoomToShowLayer(best.marker, function () { best.marker.openPopup(); });
  }, function (reason) {
    toast(reason === 'denied' ? 'Location permission denied.' : 'Location unavailable.');
  });
}

function toast(msg) {
  var t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(function () { t.hidden = true; }, 3200);
}

// Open-Meteo current temperature (free, keyless). Show a nudge on hot days only.
function loadHeatBanner() {
  var banner = document.getElementById('heat-banner');
  if (!banner) return;
  fetch('https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.405&current=temperature_2m,apparent_temperature')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var cur = data && data.current;
      if (!cur || typeof cur.apparent_temperature !== 'number') return;
      var feels = Math.round(cur.apparent_temperature);
      if (feels >= 27) {
        banner.innerHTML = '\u{2744} It feels like <strong>' + feels +
          '\u{00B0}C</strong> in Berlin \u{2014} find a cool place.';
        banner.hidden = false;
      }
    })
    .catch(function () { /* offline / blocked - just stay hidden */ });
}

function init() {
  // Zoom control top-right so it doesn't sit under the filter panel (top-left).
  map = L.map('map', { zoomControl: false }).setView([52.52, 13.405], 12);
  L.control.zoom({ position: 'topright' }).addTo(map);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  cluster = L.markerClusterGroup({
    maxClusterRadius: 50,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false
  });
  map.addLayer(cluster);

  // Inject distance/walk-time into a popup when it opens (once located).
  map.on('popupopen', function (e) {
    var src = e.popup._source;
    if (!src || !userLatLng) return;
    var el = e.popup.getElement();
    var node = el && el.querySelector('.popup-dist');
    if (!node) return;
    node.textContent = formatDistance(map.distance(userLatLng, src.getLatLng()));
    node.hidden = false;
  });

  var locateBtn = document.getElementById('locate-btn');
  if (locateBtn) locateBtn.addEventListener('click', findNearest);

  loadHeatBanner();
  initDiscovery();
  map.on('moveend', writeHash);

  fetch('points.geojson')
    .then(function (r) { return r.json(); })
    .then(function (geojson) {
      addPoints(geojson);
      buildFilterUI();
      var hadView = readHash();
      applyActiveToChips();
      rebuild();
      autoLocate(!hadView);
    })
    .catch(function (err) {
      console.error('Failed to load points.geojson', err);
      var panel = document.getElementById('filter-chips');
      if (panel) panel.innerHTML = '<p class="err">Could not load locations.</p>';
    });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
