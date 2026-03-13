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

## Project Structure

```
citation/
├── streamlit_app.py      # Main Streamlit web application
├── run.sh                # Quick-start script
├── requirements.txt      # Python dependencies
├── README.md             # This file
└── venv/                 # Virtual environment
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `streamlit` | Web application framework |
| `streamlit-folium` | Folium map integration for Streamlit |
| `folium` | Interactive map generation |
| `pandas` | Data manipulation |
| `geopy` | Geocoding affiliations |
| `citation-map` | Google Scholar data fetching |

## How It Works

1. **Input Parsing**: The app accepts either a raw Scholar ID or a full Google Scholar profile URL, automatically extracting the user ID.

2. **Data Collection**: The app uses the `citation-map` library (which wraps `scholarly`) to fetch citation data from Google Scholar for the given profile ID.

3. **Affiliation Extraction**: For each citing paper, the app extracts the authors and their institutional affiliations.

4. **Geocoding**: Affiliations are converted to geographic coordinates using:
   - A built-in cache of common universities
   - The Nominatim geocoding service (OpenStreetMap)

5. **Map Generation**: Coordinates are plotted on an interactive Folium map with:
   - Marker clustering for dense areas
   - Color-coded markers
   - Popups with author/affiliation details

6. **Export**: Users can download the map as a PNG image or the raw data as CSV.

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
