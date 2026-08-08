"""Common-schema column definitions for the 2020 Decennial Census DHC.

Technical aspects:
    Maps common cross-country wording (``population``, ``race_*``, ...) to
    Demographic and Housing Characteristics (DHC) file variable codes. DHC
    codes are exact counts (unlike ACS estimates), so no ``E``/``M`` suffix
    handling is needed.

Source:
    https://www.census.gov/programs-surveys/decennial-census/about/rdo/summary-files.html
    Variable codes: https://api.census.gov/data/2020/dec/dhc/variables.html
"""

from ...schema import ColumnSchema

SCHEMA = ColumnSchema(prefix="dhc")

# ---------------- population / housing ----------------
SCHEMA.add("population", ["P1_001N"])
SCHEMA.add("housing_units", ["H1_001N"], relative_to="population")

# ---------------- gender ----------------
SCHEMA.add("population_male", ["P12_002N"], relative_to="population")
SCHEMA.add("population_female", ["P12_026N"], relative_to="population")

# ---------------- age ----------------
SCHEMA.add(
    "population_under_18",
    [
        "P12_003N", "P12_004N", "P12_005N", "P12_006N",
        "P12_027N", "P12_028N", "P12_029N", "P12_030N",
    ],
    relative_to="population",
)
SCHEMA.add(
    "population_18_to_64",
    [
        "P12_007N", "P12_008N", "P12_009N", "P12_010N", "P12_011N", "P12_012N",
        "P12_013N", "P12_014N", "P12_015N", "P12_016N", "P12_017N", "P12_018N", "P12_019N",
        "P12_031N", "P12_032N", "P12_033N", "P12_034N", "P12_035N", "P12_036N",
        "P12_037N", "P12_038N", "P12_039N", "P12_040N", "P12_041N", "P12_042N", "P12_043N",
    ],
    relative_to="population",
)
SCHEMA.add(
    "population_over_65",
    [
        "P12_020N", "P12_021N", "P12_022N", "P12_023N", "P12_024N", "P12_025N",
        "P12_044N", "P12_045N", "P12_046N", "P12_047N", "P12_048N", "P12_049N",
    ],
    relative_to="population",
)

# ---------------- race / ethnicity ----------------
SCHEMA.add("population_white", ["P3_002N"], relative_to="population")
SCHEMA.add("population_black", ["P3_003N"], relative_to="population")
SCHEMA.add("population_native", ["P3_004N"], relative_to="population")
SCHEMA.add("population_asian", ["P3_005N"], relative_to="population")
SCHEMA.add("population_other_race", ["P3_006N", "P3_007N", "P3_008N"], relative_to="population")
SCHEMA.add("population_hispanic", ["P5_010N"], relative_to="population")
