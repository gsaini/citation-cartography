# Citation Cartography

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Folium](https://img.shields.io/badge/Folium-77B829?style=for-the-badge&logo=leaflet&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![OpenStreetMap](https://img.shields.io/badge/OpenStreetMap-7EBC6F?style=for-the-badge&logo=openstreetmap&logoColor=white)
![Google Scholar](https://img.shields.io/badge/Google_Scholar-4285F4?style=for-the-badge&logo=googlescholar&logoColor=white)
![License MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

A web application that visualizes the global impact of your research by mapping where your Google Scholar citations come from around the world.

## Overview

Citation Cartography fetches citation data from Google Scholar and plots the geographic locations of citing authors' affiliations on an interactive world map. This helps researchers understand the global reach and impact of their work.

## Features

- **Interactive World Map**: Visualize citations on a Leaflet-based map with marker clustering and CartoDB Positron tiles
- **Flexible Input**: Accepts both a raw Google Scholar ID or a full profile URL
- **Real-time Data Fetching**: Pulls live citation data from Google Scholar
- **Geocoding**: Automatically converts institutional affiliations to geographic coordinates
- **Statistics Dashboard**: View total citations, mapped locations, and unique affiliations
- **Download Options**:
  - Export map as PNG image (requires Chrome)
  - Download citation data as CSV
- **Demo Mode**: Preview the full UI with sample data — no Scholar ID needed
- **Affiliation Browser**: Expandable list showing all citing institutions and authors

## Screenshots

### Main Interface
```
┌─────────────────────────────────────────────────────────┐
│            Citation Cartography                         │
│    See where your research resonates across the globe   │
├─────────────────────────────────────────────────────────┤
│  [Scholar ID or full profile URL________] [Generate]    │
├─────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────────┐             │
│  │   125   │  │   45    │  │     32      │             │
│  │Citations│  │ Mapped  │  │Affiliations │             │
│  └─────────┘  └─────────┘  └─────────────┘             │
├─────────────────────────────────────────────────────────┤
│                    [World Map]                          │
└─────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Setup

1. **Clone or download the repository**
   ```bash
   cd citation
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Running the App

```bash
./run.sh
```

Or manually:

```bash
source venv/bin/activate
streamlit run streamlit_app.py
```

Then open **http://localhost:8501** in your browser.

### Using the App

1. Enter your Google Scholar ID **or** paste the full profile URL in the input field
   - URL example: `https://scholar.google.com/citations?user=YOUR_ID&hl=en`
   - ID example: `YOUR_ID`
2. Click **Generate**
3. Wait for the data to be fetched and processed
4. Explore the interactive map
5. Download the map or data using the download buttons

## How to Find Your Google Scholar ID

1. Go to [Google Scholar](https://scholar.google.com)
2. Sign in and click on your profile
3. Copy the URL from your browser — you can paste the entire URL directly into the app:
   ```
   https://scholar.google.com/citations?user=XXXXXXXX&hl=en
   ```
   Or copy just the ID after `user=`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Streamlit Frontend                         │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  Input    │  │   Author     │  │  Stats   │  │  Affiliations │  │
│  │  Form     │  │   Profile    │  │  Metrics │  │  Browser      │  │
│  └────┬─────┘  └──────────────┘  └──────────┘  └───────────────┘  │
│       │                                                             │
│  ┌────▼──────────────────────────────────────────────────────────┐  │
│  │              Interactive Folium Map (Leaflet.js)              │  │
│  │         CartoDB Positron · MarkerCluster · html2canvas        │  │
│  └───────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                       Data Fetching Layer                           │
│                                                                     │
│   ┌─────────────┐    ┌──────────────┐    ┌─────────────────────┐   │
│   │  Disk Cache  │───▶│   SerpAPI    │───▶│  citation-map       │   │
│   │  .cache/     │    │  (1 API call)│    │  scraping (fallback)│   │
│   └─────────────┘    └──────┬───────┘    └──────────┬──────────┘   │
│         ▲                   │                       │               │
│         │          ┌────────▼────────┐     Exponential backoff      │
│         │          │ Single call:    │     (30s, 60s, 120s)        │
│         │          │ google_scholar_ │              │               │
│         │          │ author returns: │              │               │
│         │          │ · Profile       │              │               │
│         │          │ · Articles      │              │               │
│         │          │ · Co-authors    │              │               │
│         │          │   (w/ affils)   │              │               │
│         │          │ · Citation stats│              │               │
│         │          └────────┬────────┘              │               │
│         │                   │                       │               │
│         └───────────────────┴───────────────────────┘               │
│                         CSV cached per scholar_id                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                      Geocoding Pipeline                             │
│                                                                     │
│   ┌──────────────────┐    ┌──────────────┐    ┌─────────────────┐  │
│   │ _clean_affiliation│───▶│  Nominatim   │───▶│  In-Memory      │  │
│   │ (extract inst.   │    │  (OSM)       │    │  geocode_cache  │  │
│   │  from verbose    │    │  geocoder    │    │                 │  │
│   │  role strings)   │    └──────────────┘    └─────────────────┘  │
│   └──────────────────┘                                              │
│    Strips roles/titles      Tries each                              │
│    Splits on , and .        candidate                               │
│    Finds institution        until one                               │
│    keywords                 resolves                                │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User Input ──▶ extract_scholar_id() ──▶ generate_citation_data()
                                              │
                          ┌───────────────────┬┘
                          ▼                   ▼
                   Disk Cache?           SerpAPI / Scraper
                    (hit)                  (miss)
                      │                      │
                      ▼                      ▼
                  Load CSV          Fetch & cache CSV + author profile
                      │                      │
                      └──────────┬───────────┘
                                 ▼
                         create_styled_map()
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              Geocode      Build Folium   Compute
              affiliations   Map          stats
                    │            │            │
                    └────────────┼────────────┘
                                 ▼
                          Session State
                    (map HTML, stats, profile)
                                 │
                                 ▼
                         Render UI
                   (profile + map + exports)
```

## Project Structure

```
citation/
├── streamlit_app.py           # Main application (all logic in one file)
│   ├── extract_scholar_id()   #   URL/ID parsing
│   ├── _clean_affiliation()   #   Verbose affiliation → institution name
│   ├── geocode_affiliation()  #   Institution → lat/lng via Nominatim
│   ├── _fetch_via_serpapi()   #   SerpAPI 3-step fetch + author profile
│   ├── _fetch_with_retry()    #   citation-map scraping with backoff
│   ├── generate_citation_data()#  Tiered fetching: cache → API → scraper
│   ├── create_styled_map()    #   Folium map with markers + download btn
│   └── get_demo_data()        #   Synthetic data for Try Demo
├── tests/
│   ├── __init__.py
│   └── test_streamlit_app.py  # 46 unit tests (Streamlit mocked)
├── .streamlit/
│   ├── config.toml            # Theme configuration
│   └── secrets.toml           # SerpAPI key (gitignored)
├── .cache/citations/          # Disk-cached CSV per scholar ID (gitignored)
├── requirements.txt           # Python dependencies
├── run.sh                     # Quick-start script
├── .gitignore
└── README.md
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `streamlit` | Web application framework |
| `folium` | Interactive Leaflet map generation |
| `pandas` | Data manipulation and CSV I/O |
| `geopy` | Geocoding via Nominatim (OpenStreetMap) |
| `citation-map` | Google Scholar scraping (fallback) |
| `google-search-results` | SerpAPI client (preferred data source) |

## How It Works

1. **Input Parsing**: Accepts a raw Scholar ID or full Google Scholar profile URL — `extract_scholar_id()` handles both formats.

2. **Tiered Data Fetching** (`generate_citation_data`):
   - **Disk cache** — instant return if previously fetched (`.cache/citations/<id>.csv`)
   - **SerpAPI** (preferred) — **single API call** to `google_scholar_author` returns the author's profile, articles, co-authors (with affiliations), and citation stats. Co-author affiliations are used as map locations.
   - **citation-map scraping** (fallback) — direct Google Scholar scraping with exponential backoff retry (30s, 60s, 120s)

3. **Affiliation Cleaning** (`_clean_affiliation`): SerpAPI profiles return verbose strings like *"Associate Professor of Internal Medicine, Wayne State University"*. The cleaner extracts geocodable institution names by splitting on delimiters, stripping role/title prefixes, and detecting institution keywords.

4. **Geocoding** (`geocode_affiliation`): Each cleaned candidate is tried against the Nominatim geocoder (OpenStreetMap) until one resolves. Results are cached in memory.

5. **Map Generation** (`create_styled_map`): Coordinates are plotted on an interactive Folium map with marker clustering, color-coded markers, popups with author details, and a client-side "Download Map" button powered by `html2canvas`.

6. **Export**: Download the current map view as PNG (captures zoom/pan state) or the raw citation data as CSV.

## Limitations

- **Rate Limiting**: Google Scholar may temporarily block requests if too many are made. The app includes delays to mitigate this.
- **Geocoding Accuracy**: Some affiliations may not geocode correctly, especially for:
  - Abbreviated institution names
  - Non-English institution names
  - Generic titles without institution names
- **Processing Time**: Large profiles with many citations may take several minutes to process.

## Troubleshooting

### "Could not fetch citation data"
- Verify the Scholar ID or URL is correct
- Check your internet connection
- Google Scholar may be rate-limiting requests; wait a few minutes and try again

### Map shows few locations
- Some affiliations cannot be geocoded
- Generic affiliations like "Professor" or "Researcher" without institution names cannot be mapped

### App is slow
- Large profiles take longer to process
- Geocoding requires network requests which add latency
- Results are cached, so subsequent requests for the same profile are faster

## API Rate Limits

- **Google Scholar**: No official API; the app uses web scraping with delays
- **Nominatim (OpenStreetMap)**: Max 1 request per second (built-in delay)

## License

MIT License - Feel free to use, modify, and distribute.

## Acknowledgments

- [citation-map](https://github.com/scholar-citation-map/citation-map) - Core citation fetching library
- [Folium](https://python-visualization.github.io/folium/) - Interactive maps
- [Streamlit](https://streamlit.io/) - Web app framework
- [OpenStreetMap](https://www.openstreetmap.org/) - Map tiles and geocoding

---

**Note**: This tool is for research and educational purposes. Please respect Google Scholar's terms of service and use responsibly.
