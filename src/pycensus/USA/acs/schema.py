"""Common-schema column definitions for the ACS 5-year estimates.

Technical aspects:
    Maps common cross-country wording (``population``, ``income``, ...) to
    ACS detailed-table variable codes. Each code implicitly gets an ``"E"``
    (estimate) suffix in :mod:`pycensus.USA.acs.loader` -- margins of error
    (``"M"`` suffix) are not fetched.

Source:
    ACS 5-year detailed tables: https://www.census.gov/programs-surveys/acs.html
    Variable codes looked up via https://api.census.gov/data/2023/acs/acs5/variables.html
"""

from ...schema import ColumnSchema

SCHEMA = ColumnSchema(prefix="acs")

# ---------------- population / households ----------------
SCHEMA.add("population", ["B01003_001"])
SCHEMA.add("households", ["B25044_001"], relative_to="population")
SCHEMA.add("households_owner", ["B25003_002"], relative_to="households")
SCHEMA.add("households_renter", ["B25003_003"], relative_to="households")
SCHEMA.add("household_size_mean", ["B25010_001"], agg="mean", weight_by="households")

# ---------------- income / poverty ----------------
SCHEMA.add("population_16plus", ["B23025_001"], relative_to="population")
SCHEMA.add("income_median_household", ["B19013_001"], agg="mean", weight_by="households")
SCHEMA.add("income_mean_capita", ["B19301_001"], agg="mean", weight_by="population")
SCHEMA.add("poverty_population", ["C17002_001"])
SCHEMA.add(
    "poverty_below_1_00",
    ["C17002_002", "C17002_003"],
    relative_to="poverty_population",
)
SCHEMA.add("labor_force", ["B23025_003"], relative_to="population_16plus")
SCHEMA.add("unemployed", ["B23025_005"], relative_to="labor_force")

# ---------------- commuting (workers by residence) ----------------
SCHEMA.add("workers", ["B08301_001"])
SCHEMA.add("workers_car", ["B08301_002"], relative_to="workers")
SCHEMA.add("workers_transit", ["B08301_010"], relative_to="workers")
SCHEMA.add("workers_walk", ["B08301_019"], relative_to="workers")
SCHEMA.add("workers_bike", ["B08301_018"], relative_to="workers")
SCHEMA.add("commute_time_mean", ["B08303_001"], agg="mean", weight_by="workers")

# ---------------- vehicles ----------------
SCHEMA.add("vehicles_households_0", ["B25044_003", "B25044_010"], relative_to="households")

# ---------------- housing cost / rent burden ----------------
# B25070: gross rent as a % of household income, renter-occupied units with
# income computed. "Rent burdened" is the standard equity threshold of >=30%
# of income going to rent (bins 30-34.9, 35-39.9, 40-49.9, 50+).
SCHEMA.add("rent_burden_population", ["B25070_001"])
SCHEMA.add(
    "rent_burdened",
    ["B25070_007", "B25070_008", "B25070_009", "B25070_010"],
    relative_to="rent_burden_population",
)
SCHEMA.add("rent_median_gross", ["B25064_001"], agg="mean", weight_by="households_renter")

# ---------------- education ----------------
# B15003: educational attainment for population 25 years and over.
SCHEMA.add("population_25plus", ["B15003_001"], relative_to="population")
SCHEMA.add(
    "education_less_than_hs",
    [f"B15003_{i:03d}" for i in range(2, 17)],
    relative_to="population_25plus",
)
SCHEMA.add(
    "education_bachelors_plus",
    ["B15003_022", "B15003_023", "B15003_024", "B15003_025"],
    relative_to="population_25plus",
)
