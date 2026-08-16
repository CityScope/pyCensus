# Israel Census Data

This directory can contain downloaded CBS Census 2022 data for use with pyCensus, but **it is no longer required**. Starting with the cache-based implementation, all data is automatically downloaded to and cached in the platform-specific cache directory (e.g., `~/.cache/pycensus/Israel/` on Linux).

**Note**: This `data/israel/` directory is kept for backward compatibility and for users who want to manually organize their data. For new users, the automatic cache system is recommended.

## Quick Start

```python
from pycensus.israel.census2022 import load

# Load locality-level data for a specific district
gdf = load(regions="Tel Aviv", level="locality")

# Load for multiple districts
gdf = load(regions=["Tel Aviv", "Jerusalem"], level="locality")

# Load at district level
gdf = load(regions="1", level="district")  # Northern district by code
```

## Data Sources

- **Census 2022 (Census of Population and Housing)**: https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx
- **Geographic Information**: https://www.cbs.gov.il/en/statistics/pages/geographic-information.aspx

## Geographic Levels

- **Nation**: Country-level data (Israel)
- **District**: 6 main districts + Judea and Samaria
- **Sub-district**: Within districts (nafa)
- **Locality**: Cities, towns, villages, municipalities
- **Statistical Area**: Census statistical areas
- **Street**: Street-level
- **Block**: Building blocks

## Notes

1. CBS does not provide a public API for data downloads. Files must be downloaded manually.
2. Variable codes in the schema are placeholders and should be verified against actual data.
