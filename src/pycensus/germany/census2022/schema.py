"""Common-schema for Germany Census 2022."""
from ...schema import ColumnSchema
SCHEMA = ColumnSchema(prefix="census2022")

# Population
SCHEMA.add("population", ["POP_TOTAL"])
SCHEMA.add("population_male", ["POP_MALE"], relative_to="population")
SCHEMA.add("population_female", ["POP_FEMALE"], relative_to="population")
SCHEMA.add("population_0_17", ["POP_0_17"], relative_to="population")
SCHEMA.add("population_18_29", ["POP_18_29"], relative_to="population")
SCHEMA.add("population_30_49", ["POP_30_49"], relative_to="population")
SCHEMA.add("population_50_64", ["POP_50_64"], relative_to="population")
SCHEMA.add("population_65plus", ["POP_65P"], relative_to="population")
SCHEMA.add("age_median", ["AGE_MED"], agg="mean", weight_by="population")
SCHEMA.add("population_density", ["POP_DENS"], agg="mean", weight_by="population")

# Nationality/Migration
SCHEMA.add("population_german", ["POP_GERMAN"], relative_to="population")
SCHEMA.add("population_foreign", ["POP_FOREIGN"], relative_to="population")
SCHEMA.add("population_foreign_eu", ["POP_F_EU"], relative_to="population_foreign")
SCHEMA.add("population_foreign_non_eu", ["POP_F_NON_EU"], relative_to="population_foreign")

# Education
SCHEMA.add("population_15plus", ["POP_15P"], relative_to="population")
SCHEMA.add("population_no_education", ["POP_NO_EDU"], relative_to="population_15plus")
SCHEMA.add("population_secondary", ["POP_SEC_EDU"], relative_to="population_15plus")
SCHEMA.add("population_tertiary", ["POP_TERT_EDU"], relative_to="population_15plus")

# Employment
SCHEMA.add("labor_force", ["LABOR_F"], relative_to="population_15plus")
SCHEMA.add("employed", ["EMPLOYED"], relative_to="labor_force")
SCHEMA.add("unemployed", ["UNEMPL"], relative_to="labor_force")
SCHEMA.add("unemployment_rate", ["UNEMPL_R"], agg="mean", weight_by="labor_force")
SCHEMA.add("employed_agriculture", ["EMP_AGRI"], relative_to="employed")
SCHEMA.add("employed_industry", ["EMP_IND"], relative_to="employed")
SCHEMA.add("employed_services", ["EMP_SERV"], relative_to="employed")

# Households
SCHEMA.add("households", ["HH_TOTAL"])
SCHEMA.add("household_size_mean", ["HH_SIZE"], agg="mean", weight_by="households")
SCHEMA.add("households_single", ["HH_1P"], relative_to="households")
SCHEMA.add("households_family", ["HH_FAM"], relative_to="households")

# Housing
SCHEMA.add("households_owner", ["HH_OWN"], relative_to="households")
SCHEMA.add("households_renter", ["HH_RENT"], relative_to="households")
SCHEMA.add("buildings_residential", ["BLDG_RES"], relative_to="households")
SCHEMA.add("buildings_1_2_families", ["BLDG_1_2F"], relative_to="households")
SCHEMA.add("buildings_3plus_families", ["BLDG_3P"], relative_to="households")

# Income
SCHEMA.add("income_median_household", ["INC_MED_HH"], agg="mean", weight_by="households")
SCHEMA.add("income_mean_household", ["INC_MEAN_HH"], agg="mean", weight_by="households")

# Religion (important in Germany)
SCHEMA.add("population_catholic", ["POP_CATH"], relative_to="population")
SCHEMA.add("population_protestant", ["POP_PROT"], relative_to="population")
SCHEMA.add("population_none", ["POP_NO_REL"], relative_to="population")
SCHEMA.add("population_other_religion", ["POP_OTHER_REL"], relative_to="population")

__all__ = ["SCHEMA"]
