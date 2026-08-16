"""Common-schema column definitions for Israel Census 2022.

Technical aspects:
    Maps common cross-country wording (``population``, ``income``, ...) to
    CBS Census 2022 variable codes. Unlike the US ACS which uses letter
    codes (B01003_001), CBS data uses codes that we map to the common schema.

    The Census 2022 (Census of Population and Housing) includes:
    - Person-level data: demographics, education, employment, migration
    - Household-level data: composition, income, housing conditions
    - Housing-level data: characteristics, amenities, ownership

    For aggregated data, we use CBS's tabulated results which provide
    counts at various geographic levels (nation, district, subdistrict, locality).

    Note: CBS variable codes may vary depending on the specific dataset and
    aggregation level. The codes below are placeholders based on typical CBS
    variable naming conventions and should be verified against actual data files.

Source:
    CBS Census 2022: https://www.cbs.gov.il/en/subjects/pages/census-of-population-and-housing.aspx
"""

from ...schema import ColumnSchema

SCHEMA = ColumnSchema(prefix="census2022")

# ---------------- Population / Households ----------------
SCHEMA.add("population", ["TOTAL_POP"])  # Total population
SCHEMA.add("population_male", ["POP_MALE"], relative_to="population")
SCHEMA.add("population_female", ["POP_FEMALE"], relative_to="population")

# Age groups (CBS uses various age groupings)
SCHEMA.add("population_0_4", ["POP_0_4"], relative_to="population")
SCHEMA.add("population_5_9", ["POP_5_9"], relative_to="population")
SCHEMA.add("population_10_14", ["POP_10_14"], relative_to="population")
SCHEMA.add("population_15_17", ["POP_15_17"], relative_to="population")
SCHEMA.add("population_18_24", ["POP_18_24"], relative_to="population")
SCHEMA.add("population_25_34", ["POP_25_34"], relative_to="population")
SCHEMA.add("population_35_44", ["POP_35_44"], relative_to="population")
SCHEMA.add("population_45_54", ["POP_45_54"], relative_to="population")
SCHEMA.add("population_55_64", ["POP_55_64"], relative_to="population")
SCHEMA.add("population_65_74", ["POP_65_74"], relative_to="population")
SCHEMA.add("population_75_84", ["POP_75_84"], relative_to="population")
SCHEMA.add("population_85plus", ["POP_85_PLUS"], relative_to="population")

# Broad age groups
SCHEMA.add("population_0_17", ["POP_0_17"], relative_to="population")
SCHEMA.add("population_18_29", ["POP_18_29"], relative_to="population")
SCHEMA.add("population_30_44", ["POP_30_44"], relative_to="population")
SCHEMA.add("population_45_64", ["POP_45_64"], relative_to="population")
SCHEMA.add("population_65plus", ["POP_65_PLUS"], relative_to="population")

# Median age
SCHEMA.add("age_median", ["AGE_MEDIAN"], agg="mean", weight_by="population")

# Households
SCHEMA.add("households", ["TOTAL_HH"])
SCHEMA.add("household_size_mean", ["HH_SIZE_AVG"], agg="mean", weight_by="households")

# Population density
SCHEMA.add("population_density", ["POP_DENSITY"], agg="mean", weight_by="population")

# ---------------- Gender / Sex ----------------
SCHEMA.add("sex_ratio", ["SEX_RATIO"], agg="mean", weight_by="population")

# ---------------- Ethnicity / Religion ----------------
# In Israel, religion is a key demographic category
SCHEMA.add("population_jewish", ["POP_JEWISH"], relative_to="population")
SCHEMA.add("population_arab", ["POP_ARAB"], relative_to="population")
SCHEMA.add("population_other", ["POP_OTHER"], relative_to="population")

# Jewish population by origin
SCHEMA.add("population_jewish_israel_born", ["POP_JEW_ISRAEL_BORN"], relative_to="population_jewish")
SCHEMA.add("population_jewish_asia_africa", ["POP_JEW_ASIA_AFRICA"], relative_to="population_jewish")
SCHEMA.add("population_jewish_europe_america", ["POP_JEW_EUROPE_AMERICA"], relative_to="population_jewish")
SCHEMA.add("population_jewish_former_ussr", ["POP_JEW_FORMER_USSR"], relative_to="population_jewish")

# Arab population by religion
SCHEMA.add("population_arab_muslim", ["POP_ARAB_MUSLIM"], relative_to="population_arab")
SCHEMA.add("population_arab_christian", ["POP_ARAB_CHRST"], relative_to="population_arab")
SCHEMA.add("population_arab_druze", ["POP_ARAB_DRUZE"], relative_to="population_arab")

# Religion breakdown
SCHEMA.add("population_muslim", ["POP_MUSLIM"], relative_to="population")
SCHEMA.add("population_christian", ["POP_CHRST"], relative_to="population")
SCHEMA.add("population_druze", ["POP_DRUZE"], relative_to="population")
SCHEMA.add("population_no_religion", ["POP_NO_RELIG"], relative_to="population")

# ---------------- Immigration ----------------
# Year of immigration categories
SCHEMA.add("population_born_in_israel", ["POP_BORN_ISRAEL"], relative_to="population")
SCHEMA.add("population_immigrated", ["POP_IMMIGRATED"], relative_to="population")
SCHEMA.add("population_immigrated_before_1948", ["POP_IMM_BEFORE_1948"], relative_to="population_immigrated")
SCHEMA.add("population_immigrated_1948_1959", ["POP_IMM_1948_1959"], relative_to="population_immigrated")
SCHEMA.add("population_immigrated_1960_1969", ["POP_IMM_1960_1969"], relative_to="population_immigrated")
SCHEMA.add("population_immigrated_1970_1979", ["POP_IMM_1970_1979"], relative_to="population_immigrated")
SCHEMA.add("population_immigrated_1980_1989", ["POP_IMM_1980_1989"], relative_to="population_immigrated")
SCHEMA.add("population_immigrated_1990_1999", ["POP_IMM_1990_1999"], relative_to="population_immigrated")
SCHEMA.add("population_immigrated_2000_2009", ["POP_IMM_2000_2009"], relative_to="population_immigrated")
SCHEMA.add("population_immigrated_2010_2019", ["POP_IMM_2010_2019"], relative_to="population_immigrated")
SCHEMA.add("population_immigrated_2020_2022", ["POP_IMM_2020_2022"], relative_to="population_immigrated")

# Continent of origin for immigrants
SCHEMA.add("immigrants_africa", ["IMM_AFRICA"], relative_to="population_immigrated")
SCHEMA.add("immigrants_asia", ["IMM_ASIA"], relative_to="population_immigrated")
SCHEMA.add("immigrants_europe", ["IMM_EUROPE"], relative_to="population_immigrated")
SCHEMA.add("immigrants_america", ["IMM_AMERICA"], relative_to="population_immigrated")
SCHEMA.add("immigrants_oceania", ["IMM_OCEANIA"], relative_to="population_immigrated")

# ---------------- Education ----------------
SCHEMA.add("population_15plus", ["POP_15_PLUS"], relative_to="population")
SCHEMA.add("population_18plus", ["POP_18_PLUS"], relative_to="population")
SCHEMA.add("population_20plus", ["POP_20_PLUS"], relative_to="population")

# Educational attainment for population 15+
SCHEMA.add("population_no_schooling", ["POP_NO_SCHOOL"], relative_to="population_15plus")
SCHEMA.add("population_1_8_years", ["POP_1_8_YRS"], relative_to="population_15plus")
SCHEMA.add("population_9_12_years", ["POP_9_12_YRS"], relative_to="population_15plus")
SCHEMA.add("population_13_16_years", ["POP_13_16_YRS"], relative_to="population_15plus")
SCHEMA.add("education_post_secondary", ["POP_POST_SEC"], relative_to="population_15plus")
SCHEMA.add("education_academic", ["POP_ACADEMIC"], relative_to="population_15plus")
SCHEMA.add("education_vocational", ["POP_VOCATIONAL"], relative_to="population_15plus")

# Current education status
SCHEMA.add("population_studying", ["POP_STUDYING"], relative_to="population_15plus")
SCHEMA.add("population_not_studying", ["POP_NOT_STUDYING"], relative_to="population_15plus")

# ---------------- Marital Status ----------------
SCHEMA.add("population_single", ["POP_SINGLE"], relative_to="population_15plus")
SCHEMA.add("population_married", ["POP_MARRIED"], relative_to="population_15plus")
SCHEMA.add("population_divorced", ["POP_DIVORCED"], relative_to="population_15plus")
SCHEMA.add("population_widowed", ["POP_WIDOWED"], relative_to="population_15plus")

# ---------------- Income / Employment ----------------
# Population 15+ in labor force
SCHEMA.add("labor_force", ["LABOR_FORCE"], relative_to="population_15plus")
SCHEMA.add("employed", ["EMPLOYED"], relative_to="labor_force")
SCHEMA.add("unemployed", ["UNEMPLOYED"], relative_to="labor_force")
SCHEMA.add("unemployment_rate", ["UNEMPL_RATE"], agg="mean", weight_by="labor_force")

# Employment by sector
SCHEMA.add("employed_agriculture", ["EMP_AGRI"], relative_to="employed")
SCHEMA.add("employed_industry", ["EMP_INDUS"], relative_to="employed")
SCHEMA.add("employed_construction", ["EMP_CONST"], relative_to="employed")
SCHEMA.add("employed_commerce", ["EMP_COMMERCE"], relative_to="employed")
SCHEMA.add("employed_transport", ["EMP_TRANSPORT"], relative_to="employed")
SCHEMA.add("employed_finance", ["EMP_FINANCE"], relative_to="employed")
SCHEMA.add("employed_education", ["EMP_EDUCATION"], relative_to="employed")
SCHEMA.add("employed_health", ["EMP_HEALTH"], relative_to="employed")
SCHEMA.add("employed_services", ["EMP_SERVICES"], relative_to="employed")
SCHEMA.add("employed_public_admin", ["EMP_PUB_ADMIN"], relative_to="employed")

# Household income
SCHEMA.add("income_median_household", ["INC_MEDIAN_HH"], agg="mean", weight_by="households")
SCHEMA.add("income_mean_household", ["INC_MEAN_HH"], agg="mean", weight_by="households")
SCHEMA.add("income_per_capita", ["INC_PER_CAPITA"], agg="mean", weight_by="population")

# Income sources
SCHEMA.add("households_income_work", ["HH_INC_WORK"], relative_to="households")
SCHEMA.add("households_income_business", ["HH_INC_BUSINESS"], relative_to="households")
SCHEMA.add("households_income_property", ["HH_INC_PROPERTY"], relative_to="households")
SCHEMA.add("households_income_pensions", ["HH_INC_PENSIONS"], relative_to="households")
SCHEMA.add("households_income_transfers", ["HH_INC_TRANSFERS"], relative_to="households")

# ---------------- Housing / Tenure ----------------
# Housing tenure
SCHEMA.add("households_owner", ["HH_OWNER"], relative_to="households")
SCHEMA.add("households_renter", ["HH_RENTER"], relative_to="households")
SCHEMA.add("households_rent_free", ["HH_RENT_FREE"], relative_to="households")
SCHEMA.add("households_other_tenure", ["HH_OTHER_TENURE"], relative_to="households")

# Housing type
SCHEMA.add("households_house", ["HH_HOUSE"], relative_to="households")
SCHEMA.add("households_apartment", ["HH_APARTMENT"], relative_to="households")
SCHEMA.add("households_other_type", ["HH_OTHER_TYPE"], relative_to="households")

# Building characteristics
SCHEMA.add("buildings_1_2_floors", ["BLDG_1_2_FLOORS"], relative_to="households")
SCHEMA.add("buildings_3_8_floors", ["BLDG_3_8_FLOORS"], relative_to="households")
SCHEMA.add("buildings_9plus_floors", ["BLDG_9PLUS_FLOORS"], relative_to="households")

# Construction period
SCHEMA.add("buildings_before_1948", ["BLDG_BEFORE_1948"], relative_to="households")
SCHEMA.add("buildings_1948_1960", ["BLDG_1948_1960"], relative_to="households")
SCHEMA.add("buildings_1961_1970", ["BLDG_1961_1970"], relative_to="households")
SCHEMA.add("buildings_1971_1980", ["BLDG_1971_1980"], relative_to="households")
SCHEMA.add("buildings_1981_1990", ["BLDG_1981_1990"], relative_to="households")
SCHEMA.add("buildings_1991_2000", ["BLDG_1991_2000"], relative_to="households")
SCHEMA.add("buildings_2001_2010", ["BLDG_2001_2010"], relative_to="households")
SCHEMA.add("buildings_2011_2022", ["BLDG_2011_2022"], relative_to="households")

# ---------------- Car Ownership / Vehicles ----------------
SCHEMA.add("households_no_vehicle", ["HH_NO_CAR"], relative_to="households")
SCHEMA.add("households_1_vehicle", ["HH_1_CAR"], relative_to="households")
SCHEMA.add("households_2_vehicles", ["HH_2_CARS"], relative_to="households")
SCHEMA.add("households_3plus_vehicles", ["HH_3PLUS_CARS"], relative_to="households")
SCHEMA.add("vehicles_per_household", ["CARS_PER_HH"], agg="mean", weight_by="households")

# ---------------- Housing Amenities ----------------
# Access to utilities
SCHEMA.add("households_electricity", ["HH_ELECTRICITY"], relative_to="households")
SCHEMA.add("households_water", ["HH_WATER"], relative_to="households")
SCHEMA.add("households_sewer", ["HH_SEWER"], relative_to="households")

# Air conditioning
SCHEMA.add("households_air_conditioning", ["HH_AIR_COND"], relative_to="households")
SCHEMA.add("households_central_heating", ["HH_CENTRAL_HEAT"], relative_to="households")

# Technology access
SCHEMA.add("households_internet", ["HH_INTERNET"], relative_to="households")
SCHEMA.add("households_computer", ["HH_COMPUTER"], relative_to="households")
SCHEMA.add("households_landline", ["HH_LANDLINE"], relative_to="households")
SCHEMA.add("households_cellphone", ["HH_CELLPHONE"], relative_to="households")

# ---------------- Family Characteristics ----------------
# Family structure
SCHEMA.add("households_single_person", ["HH_1_PERSON"], relative_to="households")
SCHEMA.add("households_couple_no_children", ["HH_COUPLE_NO_KIDS"], relative_to="households")
SCHEMA.add("households_couple_with_children", ["HH_COUPLE_WITH_KIDS"], relative_to="households")
SCHEMA.add("households_single_parent", ["HH_SINGLE_PARENT"], relative_to="households")
SCHEMA.add("households_other_family", ["HH_OTHER_FAMILY"], relative_to="households")
SCHEMA.add("households_non_family", ["HH_NON_FAMILY"], relative_to="households")

# ---------------- Disability ----------------
SCHEMA.add("population_disability", ["POP_DISABILITY"], relative_to="population")
SCHEMA.add("population_disability_seeing", ["POP_DIS_SEEING"], relative_to="population_disability")
SCHEMA.add("population_disability_hearing", ["POP_DIS_HEARING"], relative_to="population_disability")
SCHEMA.add("population_disability_walking", ["POP_DIS_WALKING"], relative_to="population_disability")
SCHEMA.add("population_disability_cognitive", ["POP_DIS_COGNITIVE"], relative_to="population_disability")
SCHEMA.add("population_disability_self_care", ["POP_DIS_SELF_CARE"], relative_to="population_disability")
SCHEMA.add("population_disability_communication", ["POP_DIS_COMMUNICATION"], relative_to="population_disability")

# ---------------- Veterans ----------------
SCHEMA.add("population_veterans", ["POP_VETERANS"], relative_to="population")
SCHEMA.add("population_veterans_disabled", ["POP_VETS_DISABLED"], relative_to="population_veterans")

# ---------------- Military Service ----------------
SCHEMA.add("population_served_military", ["POP_SERVED_MILITARY"], relative_to="population_18plus")
SCHEMA.add("population_currently_serving", ["POP_CURRENTLY_SERVING"], relative_to="population_18plus")

# ---------------- Language ----------------
SCHEMA.add("population_hebrew_speakers", ["POP_HEBREW"], relative_to="population")
SCHEMA.add("population_arabic_speakers", ["POP_ARABIC"], relative_to="population")
SCHEMA.add("population_russian_speakers", ["POP_RUSSIAN"], relative_to="population")
SCHEMA.add("population_english_speakers", ["POP_ENGLISH"], relative_to="population")
SCHEMA.add("population_french_speakers", ["POP_FRENCH"], relative_to="population")
SCHEMA.add("population_spanish_speakers", ["POP_SPANISH"], relative_to="population")

# ---------------- Internal Migration ----------------
SCHEMA.add("population_same_locality_5years", ["POP_SAME_LOC_5YRS"], relative_to="population")
SCHEMA.add("population_different_locality_5years", ["POP_DIFF_LOC_5YRS"], relative_to="population")
SCHEMA.add("population_same_district_5years", ["POP_SAME_DIST_5YRS"], relative_to="population")
SCHEMA.add("population_different_district_5years", ["POP_DIFF_DIST_5YRS"], relative_to="population")

__all__ = ["SCHEMA"]
