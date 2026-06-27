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
var allMarkers = [];      // [{ category, marker }]
var counts = {};          // category -> number of points

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

function rebuild() {
  cluster.clearLayers();
  var layers = [];
  for (var i = 0; i < allMarkers.length; i++) {
    if (active[allMarkers[i].category]) layers.push(allMarkers[i].marker);
  }
  cluster.addLayers(layers);
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
    });
    container.appendChild(btn);
  });

  function setAll(state) {
    CATEGORIES.forEach(function (c) { active[c.key] = state; });
    var chips = container.querySelectorAll('.filter-chip');
    for (var i = 0; i < chips.length; i++) chips[i].classList.toggle('active', state);
    rebuild();
  }
  document.getElementById('filter-all').addEventListener('click', function () { setAll(true); });
  document.getElementById('filter-none').addEventListener('click', function () { setAll(false); });

  var panel = document.getElementById('filters');
  document.getElementById('filter-toggle').addEventListener('click', function () {
    panel.classList.toggle('collapsed');
  });

  // Start collapsed on small screens so the panel doesn't cover the map.
  if (window.matchMedia && window.matchMedia('(max-width: 600px)').matches) {
    panel.classList.add('collapsed');
  }
}

function addPoints(geojson) {
  geojson.features.forEach(function (f) {
    var cat = (f.properties && f.properties.category) || 'other';
    if (!CATEGORY_BY_KEY[cat]) cat = 'other';
    counts[cat] = (counts[cat] || 0) + 1;
    var coords = f.geometry.coordinates; // [lon, lat]
    var lat = coords[1], lon = coords[0];
    var marker = L.marker([lat, lon], { icon: markerIcon(cat) });
    var c = CATEGORY_BY_KEY[cat];
    marker.bindPopup(
      '<div class="popup">' +
      '<strong>' + escapeHtml(f.properties.name) + '</strong>' +
      '<div class="popup-cat"><span class="dot" style="background:' + c.color + '"><span class="ic">' +
      c.emoji + '</span></span>' + c.label + '</div>' +
      '<a class="popup-link" href="' + gmapsUrl(f.properties.name, lat, lon) +
      '" target="_blank" rel="noopener noreferrer">View on Google Maps &#8599;</a>' +
      '</div>'
    );
    allMarkers.push({ category: cat, marker: marker });
  });
}

function locateUser() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(function (position) {
    var lat = position.coords.latitude, lon = position.coords.longitude;
    // Only recenter if the user is somewhere near Berlin.
    if (lat > 52.0 && lat < 53.0 && lon > 12.8 && lon < 13.9) {
      map.setView([lat, lon], 14);
    }
    L.circleMarker([lat, lon], {
      radius: 8, color: '#1f6feb', weight: 3, fillColor: '#1f6feb', fillOpacity: 0.4
    }).addTo(map).bindPopup('You are here');
  }, function () { /* permission denied - ignore */ });
}

function init() {
  map = L.map('map', { zoomControl: true }).setView([52.52, 13.405], 12);

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

  fetch('points.geojson')
    .then(function (r) { return r.json(); })
    .then(function (geojson) {
      addPoints(geojson);
      buildFilterUI();
      rebuild();
      locateUser();
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
