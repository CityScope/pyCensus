# pyCensus

Common-schema census loaders for the [geohierarchy](../geohierarchy) package.

Each source (`pycensus.USA.acs`, `pycensus.USA.dhc`, `pycensus.USA.lodes`) loads
data into a plain `GeoDataFrame` with a `GEOID` column and prefixed attribute
columns, ready for `geohierarchy.GeoHierarchy.add_level`. Importing a source
registers a matching accessor, e.g.:

```python
import pycensus

gdf = pycensus.USA.acs.load(aoi=my_aoi, level="tract")
gdf.acs["population"]            # raw values
gdf.acs["population"].density    # value / geometry area (m2)
gdf.acs["poverty_below_1_00"].relative  # value / its registered total column
```

API keys are resolved from an explicit argument, then the environment, then
`api_keys.json` at the package root -- see `pycensus.api_keys.resolve_api_key`.
# pyCensus
