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


def _clean_affiliation(raw: str) -> list[str]:
    """Extract geocodable institution names from a verbose affiliation string.

    SerpAPI author profiles often include titles, roles, and departments
    alongside the institution name (e.g. "Associate Professor of Internal
    Medicine, Wayne State University"). This function produces a ranked
    list of candidate strings to try geocoding, from most specific to
    most general.

    Args:
        raw: The raw affiliation string from a Scholar profile.

    Returns:
        A list of candidate strings to attempt geocoding, ordered from
        best to fallback. Always includes the original string first.
    """
    candidates = [raw]

    _institution_keywords = [
        'university', 'college', 'institute', 'hospital', 'medical center',
        'school of', 'centre', 'center', 'clinic', 'laboratory', 'labs',
        'research', 'académie', 'università', 'universität', 'sciences',
        'medical school',
    ]

    def _add(s):
        s = s.strip().strip('.,')
        if s and s not in candidates:
            candidates.append(s)

    # Split on comma AND period-space (handles "Hospital X. Director de Y" style)
    # Use ". " (period-space) to avoid splitting abbreviations like "U."
    all_parts = [p.strip() for p in re.split(r'[,]|\.\s', raw) if p.strip()]

    # Find parts that look like institutions — add them first as best candidates
    for part in all_parts:
        part_lower = part.lower()
        if any(kw in part_lower for kw in _institution_keywords):
            # Strip department/division prefixes
            stripped = re.sub(
                r'^(?:Department|Division|School|Faculty|College|Section)\s+of\s+[^,]+[,.]?\s*',
                '', part, flags=re.IGNORECASE
            ).strip()
            _add(stripped)
            if part != stripped:
                _add(part)

    # Try after " at " or " in " (e.g. "Associate Professor at XYZ")
    for sep in [' at ', ' in ']:
        if sep in raw.lower():
            idx = raw.lower().index(sep)
            after = raw[idx + len(sep):].strip().rstrip('.')
            _add(after)

    # Strip common title/role prefixes
    _role_patterns = [
        r'^(?:Full |Associate |Assistant |Adjunct |Emeritus |Distinguished |Visiting )?'
        r'(?:University )?'
        r'(?:Professor|Researcher|Research Associate|Research Fellow|Lecturer|Instructor|'
        r'Fellow|Scientist|Director|Chair|Head|Dean|Postdoc|Resident|Resident Physician|'
        r'Resident Doctor|Resident Pathologist|Hospitalist Physician|Postdoctoral Fellow)'
        r'(?:\s+of\s+[^,]+)?'
        r'[,.]?\s*',
        r'^[^,]+(?:Professor|Researcher|Fellow|Director|Chair|Dean)\s*[,.]?\s*',
    ]
    cleaned = raw
    for pattern in _role_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
    _add(cleaned)

    return candidates


def geocode_affiliation(affiliation, geolocator):
    """Convert an institutional affiliation string to geographic coordinates.

    Uses ``_clean_affiliation`` to extract geocodable institution names from
    verbose affiliation strings, then tries each candidate against the
    Nominatim geocoder until one resolves.

    Results (including ``None`` for unresolvable affiliations) are cached in
    ``geocode_cache`` so repeated lookups are free.

    Args:
        affiliation: The institution name or affiliation string to geocode.
        geolocator: A ``geopy.geocoders.Nominatim`` instance used for
            geocoding requests.

    Returns:
        A ``(latitude, longitude)`` tuple if the affiliation was resolved,
        or ``None`` if geocoding failed or timed out.
    """
    if affiliation in geocode_cache:
        return geocode_cache[affiliation]

    # Try geocoding each cleaned candidate until one succeeds
    candidates = _clean_affiliation(affiliation)
    for candidate in candidates:
        try:
            location = geolocator.geocode(candidate, timeout=10)
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


_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache", "citations")
os.makedirs(_CACHE_DIR, exist_ok=True)

_MAX_RETRIES = 3
_BACKOFF_SECONDS = [30, 60, 120]


def _get_serpapi_key() -> str | None:
    """Retrieve the SerpAPI key from Streamlit secrets or environment.

    Checks ``st.secrets["SERPAPI_KEY"]`` first, then falls back to the
    ``SERPAPI_KEY`` environment variable.

    Returns:
        The API key string, or ``None`` if not configured.
    """
    try:
        return st.secrets["SERPAPI_KEY"]
    except Exception:
        return os.environ.get("SERPAPI_KEY")


def _fetch_via_serpapi(scholar_id: str, api_key: str) -> tuple[pd.DataFrame | None, dict | None]:
    """Fetch author profile and citing authors via SerpAPI (hybrid approach).

    Uses a two-step strategy:
        1. **Author profile** (1 call) — ``google_scholar_author`` returns
           name, affiliation, email, interests, citation metrics, co-authors
           (with affiliations), and articles with ``cites_id``.
        2. **Citing papers** (N calls) — for each article with citations,
           queries ``google_scholar`` with ``cites=<cites_id>`` to discover
           all citing papers and their author names. Paginates through all
           results.

    Co-authors' affiliations (from step 1) are used for map locations.
    Citing author names (from step 2) enrich the dataset.

    Total API calls: ``1 + N`` (typically ~7-10 for a mid-sized profile).

    Args:
        scholar_id: A valid Google Scholar user ID.
        api_key: A valid SerpAPI API key.

    Returns:
        A tuple of ``(DataFrame, author_profile)`` where *author_profile*
        is a dict with keys ``name``, ``affiliations``, ``email``,
        ``interests``, ``thumbnail``, ``cited_by``, ``co_authors``, and
        ``articles``. Either or both may be ``None`` on failure.
    """
    try:
        from serpapi import GoogleSearch
    except ImportError:
        st.error("SerpAPI key found but `google-search-results` package is not installed. "
                 "Run: `pip install google-search-results`")
        return None, None

    # ── Step 1: Author profile (1 API call) ──────────────────────────────────
    author_params = {
        "engine": "google_scholar_author",
        "author_id": scholar_id,
        "api_key": api_key,
        "num": 100,
    }

    try:
        author_results = GoogleSearch(author_params).get_dict()
    except Exception as e:
        st.error(f"SerpAPI error fetching author profile: {e}")
        return None, None

    author_raw = author_results.get("author", {})
    cited_by_raw = author_results.get("cited_by", {})
    co_authors_raw = author_results.get("co_authors", [])
    articles_raw = author_results.get("articles", [])

    co_authors = [
        {"name": c.get("name", ""), "affiliations": c.get("affiliations", "")}
        for c in co_authors_raw
        if c.get("affiliations")
    ]

    articles = [
        {
            "title": a.get("title", ""),
            "year": a.get("year", ""),
            "cited_by": a.get("cited_by", {}).get("value", 0) or 0,
        }
        for a in articles_raw
    ]

    author_profile = {
        "name": author_raw.get("name", ""),
        "affiliations": author_raw.get("affiliations", ""),
        "email": author_raw.get("email", ""),
        "interests": [i.get("title", "") for i in author_raw.get("interests", [])],
        "thumbnail": author_raw.get("thumbnail", ""),
        "cited_by": cited_by_raw,
        "co_authors": co_authors,
        "articles": articles,
    }

    # ── Step 2: Fetch citing papers for each article (N API calls) ───────────
    # Build a lookup of co-author affiliations by name for quick merging
    coauthor_affil = {}
    for ca in co_authors:
        if ca["affiliations"]:
            coauthor_affil[ca["name"]] = ca["affiliations"]

    rows = []
    seen_authors: set[str] = set()

    # Include the author's own affiliation
    if author_raw.get("affiliations"):
        rows.append({
            "citing author name": author_raw["name"],
            "affiliation": author_raw["affiliations"],
        })
        seen_authors.add(author_raw["name"])

    # Include co-authors with their affiliations
    for ca in co_authors:
        if ca["affiliations"] and ca["name"] not in seen_authors:
            rows.append({
                "citing author name": ca["name"],
                "affiliation": ca["affiliations"],
            })
            seen_authors.add(ca["name"])

    # Fetch citing papers to collect all citing author names
    articles_with_cites = [a for a in articles_raw if a.get("cited_by", {}).get("cites_id")]
    total_cite_pages = sum(
        max(1, -(-min(a.get("cited_by", {}).get("value", 0), 200) // 20))
        for a in articles_with_cites
    ) if articles_with_cites else 0

    if articles_with_cites:
        progress = st.progress(0, text="Fetching citing papers...")
        api_calls = 1  # already made 1 for author profile
        cite_page_done = 0

        for article in articles_with_cites:
            cites_id = article["cited_by"]["cites_id"]
            cite_count = article["cited_by"].get("value", 0)
            start = 0
            max_results = min(cite_count, 200)

            while start < max_results:
                try:
                    cite_params = {
                        "engine": "google_scholar",
                        "cites": cites_id,
                        "api_key": api_key,
                        "start": start,
                        "num": 20,
                    }
                    cite_results = GoogleSearch(cite_params).get_dict()
                    api_calls += 1
                except Exception:
                    break

                organic = cite_results.get("organic_results", [])
                if not organic:
                    break

                for paper in organic:
                    pub_info = paper.get("publication_info", {})
                    for author in pub_info.get("authors", []):
                        name = author.get("name", "").strip()
                        if not name or name in seen_authors:
                            continue
                        seen_authors.add(name)
                        # Use co-author affiliation if this citing author
                        # happens to be a known co-author
                        affiliation = coauthor_affil.get(name, "")
                        rows.append({
                            "citing author name": name,
                            "affiliation": affiliation,
                        })

                start += 20
                cite_page_done += 1
                progress.progress(
                    min(cite_page_done / max(total_cite_pages, 1), 1.0),
                    text=f"Fetching citing papers... ({cite_page_done}/{total_cite_pages} pages)",
                )

        progress.empty()
        st.caption(f"Completed: {api_calls} API calls, {len(rows)} citing authors found")

    if not rows:
        return None, author_profile

    df = pd.DataFrame(rows)
    return df, author_profile


def _get_disk_cache_path(scholar_id: str) -> str:
    """Return the file path for the on-disk citation cache for a scholar ID.

    Args:
        scholar_id: The Google Scholar user ID.

    Returns:
        Absolute path to the cached CSV file.
    """
    return os.path.join(_CACHE_DIR, f"{scholar_id}.csv")


def _fetch_with_retry(scholar_id: str) -> pd.DataFrame | None:
    """Attempt to fetch citation data with exponential backoff on rate limits.

    Retries up to ``_MAX_RETRIES`` times when Google Scholar blocks the
    request, waiting ``_BACKOFF_SECONDS[i]`` seconds between attempts.
    A Streamlit status area shows countdown progress during waits.

    Args:
        scholar_id: A valid Google Scholar user ID.

    Returns:
        A ``pandas.DataFrame`` of citation data, or ``None`` if all
        attempts failed.
    """
    temp_dir = tempfile.mkdtemp()
    csv_path = os.path.join(temp_dir, "citation_info.csv")
    map_path = os.path.join(temp_dir, "citation_map.html")

    for attempt in range(_MAX_RETRIES):
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
            is_rate_limit = "Cannot Fetch" in msg or "Google Scholar" in msg
            if is_rate_limit and attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_SECONDS[attempt]
                placeholder = st.empty()
                for remaining in range(wait, 0, -1):
                    placeholder.warning(
                        f"Rate-limited by Google Scholar. "
                        f"Retrying in {remaining}s "
                        f"(attempt {attempt + 2}/{_MAX_RETRIES})..."
                    )
                    time.sleep(1)
                placeholder.empty()
            elif is_rate_limit:
                st.error(
                    "Google Scholar is temporarily blocking requests (rate limit). "
                    "Please wait a few minutes and try again."
                )
                return None
            else:
                st.error(f"Error fetching data: {msg}")
                return None
    return None


@st.cache_data(show_spinner=False)
def generate_citation_data(scholar_id):
    """Fetch citation data and author profile from Google Scholar with disk caching.

    Uses a tiered strategy:
        1. **Disk cache** — returns instantly if data was previously fetched
           for this Scholar ID (persisted in ``.cache/citations/``).
        2. **SerpAPI** (preferred) — if a ``SERPAPI_KEY`` is configured in
           Streamlit secrets or environment, uses the official SerpAPI Google
           Scholar endpoints. No rate-limit issues. Also returns the author's
           profile summary.
        3. **citation-map scraping** (fallback) — if no SerpAPI key is set,
           falls back to direct Google Scholar scraping with automatic retry
           and exponential backoff (30s, 60s, 120s).

    Args:
        scholar_id: A valid Google Scholar user ID (e.g. ``"ABC123"``).

    Returns:
        A tuple ``(DataFrame, author_profile)`` where *author_profile* is
        a dict with the author's name, affiliation, interests, citation
        metrics, and co-authors (or ``None`` when using scraping fallback
        or disk cache).
    """
    cache_path = _get_disk_cache_path(scholar_id)
    author_profile = None

    if os.path.exists(cache_path):
        return pd.read_csv(cache_path), None

    # Try SerpAPI first if key is available
    api_key = _get_serpapi_key()
    if api_key:
        df, author_profile = _fetch_via_serpapi(scholar_id, api_key)
    else:
        df = _fetch_with_retry(scholar_id)

    if df is not None and not df.empty:
        df.to_csv(cache_path, index=False)

    return df, author_profile


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
    """Return sample citation data and a demo author profile for UI preview.

    Provides 20 synthetic records with realistic verbose affiliations (matching
    the format returned by SerpAPI author profiles) spanning institutions across
    North America, Europe, Asia, and Africa. Also returns a demo author profile
    so the profile summary section is exercised.

    Returns:
        A tuple ``(DataFrame, author_profile)`` matching the schema produced by
        ``generate_citation_data``.
    """
    co_authors = [
        {"name": "Alice Johnson", "affiliations": "Massachusetts Institute of Technology"},
        {"name": "Bob Smith", "affiliations": "Stanford University"},
        {"name": "Diana Chen", "affiliations": "University of Cambridge"},
        {"name": "George Tanaka", "affiliations": "University of Toronto"},
        {"name": "Qi Zhang", "affiliations": "Peking University"},
        {"name": "Marco Rossi", "affiliations": "University of Milan"},
        {"name": "Nina Johansson", "affiliations": "Karolinska Institute"},
        {"name": "Omar Hassan", "affiliations": "Cairo University"},
    ]

    # DataFrame: author + co-authors (same as real SerpAPI flow)
    rows = [{"citing author name": "Dr. Jane Researcher", "affiliation": "Stanford University"}]
    for ca in co_authors:
        rows.append({"citing author name": ca["name"], "affiliation": ca["affiliations"]})
    df = pd.DataFrame(rows)

    demo_profile = {
        "name": "Dr. Jane Researcher",
        "affiliations": "Stanford University",
        "email": "Verified email at stanford.edu",
        "interests": ["Machine Learning", "Data Science", "Bioinformatics", "Statistics"],
        "thumbnail": "https://ui-avatars.com/api/?name=Jane+Researcher&size=120&background=d97706&color=fff&rounded=true",
        "cited_by": {
            "table": [
                {"citations": {"all": 1250, "since_2021": 870}},
                {"h_index": {"all": 18, "since_2021": 14}},
                {"i10_index": {"all": 24, "since_2021": 19}},
            ],
            "graph": [],
        },
        "co_authors": co_authors,
        "articles": [
            {"title": "Deep Learning for Genomic Variant Classification", "year": "2023", "cited_by": 342},
            {"title": "Transformer Models in Protein Structure Prediction", "year": "2022", "cited_by": 289},
            {"title": "Statistical Methods for Single-Cell RNA Sequencing", "year": "2021", "cited_by": 215},
            {"title": "A Survey of Federated Learning in Healthcare", "year": "2023", "cited_by": 178},
            {"title": "Interpretable Machine Learning for Clinical Decision Support", "year": "2020", "cited_by": 156},
        ],
    }

    return df, demo_profile


# ── Results ───────────────────────────────────────────────────────────────────

# Persist results across reruns
if "result_df" not in st.session_state:
    st.session_state.result_df = None
    st.session_state.is_demo = False
    st.session_state.author_profile = None

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

_new_df = None

if demo_btn:
    _new_df, _demo_profile = get_demo_data()
    st.session_state.is_demo = True
    st.session_state.author_profile = _demo_profile
elif submitted and user_input:
    if not scholar_id:
        st.error("Could not detect a valid Scholar ID. Please check your input.")
    else:
        with st.spinner("Fetching citation data from Google Scholar..."):
            _new_df, _author_profile = generate_citation_data(scholar_id)
        if _author_profile:
            st.session_state.author_profile = _author_profile
        if _new_df is None or _new_df.empty:
            st.error("Could not fetch citation data. Please check the Scholar ID.")
            _new_df = None
        else:
            st.session_state.is_demo = False
elif submitted:
    st.warning("Please enter a Google Scholar ID or profile URL.")

if _new_df is not None and not _new_df.empty:
    st.session_state.result_df = _new_df
    _build_and_cache(_new_df)

if st.session_state.is_demo:
    st.info("Showing demo data to preview the UI.", icon="🧪")

df = st.session_state.result_df
cached_map_html = st.session_state.get("cached_map_html")
stats = st.session_state.get("cached_stats")

if df is not None and not df.empty and cached_map_html:
    st.divider()

    # Author Profile Summary
    _profile = st.session_state.get("author_profile")
    if _profile and _profile.get("name"):
        st.subheader("Author Profile")

        # Profile card
        _p_col1, _p_col2 = st.columns([1, 3])

        with _p_col1:
            if _profile.get("thumbnail"):
                st.image(_profile["thumbnail"], width=120)

        with _p_col2:
            st.markdown(f"### {_profile['name']}")
            if _profile.get("affiliations"):
                st.markdown(f"**{_profile['affiliations']}**")
            if _profile.get("email"):
                st.caption(_profile["email"])
            if _profile.get("interests"):
                st.markdown(
                    " ".join(f"`{i}`" for i in _profile["interests"])
                )

        # Citation metrics
        _cited_by = _profile.get("cited_by", {})
        _table = _cited_by.get("table", [])
        if _table:
            _m_cols = st.columns(len(_table))
            for _idx, _entry in enumerate(_table):
                _key = list(_entry.keys())[0]
                _vals = _entry[_key]
                _m_cols[_idx].metric(
                    _key.replace("_", " ").title(),
                    f"{_vals.get('all', 0):,}",
                    f"{_vals.get('since_2021', 0):,} since 2021",
                )

        # Co-authors & Articles side by side
        _co = _profile.get("co_authors", [])
        _articles = _profile.get("articles", [])
        _exp_left, _exp_right = st.columns(2)

        with _exp_left:
            if _co:
                with st.expander(f"Co-Authors ({len(_co)})", expanded=True):
                    for _ca in _co:
                        _aff_text = f" — {_ca['affiliations']}" if _ca.get("affiliations") else ""
                        st.markdown(f"- **{_ca['name']}**{_aff_text}")

        with _exp_right:
            if _articles:
                _cited_articles = [a for a in _articles if a.get("cited_by")]
                with st.expander(f"Top Articles ({len(_cited_articles)})", expanded=True):
                    for _art in sorted(_cited_articles, key=lambda x: x["cited_by"], reverse=True)[:10]:
                        _yr = f" ({_art['year']})" if _art.get("year") else ""
                        st.markdown(f"- **{_art['cited_by']}** cites — {_art['title'][:70]}{_yr}")

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
