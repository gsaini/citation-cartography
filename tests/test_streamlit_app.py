"""Unit tests for Citation Cartography (streamlit_app.py).

Tests cover the pure-logic helper functions that can be validated without
a running Streamlit server: Scholar ID extraction, geocoding, demo data
generation, and styled-map construction.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Stub out Streamlit before importing the app module so we can test helpers
# without launching a Streamlit server.
# ---------------------------------------------------------------------------

_ctx = MagicMock()

_st_mock = MagicMock()

def _cache_data_decorator(*args, show_spinner=True, **kwargs):
    """Allow @st.cache_data and @st.cache_data(show_spinner=False)."""
    if args and callable(args[0]):
        return args[0]
    return lambda fn: fn

_st_mock.cache_data = _cache_data_decorator
_st_mock.set_page_config = MagicMock()
_st_mock.html = MagicMock()
class _SessionState(dict):
    """Dict that also supports attribute access (like st.session_state)."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)
    def __setattr__(self, key, value):
        self[key] = value
    def __delattr__(self, key):
        del self[key]

_st_mock.session_state = _SessionState()
# st.columns must return the right number of mocks for unpacking
_st_mock.columns = lambda cols, **kw: [MagicMock() for _ in (cols if isinstance(cols, list) else range(cols))]
# st.form returns a context manager
_st_mock.form = MagicMock(return_value=_ctx)
# st.form_submit_button returns False by default
_st_mock.form_submit_button = MagicMock(return_value=False)
# st.spinner returns a context manager
_st_mock.spinner = MagicMock(return_value=_ctx)
# st.text_input returns an empty string by default
_st_mock.text_input = MagicMock(return_value="")
# st.divider, st.write, st.subheader, etc. — no-ops
_st_mock.divider = MagicMock()
_st_mock.write = MagicMock()
_st_mock.subheader = MagicMock()
_st_mock.metric = MagicMock()
_st_mock.expander = MagicMock(return_value=_ctx)
_st_mock.dataframe = MagicMock()
_st_mock.download_button = MagicMock()
_st_mock.info = MagicMock()
_st_mock.error = MagicMock()
_st_mock.warning = MagicMock()
_st_mock.success = MagicMock()

sys.modules["streamlit"] = _st_mock
sys.modules["streamlit.components"] = MagicMock()
sys.modules["streamlit.components.v1"] = MagicMock()
sys.modules["streamlit_folium"] = MagicMock()

# Now import the helpers under test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from streamlit_app import (
    extract_scholar_id,
    geocode_affiliation,
    get_demo_data,
    create_styled_map,
)


# ═══════════════════════════════════════════════════════════════════════════
#  extract_scholar_id
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractScholarId:
    """Tests for ``extract_scholar_id``."""

    # ── Happy-path: full URLs ────────────────────────────────────────────

    def test_full_url_basic(self):
        """Should extract the user param from a standard Scholar URL."""
        url = "https://scholar.google.com/citations?user=ABC123XYZ&hl=en"
        assert extract_scholar_id(url) == "ABC123XYZ"

    def test_full_url_no_hl(self):
        """Should work when the ``hl`` query param is absent."""
        url = "https://scholar.google.com/citations?user=XYZ789"
        assert extract_scholar_id(url) == "XYZ789"

    def test_full_url_extra_params(self):
        """Should extract user ID even when extra query params are present."""
        url = "https://scholar.google.com/citations?user=MYID1234&hl=en&oi=ao"
        assert extract_scholar_id(url) == "MYID1234"

    def test_http_url(self):
        """Should handle ``http://`` (non-TLS) URLs."""
        url = "http://scholar.google.com/citations?user=HTTPSID1"
        assert extract_scholar_id(url) == "HTTPSID1"

    def test_country_specific_scholar_url(self):
        """Should handle country-specific Scholar domains like scholar.google.co.in."""
        url = "https://scholar.google.co.in/citations?user=INDIAID1&hl=en"
        assert extract_scholar_id(url) == "INDIAID1"

    # ── Happy-path: raw IDs ──────────────────────────────────────────────

    def test_raw_id_alphanumeric(self):
        """Should accept a plain alphanumeric Scholar ID."""
        assert extract_scholar_id("ABC123XYZ") == "ABC123XYZ"

    def test_raw_id_with_underscores(self):
        """Should accept IDs containing underscores."""
        assert extract_scholar_id("A_B-C_123") == "A_B-C_123"

    def test_raw_id_with_hyphens(self):
        """Should accept IDs containing hyphens."""
        assert extract_scholar_id("abcd-1234") == "abcd-1234"

    def test_raw_id_min_length(self):
        """Should accept an 8-character ID (minimum length)."""
        assert extract_scholar_id("ABCD1234") == "ABCD1234"

    def test_raw_id_max_length(self):
        """Should accept a 20-character ID (maximum length)."""
        assert extract_scholar_id("A" * 20) == "A" * 20

    # ── Whitespace handling ──────────────────────────────────────────────

    def test_leading_trailing_whitespace(self):
        """Should strip leading/trailing whitespace before processing."""
        assert extract_scholar_id("  ABC123XYZ  ") == "ABC123XYZ"

    def test_url_with_whitespace(self):
        """Should strip whitespace around a URL."""
        url = "  https://scholar.google.com/citations?user=XYZ789  "
        assert extract_scholar_id(url) == "XYZ789"

    # ── Edge cases / invalid input ───────────────────────────────────────

    def test_empty_string(self):
        """Should return None for an empty string."""
        assert extract_scholar_id("") is None

    def test_whitespace_only(self):
        """Should return None for whitespace-only input."""
        assert extract_scholar_id("   ") is None

    def test_too_short_id(self):
        """Should return None for IDs shorter than 8 characters."""
        assert extract_scholar_id("AB12") is None

    def test_too_long_id(self):
        """Should return None for IDs longer than 20 characters."""
        assert extract_scholar_id("A" * 21) is None

    def test_url_without_user_param(self):
        """Should return None for a Scholar URL missing the user param."""
        url = "https://scholar.google.com/citations?hl=en"
        assert extract_scholar_id(url) is None

    def test_non_scholar_url_with_user_param(self):
        """Should still extract user= from non-Scholar URLs (fallback regex)."""
        url = "https://example.com/page?user=ABC123XYZ"
        assert extract_scholar_id(url) == "ABC123XYZ"

    def test_non_scholar_url_without_user_param(self):
        """Should return None for a non-Scholar URL with no user param."""
        url = "https://example.com/page?id=something"
        assert extract_scholar_id(url) is None

    def test_partial_fragment_with_user(self):
        """Should extract ID from a fragment like ``user=XYZ``."""
        assert extract_scholar_id("user=ABC12345") == "ABC12345"


# ═══════════════════════════════════════════════════════════════════════════
#  geocode_affiliation
# ═══════════════════════════════════════════════════════════════════════════

class TestGeocodeAffiliation:
    """Tests for ``geocode_affiliation``."""

    def setup_method(self):
        """Clear the geocode cache before each test."""
        from streamlit_app import geocode_cache
        geocode_cache.clear()

    def test_cleaned_candidate_geocodes(self):
        """Should extract institution name and geocode it when raw string fails."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 42.35
        mock_location.longitude = -83.05

        # Raw string fails, cleaned candidate "Wayne State University" succeeds
        mock_geolocator.geocode.side_effect = lambda q, **kw: (
            mock_location if "Wayne State University" in q else None
        )

        coords = geocode_affiliation(
            "Associate Professor of Internal Medicine, Wayne State University",
            mock_geolocator,
        )
        assert coords == (42.35, -83.05)

    def test_verbose_affiliation_tries_multiple_candidates(self):
        """Should try progressively cleaned candidates until one works."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 43.66
        mock_location.longitude = -79.39

        mock_geolocator.geocode.side_effect = lambda q, **kw: (
            mock_location if q == "University of Toronto" else None
        )

        coords = geocode_affiliation(
            "Professor, Anesthesia, University Health Network, University of Toronto",
            mock_geolocator,
        )
        assert coords == (43.66, -79.39)

    def test_simple_affiliation_geocodes_directly(self):
        """Simple institution names should geocode on the first try."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 37.42
        mock_location.longitude = -122.17
        mock_geolocator.geocode.return_value = mock_location

        coords = geocode_affiliation("Stanford University", mock_geolocator)
        assert coords == (37.42, -122.17)
        mock_geolocator.geocode.assert_called_once_with("Stanford University", timeout=10)

    def test_nominatim_geocodes_simple_name(self):
        """Should geocode a simple institution name via Nominatim."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 48.8566
        mock_location.longitude = 2.3522
        mock_geolocator.geocode.return_value = mock_location

        coords = geocode_affiliation("Sorbonne University", mock_geolocator)
        assert coords == (48.8566, 2.3522)

    def test_nominatim_returns_none(self):
        """Should return None when Nominatim cannot resolve the affiliation."""
        mock_geolocator = MagicMock()
        mock_geolocator.geocode.return_value = None

        coords = geocode_affiliation("Unknown Lab XYZ", mock_geolocator)
        assert coords is None

    def test_nominatim_timeout(self):
        """Should return None on GeocoderTimedOut and cache the failure."""
        from geopy.exc import GeocoderTimedOut

        mock_geolocator = MagicMock()
        mock_geolocator.geocode.side_effect = GeocoderTimedOut("timeout")

        coords = geocode_affiliation("Remote Institute", mock_geolocator)
        assert coords is None

    def test_result_is_cached(self):
        """Subsequent calls for the same affiliation should use the cache."""
        mock_geolocator = MagicMock()
        mock_location = MagicMock()
        mock_location.latitude = 51.5074
        mock_location.longitude = -0.1278
        mock_geolocator.geocode.return_value = mock_location

        geocode_affiliation("University of London", mock_geolocator)
        geocode_affiliation("University of London", mock_geolocator)

        # Nominatim should only have been called once
        assert mock_geolocator.geocode.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════
#  get_demo_data
# ═══════════════════════════════════════════════════════════════════════════

class TestGetDemoData:
    """Tests for ``get_demo_data``."""

    def test_returns_tuple(self):
        """Should return a (DataFrame, profile) tuple."""
        result = get_demo_data()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_dataframe(self):
        """Should return a pandas DataFrame as the first element."""
        df, _ = get_demo_data()
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self):
        """Should contain the columns expected by the rest of the app."""
        df, _ = get_demo_data()
        assert "citing author name" in df.columns
        assert "affiliation" in df.columns

    def test_has_records(self):
        """Should contain at least one record."""
        df, _ = get_demo_data()
        assert len(df) > 0

    def test_no_null_values(self):
        """All demo records should have non-null values."""
        df, _ = get_demo_data()
        assert df.notna().all().all()

    def test_unique_authors(self):
        """All demo author names should be unique."""
        df, _ = get_demo_data()
        assert df["citing author name"].is_unique

    def test_multiple_affiliations(self):
        """Demo data should span multiple institutions."""
        df, _ = get_demo_data()
        assert df["affiliation"].nunique() >= 5

    def test_profile_has_required_keys(self):
        """Demo profile should contain name, affiliations, and cited_by."""
        _, profile = get_demo_data()
        assert isinstance(profile, dict)
        assert "name" in profile
        assert "affiliations" in profile
        assert "cited_by" in profile
        assert "co_authors" in profile


# ═══════════════════════════════════════════════════════════════════════════
#  create_styled_map
# ═══════════════════════════════════════════════════════════════════════════

def _mock_geocode(affiliation, geolocator):
    """Deterministic geocode stub for map tests — returns fixed coords per affiliation."""
    _coords = {
        "MIT": (42.36, -71.09),
        "Stanford University": (37.42, -122.17),
        "Harvard University": (42.37, -71.12),
        "Yale University": (41.31, -72.92),
        "Oxford University": (51.75, -1.25),
    }
    return _coords.get(affiliation)


class TestCreateStyledMap:
    """Tests for ``create_styled_map``."""

    def setup_method(self):
        """Clear geocode cache before each test."""
        from streamlit_app import geocode_cache
        geocode_cache.clear()

    def _make_df(self, affiliations, authors=None):
        """Helper to build a citation DataFrame."""
        if authors is None:
            authors = [f"Author {i}" for i in range(len(affiliations))]
        return pd.DataFrame({
            "citing author name": authors,
            "affiliation": affiliations,
        })

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_returns_map_and_stats(self, _mock):
        """Should return a folium.Map and a stats dict for valid data."""
        df = self._make_df(["MIT", "Stanford University"])
        m, stats = create_styled_map(df)

        assert m is not None
        assert isinstance(stats, dict)
        assert "total_citations" in stats
        assert "mapped_locations" in stats
        assert "affiliations" in stats

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_stats_total_citations(self, _mock):
        """total_citations should equal the row count of the input DataFrame."""
        df = self._make_df(["MIT", "Harvard University", "Yale University"])
        _, stats = create_styled_map(df)
        assert stats["total_citations"] == 3

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_stats_mapped_locations(self, _mock):
        """mapped_locations should count successfully geocoded affiliations."""
        df = self._make_df(["MIT", "Stanford University"])
        _, stats = create_styled_map(df)
        assert stats["mapped_locations"] == 2

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_stats_affiliations_list(self, _mock):
        """Each geocoded affiliation should appear in the affiliations list."""
        df = self._make_df(["MIT", "Oxford University"])
        _, stats = create_styled_map(df)
        names = [a["name"] for a in stats["affiliations"]]
        assert "MIT" in names
        assert "Oxford University" in names

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_affiliation_has_coords(self, _mock):
        """Each affiliation record should include lat/lng coordinates."""
        df = self._make_df(["MIT"])
        _, stats = create_styled_map(df)
        affil = stats["affiliations"][0]
        assert "lat" in affil and "lng" in affil
        assert isinstance(affil["lat"], float)
        assert isinstance(affil["lng"], float)

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_affiliation_has_authors(self, _mock):
        """Each affiliation record should list its authors."""
        df = self._make_df(
            ["MIT", "MIT"],
            ["Alice", "Bob"],
        )
        _, stats = create_styled_map(df)
        affil = stats["affiliations"][0]
        assert set(affil["authors"]) == {"Alice", "Bob"}

    def test_empty_after_filtering(self):
        """Should return (None, {}) when all affiliations are 'No_author_found'."""
        df = self._make_df(["No_author_found", "No_author_found"])
        m, stats = create_styled_map(df)
        assert m is None
        assert stats == {}

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_null_affiliations_filtered(self, _mock):
        """Rows with NaN affiliations should be excluded, not crash."""
        df = self._make_df(["MIT", None], ["Alice", "Bob"])
        m, stats = create_styled_map(df)
        assert m is not None
        assert stats["mapped_locations"] == 1

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_map_html_contains_download_button(self, _mock):
        """The generated map HTML should contain the Download Map control."""
        df = self._make_df(["MIT"])
        m, _ = create_styled_map(df)
        html = m._repr_html_()
        assert "html2canvas" in html
        assert "Download Map" in html

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_map_html_contains_leaflet(self, _mock):
        """The generated map HTML should include Leaflet assets."""
        df = self._make_df(["MIT"])
        m, _ = create_styled_map(df)
        html = m._repr_html_()
        assert "leaflet" in html.lower()

    @patch("streamlit_app.geocode_affiliation", side_effect=_mock_geocode)
    def test_duplicate_affiliations_grouped(self, _mock):
        """Multiple rows with the same affiliation should produce one marker."""
        df = self._make_df(
            ["MIT", "MIT", "MIT"],
            ["Alice", "Bob", "Charlie"],
        )
        _, stats = create_styled_map(df)
        assert stats["mapped_locations"] == 1
        assert len(stats["affiliations"]) == 1
        assert len(stats["affiliations"][0]["authors"]) == 3
