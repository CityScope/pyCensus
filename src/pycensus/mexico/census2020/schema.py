"""Common-schema column definitions for Mexico Census 2020.

Technical aspects:
    Maps common cross-country wording (``population``, ``income``, ...) to
    INEGI Census 2020 variable codes. Unlike the US ACS which uses letter
    codes (B01003_001), INEGI data uses Spanish column names that we map
    to the common schema.

    The Census 2020 (CPV 2020) includes:
    - Person-level data: demographics, education, employment, migration
    - Household-level data: composition, income, housing conditions
    - Housing-level data: characteristics, amenities, ownership

    For aggregated data, we use INEGI's tabulated results which provide
    counts at various geographic levels (state, municipality, locality, ageb).

Source:
    INEGI Census 2020: https://www.inegi.org.mx/programas/ccpv/2020/
    Variable documentation: https://www.inegi.org.mx/programas/ccpv/2020/#Documentacion
"""

from ...schema import ColumnSchema

SCHEMA = ColumnSchema(prefix="census2020")

# ---------------- Population / Households ----------------
# Population counts from person-level data
SCHEMA.add("population", ["POBTOTAL"])  # Total population
SCHEMA.add("population_male", ["POBHOMBRES"], relative_to="population")
SCHEMA.add("population_female", ["POBMUJERES"], relative_to="population")

# Age groups
SCHEMA.add("population_0_4", ["POB_0_A_4"], relative_to="population")
SCHEMA.add("population_5_14", ["POB_5_A_14"], relative_to="population")
SCHEMA.add("population_15_19", ["POB_15_A_19"], relative_to="population")
SCHEMA.add("population_20_24", ["POB_20_A_24"], relative_to="population")
SCHEMA.add("population_25_29", ["POB_25_A_29"], relative_to="population")
SCHEMA.add("population_30_39", ["POB_30_A_39"], relative_to="population")
SCHEMA.add("population_40_49", ["POB_40_A_49"], relative_to="population")
SCHEMA.add("population_50_59", ["POB_50_A_59"], relative_to="population")
SCHEMA.add("population_60_69", ["POB_60_A_69"], relative_to="population")
SCHEMA.add("population_70_79", ["POB_70_A_79"], relative_to="population")
SCHEMA.add("population_80plus", ["POB_80_Y_MAS"], relative_to="population")

# Median age
SCHEMA.add("age_median", ["EDAD_MEDIA"], agg="mean", weight_by="population")

# Households
SCHEMA.add("households", ["TOTAL_HOGARES"])
SCHEMA.add("household_size_mean", ["TAMHOG_PROMEDIO"], agg="mean", weight_by="households")

# ---------------- Gender / Sex ----------------
# Already covered in population breakdowns above

# ---------------- Ethnicity / Race ----------------
# INEGI collects data on indigenous populations and language
SCHEMA.add("population_indigenous", ["POB_INDIGENA"], relative_to="population")
SCHEMA.add("population_speaks_indigenous_language", ["POB_HABLANTE_LENGUA_IND"], relative_to="population")

# Specific indigenous language speakers (top languages)
SCHEMA.add("population_nahuatl", ["POB_NAHUATL"], relative_to="population_speaks_indigenous_language")
SCHEMA.add("population_maya", ["POB_MAYA"], relative_to="population_speaks_indigenous_language")
SCHEMA.add("population_otomi", ["POB_OTOMI"], relative_to="population_speaks_indigenous_language")
SCHEMA.add("population_mixe", ["POB_MIXE"], relative_to="population_speaks_indigenous_language")
SCHEMA.add("population_zapoteco", ["POB_ZAPOTEC"], relative_to="population_speaks_indigenous_language")

# Afro-Mexican population (added in 2020 census)
SCHEMA.add("population_afro_mexican", ["POB_AFROMEXICANA"], relative_to="population")

# ---------------- Religion ----------------
SCHEMA.add("population_catholic", ["POB_CATOLICA"], relative_to="population")
SCHEMA.add("population_protestant", ["POB_PROTESTANTE"], relative_to="population")
SCHEMA.add("population_other_christian", ["POB_OTRA_CRISTIANA"], relative_to="population")
SCHEMA.add("population_jewish", ["POB_JUDIA"], relative_to="population")
SCHEMA.add("population_none", ["POB_SIN_RELIGION"], relative_to="population")

# ---------------- Education ----------------
SCHEMA.add("population_15plus", ["POB_15_Y_MAS"], relative_to="population")
SCHEMA.add("population_18plus", ["POB_18_Y_MAS"], relative_to="population")

# Educational attainment for population 15+
SCHEMA.add("population_no_education", ["POB_SIN_EDUCACION"], relative_to="population_15plus")
SCHEMA.add("population_preschool", ["POB_PREESCOLAR"], relative_to="population_15plus")
SCHEMA.add("population_primary", ["POB_PRIMARIA"], relative_to="population_15plus")
SCHEMA.add("population_secondary", ["POB_SECUNDARIA"], relative_to="population_15plus")
SCHEMA.add("education_preparatoria", ["POB_PREPARATORIA"], relative_to="population_15plus")
SCHEMA.add("education_professional", ["POB_PROFESIONAL"], relative_to="population_15plus")
SCHEMA.add("education_bachelors", ["POB_LICENCIATURA"], relative_to="population_15plus")
SCHEMA.add("education_postgraduate", ["POB_POSGRADO"], relative_to="population_15plus")

# Literacy
SCHEMA.add("population_literate", ["POB_ALFABETA"], relative_to="population_15plus")

# ---------------- Income / Poverty ----------------
# Household income - INEGI collects this in ranges
SCHEMA.add("income_median_household", ["INGRESO_MEDIO_HOGAR"], agg="mean", weight_by="households")
SCHEMA.add("income_mean_household", ["INGRESO_PROMEDIO_HOGAR"], agg="mean", weight_by="households")

# Income ranges (for relative measures)
SCHEMA.add("households_no_income", ["HOGARES_SIN_INGRESOS"], relative_to="households")
SCHEMA.add("households_income_1_to_3_salaries", ["HOGARES_1_A_3_SALARIOS"], relative_to="households")
SCHEMA.add("households_income_3_to_5_salaries", ["HOGARES_3_A_5_SALARIOS"], relative_to="households")
SCHEMA.add("households_income_5_to_10_salaries", ["HOGARES_5_A_10_SALARIOS"], relative_to="households")
SCHEMA.add("households_income_over_10_salaries", ["HOGARES_MAS_10_SALARIOS"], relative_to="households")

# ---------------- Employment / Labor Force ----------------
# Population 12+ for labor force
SCHEMA.add("population_12plus", ["POB_12_Y_MAS"], relative_to="population")

# Labor force status
SCHEMA.add("labor_force", ["PEA"], relative_to="population_12plus")
SCHEMA.add("employed", ["OCUPADOS"], relative_to="labor_force")
SCHEMA.add("unemployed", ["DESOCUPADOS"], relative_to="labor_force")
SCHEMA.add("unemployment_rate", ["TASA_DESOCUPACION"], agg="mean", weight_by="labor_force")

# Employment by sector
SCHEMA.add("employed_agriculture", ["OCUP_AGRICULTURA"], relative_to="employed")
SCHEMA.add("employed_mining", ["OCUP_MINERIA"], relative_to="employed")
SCHEMA.add("employed_manufacturing", ["OCUP_MANUFACTURA"], relative_to="employed")
SCHEMA.add("employed_construction", ["OCUP_CONSTRUCCION"], relative_to="employed")
SCHEMA.add("employed_commerce", ["OCUP_COMERCIO"], relative_to="employed")
SCHEMA.add("employed_services", ["OCUP_SERVICIOS"], relative_to="employed")
SCHEMA.add("employed_transport", ["OCUP_TRANSPORTE"], relative_to="employed")

# Formal vs informal employment
SCHEMA.add("employed_formal", ["OCUP_FORMAL"], relative_to="employed")
SCHEMA.add("employed_informal", ["OCUP_INFORMAL"], relative_to="employed")

# ---------------- Housing / Renters ----------------
# Housing tenure (owner vs renter)
SCHEMA.add("households_owner", ["HOGARES_PROPIETARIOS"], relative_to="households")
SCHEMA.add("households_renter", ["HOGARES_RENTA"], relative_to="households")
SCHEMA.add("households_other_tenure", ["HOGARES_OTRA_TENENCIA"], relative_to="households")

# Housing type
SCHEMA.add("households_house", ["VIVIENDAS_CASA"], relative_to="households")
SCHEMA.add("households_apartment", ["VIVIENDAS_DEPARTAMENTO"], relative_to="households")
SCHEMA.add("households_mobile_home", ["VIVIENDAS_MOVIL"], relative_to="households")

# ---------------- Car Ownership / Vehicles ----------------
SCHEMA.add("households_no_vehicle", ["HOGARES_SIN_VEHICULO"], relative_to="households")
SCHEMA.add("households_1_vehicle", ["HOGARES_1_VEHICULO"], relative_to="households")
SCHEMA.add("households_2_vehicles", ["HOGARES_2_VEHICULOS"], relative_to="households")
SCHEMA.add("households_3plus_vehicles", ["HOGARES_3_Y_MAS_VEHICULOS"], relative_to="households")
SCHEMA.add("vehicles_per_household", ["VEHICULOS_POR_HOGAR"], agg="mean", weight_by="households")

# ---------------- Commuting Mode ----------------
# Mode of transportation to work (for employed population)
SCHEMA.add("workers_walk", ["OCUP_CAMINA"], relative_to="employed")
SCHEMA.add("workers_bike", ["OCUP_BICICLETA"], relative_to="employed")
SCHEMA.add("workers_car", ["OCUP_AUTOMOVIL"], relative_to="employed")
SCHEMA.add("workers_motorcycle", ["OCUP_MOTOCICLETA"], relative_to="employed")
SCHEMA.add("workers_public_transit", ["OCUP_TRANSPORTE_PUBLICO"], relative_to="employed")
SCHEMA.add("workers_taxicab", ["OCUP_TAXI"], relative_to="employed")
SCHEMA.add("workers_company_vehicle", ["OCUP_VEHICULO_EMPRESA"], relative_to="employed")
SCHEMA.add("workers_other", ["OCUP_OTRO_TRANSPORTE"], relative_to="employed")
SCHEMA.add("workers_home", ["OCUP_TRABAJA_EN_CASA"], relative_to="employed")

SCHEMA.add("commute_time_mean", ["TIEMPO_TRASLADO_PROMEDIO"], agg="mean", weight_by="employed")

# ---------------- Housing Amenities ----------------
# Access to basic services
SCHEMA.add("households_water_piped", ["VIVIENDAS_AGUA_ENTUBADA"], relative_to="households")
SCHEMA.add("households_water_well", ["VIVIENDAS_AGUA_POZO"], relative_to="households")
SCHEMA.add("households_no_water", ["VIVIENDAS_SIN_AGUA"], relative_to="households")

SCHEMA.add("households_sewer", ["VIVIENDAS_DRENAJE"], relative_to="households")
SCHEMA.add("households_no_sewer", ["VIVIENDAS_SIN_DRENAJE"], relative_to="households")

SCHEMA.add("households_electricity", ["VIVIENDAS_ELECTRICIDAD"], relative_to="households")
SCHEMA.add("households_no_electricity", ["VIVIENDAS_SIN_ELECTRICIDAD"], relative_to="households")

# Internet and technology access
SCHEMA.add("households_internet", ["VIVIENDAS_INTERNET"], relative_to="households")
SCHEMA.add("households_computer", ["VIVIENDAS_COMPUTADORA"], relative_to="households")
SCHEMA.add("households_cellphone", ["VIVIENDAS_CELULAR"], relative_to="households")
SCHEMA.add("households_landline", ["VIVIENDAS_TELEFONO_FIJO"], relative_to="households")

# Heating and cooking
SCHEMA.add("households_gas_stove", ["VIVIENDAS_ESTUFA_GAS"], relative_to="households")
SCHEMA.add("households_electric_stove", ["VIVIENDAS_ESTUFA_ELECTRICA"], relative_to="households")
SCHEMA.add("households_wood_stove", ["VIVIENDAS_ESTUFA_LENA"], relative_to="households")

# ---------------- Disability ----------------
SCHEMA.add("population_disability", ["POB_DISCAPACIDAD"], relative_to="population")
SCHEMA.add("population_disability_vision", ["POB_DISC_VISUAL"], relative_to="population_disability")
SCHEMA.add("population_disability_hearing", ["POB_DISC_AUDITIVA"], relative_to="population_disability")
SCHEMA.add("population_disability_mobility", ["POB_DISC_MOTRIZ"], relative_to="population_disability")
SCHEMA.add("population_disability_cognitive", ["POB_DISC_COGNITIVA"], relative_to="population_disability")

# ---------------- Health Insurance ----------------
SCHEMA.add("population_with_healthcare", ["POB_CON_DERECHOHABIENCIA"], relative_to="population")
SCHEMA.add("population_no_healthcare", ["POB_SIN_DERECHOHABIENCIA"], relative_to="population")

# Public healthcare types
SCHEMA.add("population_imss", ["POB_IMSS"], relative_to="population_with_healthcare")
SCHEMA.add("population_issste", ["POB_ISSSTE"], relative_to="population_with_healthcare")
SCHEMA.add("population_seguro_popular", ["POB_SEGURO_POPULAR"], relative_to="population_with_healthcare")
SCHEMA.add("population_other_healthcare", ["POB_OTRO_SEGURO"], relative_to="population_with_healthcare")

__all__ = ["SCHEMA"]
