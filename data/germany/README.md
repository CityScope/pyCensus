# Germany Census Data

This directory can contain downloaded Destatis Census 2022 data for pyCensus.
All data is cached in `~/.cache/pycensus/Germany/`.

## Quick Start

```python
from pycensus.germany.census2022 import load
gdf = load(regions="BW", level="district")
```

## Data Source
- Destatis: https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Zensus/_inhalt.html

## Notes
1. Destatis does not provide a REST API. Manual downloads required.
2. Variable codes are placeholders.
