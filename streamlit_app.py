import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import streamlit.components.v1 as components
from citation_map import generate_citation_map
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import tempfile
import os
import time
import re
from urllib.parse import urlparse, parse_qs

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Citation Map",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Minimal CSS fixes
st.html("""<style>
#MainMenu, footer { display: none }
/* Input border */
[data-testid="stTextInput"] input { border: 1.5px solid #d1d5db !important; }
[data-testid="stTextInput"] input:focus { border-color: #d97706 !important; }
/* Compact layout — clear the fixed header */
.stMainBlockContainer { padding-top: 3.5rem !important; }
/* Remove form border */
[data-testid="stForm"] { border: none !important; padding: 0 !important; }
/* Tighten gaps */
[data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
/* Constrain main content for readability */
.stMainBlockContainer { max-width: 1100px !important; margin: 0 auto !important; }
/* Pin footer to bottom */
.app-footer { position: fixed; bottom: 0; left: 0; right: 0; background: #fff; z-index: 100; padding: 0 1rem; }
.stMainBlockContainer { padding-bottom: 4rem !important; }
</style>""")


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_scholar_id(input_str: str) -> str | None:
    """Extract a Google Scholar user ID from a URL or raw ID string.

    Accepts three input formats:
        1. A full Google Scholar profile URL
           (e.g. ``https://scholar.google.com/citations?user=ABC123&hl=en``)
        2. A raw alphanumeric Scholar ID (e.g. ``ABC123``)
        3. A partial URL fragment containing ``user=<id>``

    Args:
        input_str: The raw user input — may be a URL, an ID, or empty.

    Returns:
        The extracted Scholar ID string, or ``None`` if the input is empty
        or no valid ID could be detected.
    """
    input_str = input_str.strip()
    if not input_str:
        return None

    if "scholar.google" in input_str or input_str.startswith("http"):
        try:
            parsed = urlparse(input_str)
            params = parse_qs(parsed.query)
            if "user" in params:
                return params["user"][0]
        except Exception:
            pass

    if re.match(r'^[A-Za-z0-9_-]{8,20}$', input_str):
        return input_str

    match = re.search(r'user=([A-Za-z0-9_-]+)', input_str)
    if match:
        return match.group(1)

    return None


@st.cache_data
def get_cached_geocode():
    """Return a shared geocode cache dict, persisted across Streamlit reruns.

    The ``@st.cache_data`` decorator ensures a single dict instance is
    reused for the lifetime of the Streamlit server process, avoiding
    redundant geocoding requests.

    Returns:
        An empty dict on first call; the same (now populated) dict on
        subsequent calls.
    """
    return {}

geocode_cache = get_cached_geocode()


def geocode_affiliation(affiliation, geolocator):
    """Convert an institutional affiliation string to geographic coordinates.

    Uses a two-tier lookup strategy:
        1. **Manual cache** — a built-in dictionary of well-known universities
           and institutions with pre-defined coordinates, checked first for
           speed and reliability.
        2. **Nominatim geocoder** — falls back to the OpenStreetMap Nominatim
           service for affiliations not found in the manual cache.

    Results (including ``None`` for unresolvable affiliations) are cached in
    ``geocode_cache`` so repeated lookups are free.

    Args:
        affiliation: The institution name or affiliation string to geocode.
        geolocator: A ``geopy.geocoders.Nominatim`` instance used for the
            fallback geocoding request.

    Returns:
        A ``(latitude, longitude)`` tuple if the affiliation was resolved,
        or ``None`` if geocoding failed or timed out.
    """
    if affiliation in geocode_cache:
        return geocode_cache[affiliation]

    manual_locations = {
        "Harvard Medical School": (42.3364, -71.1064),
        "Harvard University": (42.3770, -71.1167),
        "MIT": (42.3601, -71.0942),
        "Stanford University": (37.4275, -122.1697),
        "University of Cambridge": (52.2053, 0.1218),
        "Oxford University": (51.7548, -1.2544),
        "Yale University": (41.3163, -72.9223),
        "University of Nebraska Medical Center": (41.2562, -95.9754),
        "Northwestern University": (41.8950, -87.6200),
        "Yonsei University": (37.5615, 126.9388),
        "Brigham and Women's Hospital": (42.3364, -71.1064),
        "University of Lincoln": (53.2276, -0.5484),
        "University of Toronto": (43.6629, -79.3957),
        "Zhengzhou University": (34.8152, 113.5358),
        "VIT University": (12.8398, 80.1558),
        "Vellore Institute of Technology": (12.8398, 80.1558),
        "University of Utah": (40.7674, -111.8413),
        "Texas A&M University": (30.6187, -96.3365),
        "Wayne State University": (42.3503, -83.0561),
        "Morehouse School of Medicine": (33.7380, -84.4128),
        "Cincinnati Children's Hospital": (39.1415, -84.5009),
        "University of Miami": (25.7923, -80.2131),
        "Cambridge University": (52.2053, 0.1192),
        "Kermanshah University": (34.3311, 47.0706),
        "Airlangga University": (-7.2690, 112.7853),
        "Oakland University": (42.6738, -83.2162),
        "University of Massachusetts Boston": (42.3134, -71.0368),
        "Florida International University": (25.7562, -80.3756),
        "Iran University of Medical Sciences": (35.7441, 51.3653),
        "University of Tokyo": (35.7126, 139.7620),
        "Tsinghua University": (40.0003, 116.3267),
        "University of Milan": (45.4602, 9.1946),
        "Karolinska Institute": (59.3487, 18.0237),
        "Cairo University": (30.0271, 31.2089),
        "Indian Institute of Technology Delhi": (28.5450, 77.1926),
        "Peking University": (39.9869, 116.3059),
        "Seoul National University": (37.4592, 126.9520),
        "ETH Zurich": (47.3763, 8.5480),
    }

    for key, coords in manual_locations.items():
        if key.lower() in affiliation.lower():
            geocode_cache[affiliation] = coords
            return coords

    try:
        location = geolocator.geocode(affiliation, timeout=10)
        if location:
            coords = (location.latitude, location.longitude)
            geocode_cache[affiliation] = coords
            return coords
    except GeocoderTimedOut:
        pass
    except Exception:
        pass

    geocode_cache[affiliation] = None
    return None


@st.cache_data(show_spinner=False)
def generate_citation_data(scholar_id):
    """Fetch citation data from Google Scholar for the given profile.

    Delegates to the ``citation-map`` library, which scrapes Google Scholar
    to collect citing papers and their authors' affiliations. The results
    are written to a temporary CSV file and loaded into a DataFrame.

    Args:
        scholar_id: A valid Google Scholar user ID (e.g. ``"ABC123"``).

    Returns:
        A ``pandas.DataFrame`` with columns including ``citing author name``
        and ``affiliation``, or ``None`` if the fetch failed. Displays a
        Streamlit error message on failure (rate-limit or other exceptions).
    """
    temp_dir = tempfile.mkdtemp()
    csv_path = os.path.join(temp_dir, 'citation_info.csv')
    map_path = os.path.join(temp_dir, 'citation_map.html')

    try:
        generate_citation_map(
            scholar_id,
            output_path=map_path,
            csv_output_path=csv_path,
            num_processes=2,
            pin_colorful=True,
            print_citing_affiliations=True,
            use_proxy=False,
        )

        if os.path.exists(csv_path):
            return pd.read_csv(csv_path)
        return None
    except Exception as e:
        msg = str(e)
        if "Cannot Fetch" in msg or "Google Scholar" in msg:
            st.error(
                "Google Scholar is temporarily blocking requests (rate limit). "
                "Please wait a few minutes and try again."
            )
        else:
            st.error(f"Error fetching data: {msg}")
        return None


def create_styled_map(df):
    """Build an interactive Folium map from citation data.

    Filters out rows with missing or placeholder affiliations, geocodes each
    unique affiliation, and places color-coded markers on a clustered Leaflet
    map. A client-side "Download Map" button (powered by ``html2canvas``) is
    injected as a native Leaflet control so users can export the current
    map view as a PNG with padding.

    Args:
        df: A ``pandas.DataFrame`` containing at least ``affiliation`` and
            ``citing author name`` columns.

    Returns:
        A tuple ``(folium.Map, stats)`` where *stats* is a dict with keys:
            - ``total_citations`` (int): Total rows in the input DataFrame.
            - ``mapped_locations`` (int): Number of successfully geocoded
              affiliations.
            - ``affiliations`` (list[dict]): Per-affiliation records with
              ``name``, ``authors``, ``lat``, and ``lng``.
        Returns ``(None, {})`` if no valid affiliations remain after filtering.
    """
    df_filtered = df[df['affiliation'] != 'No_author_found'].dropna(subset=['affiliation'])

    if df_filtered.empty:
        return None, {}

    affiliations = df_filtered['affiliation'].unique()
    geolocator = Nominatim(user_agent="citation_map_streamlit")

    m = folium.Map(location=[30, 0], zoom_start=2, tiles="CartoDB positron", attr="CartoDB")
    marker_cluster = MarkerCluster().add_to(m)

    colors = [
        'darkred', 'cadetblue', 'darkgreen', 'darkpurple', 'orange',
        'red', 'blue', 'green', 'purple', 'pink', 'lightblue', 'lightgreen',
    ]

    stats = {"total_citations": len(df), "mapped_locations": 0, "affiliations": []}

    for idx, affil in enumerate(affiliations):
        coords = geocode_affiliation(affil, geolocator)
        time.sleep(0.05)

        if coords:
            affil_data = df_filtered[df_filtered['affiliation'] == affil]
            authors = affil_data['citing author name'].unique()
            color = colors[idx % len(colors)]

            popup_html = f"""
            <div style="font-family:system-ui,sans-serif;min-width:180px;max-width:280px;">
                <div style="font-weight:600;font-size:13px;margin-bottom:6px;">{affil}</div>
                <div style="font-size:11px;color:#666;border-top:1px solid #eee;padding-top:6px;">
                    {', '.join(authors[:5])}
                    {'<br><span style="color:#d97706">+' + str(len(authors)-5) + ' more</span>' if len(authors) > 5 else ''}
                </div>
            </div>
            """

            folium.Marker(
                location=coords,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=affil[:60],
                icon=folium.Icon(color=color, icon="info-sign"),
            ).add_to(marker_cluster)

            stats["mapped_locations"] += 1
            stats["affiliations"].append({
                "name": affil, "authors": list(authors),
                "lat": coords[0], "lng": coords[1],
            })

    # Add download button as a Leaflet control
    download_js = folium.Element("""
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() {
            var mapEl = document.querySelector('.leaflet-container');
            if (!mapEl) return;
            var map = Object.values(mapEl).find(v => v && v._leaflet_id !== undefined)
                      || window[Object.keys(window).find(k => window[k] instanceof L.Map)];

            var DownloadControl = L.Control.extend({
                options: { position: 'topright' },
                onAdd: function() {
                    var btn = L.DomUtil.create('div', 'leaflet-bar');
                    btn.innerHTML = '<a href="#" title="Download map as PNG" style="display:flex;align-items:center;justify-content:center;width:auto;padding:0 10px;height:30px;font-size:13px;font-family:system-ui,sans-serif;text-decoration:none;color:#333;background:#fff;cursor:pointer;">&#x2913; Download Map</a>';
                    L.DomEvent.disableClickPropagation(btn);
                    btn.querySelector('a').addEventListener('click', function(e) {
                        e.preventDefault();
                        var controlContainer = document.querySelector('.leaflet-control-container');
                        controlContainer.style.display = 'none';
                        html2canvas(mapEl, { useCORS: true, allowTaint: true, scale: 2 }).then(function(canvas) {
                            controlContainer.style.display = '';
                            var pad = 24, w = canvas.width + pad*2, h = canvas.height + pad*2;
                            var out = document.createElement('canvas');
                            out.width = w; out.height = h;
                            var ctx = out.getContext('2d');
                            ctx.fillStyle = '#ffffff';
                            ctx.fillRect(0, 0, w, h);
                            ctx.drawImage(canvas, pad, pad);
                            var link = document.createElement('a');
                            link.download = 'citation_map.png';
                            link.href = out.toDataURL('image/png');
                            link.click();
                        }).catch(function() {
                            controlContainer.style.display = '';
                        });
                    });
                    return btn;
                }
            });

            if (map && map.addControl) {
                map.addControl(new DownloadControl());
            }
        }, 500);
    });
    </script>
    """)
    m.get_root().html.add_child(download_js)

    return m, stats


# ══════════════════════════════════════════════════════════════════════════════
#                              MAIN UI
# ══════════════════════════════════════════════════════════════════════════════

st.html("""
<div style="text-align:center; padding:1rem 0 0.5rem;">
    <h2 style="margin:0; font-size:1.8rem; font-weight:600;">🌍 Citation Cartography</h2>
    <p style="color:#6b7280; margin:0.25rem 0 0; font-size:0.95rem;">Visualize where your research resonates across the globe</p>
</div>
""")

# ── Input ─────────────────────────────────────────────────────────────────────
with st.form("scholar_form"):
    user_input = st.text_input(
        "Google Scholar ID or Profile URL",
        placeholder="Scholar ID or full URL (e.g. scholar.google.com/citations?user=YOUR_ID)",
    )
    btn_left, btn_col, demo_col, btn_right = st.columns([1, 1, 1, 1])
    with btn_col:
        submitted = st.form_submit_button("Generate Map", type="primary", use_container_width=True)
    with demo_col:
        demo_btn = st.form_submit_button("Try Demo", use_container_width=True)

# Show detected ID
scholar_id = None
if user_input:
    scholar_id = extract_scholar_id(user_input)
    if scholar_id and scholar_id != user_input.strip():
        st.success(f"Detected Scholar ID: **{scholar_id}**", icon="✅")


def get_demo_data():
    """Return a sample DataFrame of citation data for UI preview.

    Provides 20 synthetic records spanning institutions across North America,
    Europe, Asia, and Africa so the full UI (map, stats, affiliations list)
    can be exercised without hitting Google Scholar.

    Returns:
        A ``pandas.DataFrame`` with ``citing author name`` and ``affiliation``
        columns, matching the schema produced by ``generate_citation_data``.
    """
    return pd.DataFrame({
        "citing author name": [
            "Alice Johnson", "Bob Smith", "Carlos Rivera", "Diana Chen", "Eva Braun",
            "Fatima Al-Rashid", "George Tanaka", "Hannah Mueller", "Ivan Petrov", "Julia Santos",
            "Kenji Yamamoto", "Lisa Wang", "Marco Rossi", "Nina Johansson", "Omar Hassan",
            "Priya Sharma", "Qi Zhang", "Rachel Kim", "Stefan Fischer", "Tomoko Sato",
        ],
        "affiliation": [
            "MIT", "Stanford University", "Harvard University", "University of Cambridge",
            "Oxford University", "Yale University", "University of Toronto",
            "Northwestern University", "University of Cambridge", "Stanford University",
            "University of Tokyo", "Tsinghua University", "University of Milan",
            "Karolinska Institute", "Cairo University",
            "Indian Institute of Technology Delhi", "Peking University",
            "Seoul National University", "ETH Zurich", "University of Tokyo",
        ],
    })


# ── Results ───────────────────────────────────────────────────────────────────

# Persist results across reruns
if "result_df" not in st.session_state:
    st.session_state.result_df = None
    st.session_state.is_demo = False

def _build_and_cache(df):
    """Build the map and statistics, then persist them in Streamlit session state.

    Calls ``create_styled_map`` to geocode affiliations and generate the
    Folium map, then stores the rendered HTML and stats dict in
    ``st.session_state`` so they survive Streamlit reruns without
    recomputation.

    Args:
        df: A ``pandas.DataFrame`` of citation data (same schema as
            ``generate_citation_data`` output).
    """
    with st.spinner("Building map and geocoding affiliations..."):
        citation_map, stats = create_styled_map(df)
        st.session_state.cached_map_html = citation_map._repr_html_() if citation_map else None
        st.session_state.cached_stats = stats

if demo_btn:
    st.session_state.result_df = get_demo_data()
    st.session_state.is_demo = True
    _build_and_cache(st.session_state.result_df)
elif submitted and user_input:
    if not scholar_id:
        st.error("Could not detect a valid Scholar ID. Please check your input.")
    else:
        with st.spinner("Fetching citations and building map — this may take a minute..."):
            df = generate_citation_data(scholar_id)
            if df is not None and not df.empty:
                st.session_state.result_df = df
                st.session_state.is_demo = False
                _build_and_cache(df)
            else:
                st.error("Could not fetch citation data. Please check the Scholar ID.")
elif submitted:
    st.warning("Please enter a Google Scholar ID or profile URL.")

if st.session_state.is_demo:
    st.info("Showing demo data to preview the UI.", icon="🧪")

df = st.session_state.result_df
cached_map_html = st.session_state.get("cached_map_html")
stats = st.session_state.get("cached_stats")

if df is not None and not df.empty and cached_map_html:
    st.divider()

    # Stats
    c1, c2, c3 = st.columns(3)
    c1.metric("Citations", f"{stats['total_citations']:,}")
    c2.metric("Locations", stats['mapped_locations'])
    c3.metric("Affiliations", len(stats['affiliations']))

    # Map
    st.subheader("World Map")
    components.html(cached_map_html, height=520, scrolling=False)

    # Downloads
    st.write("")  # spacer
    dl1, _, _ = st.columns([1, 1, 2])
    with dl1:
        st.download_button(
            "Download Data (.csv)",
            data=df.to_csv(index=False),
            file_name="citation_data.csv", mime="text/csv",
            use_container_width=True,
        )
    st.write("")  # spacer

    # Affiliations
    st.subheader("Affiliations")
    for affil in stats['affiliations']:
        with st.expander(affil['name'][:80]):
            st.markdown(f"**Coordinates:** `{affil['lat']:.4f}, {affil['lng']:.4f}`")
            authors_str = ", ".join(affil["authors"][:10])
            extra = f" *and {len(affil['authors']) - 10} more*" if len(affil["authors"]) > 10 else ""
            st.markdown(f"**Authors:** {authors_str}{extra}")

    with st.expander("View raw data"):
        st.dataframe(df, use_container_width=True)

# Footer
st.html("""
<div class="app-footer">
<hr style="margin:0 0 0.3rem;border:none;border-top:1px solid #e5e7eb;">
<p style="text-align:center;color:#9ca3af;font-size:0.8rem;line-height:1.6;margin:0 0 0.4rem;">
    Data sourced from <a href="https://scholar.google.com" target="_blank" style="color:#d97706;text-decoration:none;">Google Scholar</a>
    &middot; Maps by <a href="https://www.openstreetmap.org" target="_blank" style="color:#d97706;text-decoration:none;">OpenStreetMap</a>
    &middot; Built with <a href="https://streamlit.io" target="_blank" style="color:#d97706;text-decoration:none;">Streamlit</a>
    &amp; <a href="https://python-visualization.github.io/folium/" target="_blank" style="color:#d97706;text-decoration:none;">Folium</a>
</p>
</div>
""")
