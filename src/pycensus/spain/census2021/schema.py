"""Common-schema column definitions for Spain Census 2021.

Technical aspects:
    Maps common cross-country wording (``population``, ``income``, ...) to
    INE Census 2021 variable codes. Unlike the US ACS which uses letter
    codes (B01003_001), INE data uses Spanish column names that we map
    to the common schema.

    The Census 2021 (Censo de Población y Viviendas 2021) includes:
    - Person-level data: demographics, education, employment, migration
    - Household-level data: composition, income, housing conditions
    - Housing-level data: characteristics, amenities, ownership

    For aggregated data, we use INE's tabulated results which provide
    counts at various geographic levels (nation, autonomous_community, 
    province, municipality, section).

    Note: INE variable codes may vary depending on the specific dataset and
    aggregation level. The codes below are placeholders based on typical INE
    variable naming conventions and should be verified against actual data files.

Source:
    INE Census 2021: https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780
    Variable documentation: https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736176780#Documentacion
"""

from ...schema import ColumnSchema

SCHEMA = ColumnSchema(prefix="census2021")

# ---------------- Population / Households ----------------
# Population counts from person-level data
SCHEMA.add("population", ["TOTAL_POB"])  # Total population
SCHEMA.add("population_male", ["POB_HOMBRES"], relative_to="population")
SCHEMA.add("population_female", ["POB_MUJERES"], relative_to="population")

# Age groups (INE typically uses 5-year age groups)
SCHEMA.add("population_0_4", ["POB_0_4"], relative_to="population")
SCHEMA.add("population_5_9", ["POB_5_9"], relative_to="population")
SCHEMA.add("population_10_14", ["POB_10_14"], relative_to="population")
SCHEMA.add("population_15_19", ["POB_15_19"], relative_to="population")
SCHEMA.add("population_20_24", ["POB_20_24"], relative_to="population")
SCHEMA.add("population_25_29", ["POB_25_29"], relative_to="population")
SCHEMA.add("population_30_34", ["POB_30_34"], relative_to="population")
SCHEMA.add("population_35_39", ["POB_35_39"], relative_to="population")
SCHEMA.add("population_40_44", ["POB_40_44"], relative_to="population")
SCHEMA.add("population_45_49", ["POB_45_49"], relative_to="population")
SCHEMA.add("population_50_54", ["POB_50_54"], relative_to="population")
SCHEMA.add("population_55_59", ["POB_55_59"], relative_to="population")
SCHEMA.add("population_60_64", ["POB_60_64"], relative_to="population")
SCHEMA.add("population_65_69", ["POB_65_69"], relative_to="population")
SCHEMA.add("population_70_74", ["POB_70_74"], relative_to="population")
SCHEMA.add("population_75_79", ["POB_75_79"], relative_to="population")
SCHEMA.add("population_80_84", ["POB_80_84"], relative_to="population")
SCHEMA.add("population_85plus", ["POB_85_Y_MAS"], relative_to="population")

# Median age
SCHEMA.add("age_median", ["EDAD_MEDIA"], agg="mean", weight_by="population")

# Households
SCHEMA.add("households", ["TOTAL_HOGARES"])
SCHEMA.add("household_size_mean", ["TAMHOG_PROMEDIO"], agg="mean", weight_by="households")

# Population by broad age groups (for compatibility)
SCHEMA.add("population_0_14", ["POB_0_14"], relative_to="population")
SCHEMA.add("population_15_24", ["POB_15_24"], relative_to="population")
SCHEMA.add("population_25_44", ["POB_25_44"], relative_to="population")
SCHEMA.add("population_45_64", ["POB_45_64"], relative_to="population")
SCHEMA.add("population_65plus", ["POB_65_Y_MAS"], relative_to="population")

# ---------------- Gender / Sex ----------------
# Ratio
SCHEMA.add("sex_ratio", ["RATIO_HOMBRES_MUJERES"], agg="mean", weight_by="population")

# ---------------- Ethnicity / Race / Nationality ----------------
# INE collects data on nationality and place of birth
SCHEMA.add("population_spanish_nationality", ["POB_NACIONALIDAD_ESPANOLA"], relative_to="population")
SCHEMA.add("population_foreign_nationality", ["POB_NACIONALIDAD_EXTRANJERA"], relative_to="population")

# Foreign population by continent of birth
SCHEMA.add("population_born_africa", ["POB_NACIDOS_AFRICA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_born_america", ["POB_NACIDOS_AMERICA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_born_asia", ["POB_NACIDOS_ASIA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_born_europe", ["POB_NACIDOS_EUROPA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_born_oceania", ["POB_NACIDOS_OCEANIA"], relative_to="population_foreign_nationality")

# Specific nationalities (top groups in Spain)
SCHEMA.add("population_romanian", ["POB_NACIONALIDAD_RUMANA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_moroccan", ["POB_NACIONALIDAD_MARROQUI"], relative_to="population_foreign_nationality")
SCHEMA.add("population_british", ["POB_NACIONALIDAD_BRITANICA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_venezuelan", ["POB_NACIONALIDAD_VENEZOLANA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_colombian", ["POB_NACIONALIDAD_COLOMBIANA"], relative_to="population_foreign_nationality")

# ---------------- Religion ----------------
# Note: Spain does not collect religion data in the census (it's a sensitive topic)
# This is available from other sources but not from INE census
# We include placeholders for compatibility
SCHEMA.add("population_catholic", ["POB_CATOLICA"], relative_to="population")
SCHEMA.add("population_none", ["POB_SIN_RELIGION"], relative_to="population")
SCHEMA.add("population_other_religions", ["POB_OTRAS_RELIGIONES"], relative_to="population")

# ---------------- Education ----------------
SCHEMA.add("population_15plus", ["POB_15_Y_MAS"], relative_to="population")
SCHEMA.add("population_16plus", ["POB_16_Y_MAS"], relative_to="population")
SCHEMA.add("population_18plus", ["POB_18_Y_MAS"], relative_to="population")

# Educational attainment for population 15+
SCHEMA.add("population_no_education", ["POB_SIN_ESTUDIOS"], relative_to="population_15plus")
SCHEMA.add("population_primary_incomplete", ["POB_ESTUDIOS_PRIMARIOS_INCOMPLETOS"], relative_to="population_15plus")
SCHEMA.add("population_primary", ["POB_ESTUDIOS_PRIMARIOS"], relative_to="population_15plus")
SCHEMA.add("population_lower_secondary", ["POB_ESTUDIOS_SECUNDARIOS_PRIMERA_ETAPA"], relative_to="population_15plus")
SCHEMA.add("population_upper_secondary", ["POB_ESTUDIOS_SECUNDARIOS_SEGUNDA_ETAPA"], relative_to="population_15plus")
SCHEMA.add("population_post_secondary", ["POB_ESTUDIOS_POSTSECUNDARIOS_NO_SUPERIORES"], relative_to="population_15plus")
SCHEMA.add("education_vocational", ["POB_FORMACION_PROFESIONAL"], relative_to="population_15plus")
SCHEMA.add("education_university", ["POB_ESTUDIOS_SUPERIORES"], relative_to="population_15plus")

# Literacy
SCHEMA.add("population_literate", ["POB_SABE_LEER_ESCRIBIR"], relative_to="population_15plus")
SCHEMA.add("population_illiterate", ["POB_NO_SABE_LEER_ESCRIBIR"], relative_to="population_15plus")

# ---------------- Income / Poverty ----------------
# Household income - INE collects this in ranges
SCHEMA.add("income_median_household", ["RENTA_MEDIANA_HOGAR"], agg="mean", weight_by="households")
SCHEMA.add("income_mean_household", ["RENTA_MEDIA_HOGAR"], agg="mean", weight_by="households")

# Income ranges (for relative measures)
SCHEMA.add("households_no_income", ["HOGARES_SIN_RENTAS"], relative_to="households")
SCHEMA.add("households_income_1", ["HOGARES_RENTA_MENOS_6000"], relative_to="households")
SCHEMA.add("households_income_2", ["HOGARES_RENTA_6000_12000"], relative_to="households")
SCHEMA.add("households_income_3", ["HOGARES_RENTA_12000_18000"], relative_to="households")
SCHEMA.add("households_income_4", ["HOGARES_RENTA_18000_24000"], relative_to="households")
SCHEMA.add("households_income_5", ["HOGARES_RENTA_24000_30000"], relative_to="households")
SCHEMA.add("households_income_6", ["HOGARES_RENTA_30000_36000"], relative_to="households")
SCHEMA.add("households_income_7", ["HOGARES_RENTA_36000_42000"], relative_to="households")
SCHEMA.add("households_income_8", ["HOGARES_RENTA_42000_48000"], relative_to="households")
SCHEMA.add("households_income_9", ["HOGARES_RENTA_48000_54000"], relative_to="households")
SCHEMA.add("households_income_10", ["HOGARES_RENTA_MAS_54000"], relative_to="households")

# Income per capita
SCHEMA.add("income_per_capita", ["RENTA_POR_HABITANTE"], agg="mean", weight_by="population")

# ---------------- Employment / Labor Force ----------------
# Population 16+ for labor force (Spain uses 16 as the minimum age for labor force)
SCHEMA.add("population_16plus", ["POB_16_Y_MAS"], relative_to="population")

# Labor force status
SCHEMA.add("labor_force", ["POB_ACTIVA"], relative_to="population_16plus")
SCHEMA.add("employed", ["POB_OCUPADA"], relative_to="labor_force")
SCHEMA.add("unemployed", ["POB_PARADA"], relative_to="labor_force")
SCHEMA.add("unemployment_rate", ["TASA_PARO"], agg="mean", weight_by="labor_force")

# Employment by sector
SCHEMA.add("employed_agriculture", ["OCUP_AGRICULTURA"], relative_to="employed")
SCHEMA.add("employed_mining", ["OCUP_MINERIA"], relative_to="employed")
SCHEMA.add("employed_manufacturing", ["OCUP_INDUSTRIA"], relative_to="employed")
SCHEMA.add("employed_construction", ["OCUP_CONSTRUCCION"], relative_to="employed")
SCHEMA.add("employed_commerce", ["OCUP_COMERCIO"], relative_to="employed")
SCHEMA.add("employed_transport", ["OCUP_TRANSPORTE"], relative_to="employed")
SCHEMA.add("employed_hostelry", ["OCUP_HOSTELERIA"], relative_to="employed")
SCHEMA.add("employed_information_communication", ["OCUP_INFORMACION_COMUNICACION"], relative_to="employed")
SCHEMA.add("employed_financial", ["OCUP_FINANCIERA"], relative_to="employed")
SCHEMA.add("employed_real_estate", ["OCUP_INMOBILIARIA"], relative_to="employed")
SCHEMA.add("employed_professional", ["OCUP_PROFESIONALES"], relative_to="employed")
SCHEMA.add("employed_administration", ["OCUP_ADMINISTRACION"], relative_to="employed")
SCHEMA.add("employed_education", ["OCUP_EDUCACION"], relative_to="employed")
SCHEMA.add("employed_health", ["OCUP_SALUD"], relative_to="employed")
SCHEMA.add("employed_services", ["OCUP_SERVICIOS"], relative_to="employed")

# Formal vs informal employment (in Spain context: contract type)
SCHEMA.add("employed_permanent_contract", ["OCUP_CONTRATO_INDEFINIDO"], relative_to="employed")
SCHEMA.add("employed_temporary_contract", ["OCUP_CONTRATO_TEMPORAL"], relative_to="employed")
SCHEMA.add("employed_self_employed", ["OCUP_AUTONOMO"], relative_to="employed")

# Employment status
SCHEMA.add("employed_full_time", ["OCUP_JORNADA_COMPLETA"], relative_to="employed")
SCHEMA.add("employed_part_time", ["OCUP_JORNADA_PARCIAL"], relative_to="employed")

# ---------------- Housing / Tenure ----------------
# Housing tenure (owner vs renter)
SCHEMA.add("households_owner", ["VIVIENDAS_PROPIEDAD"], relative_to="households")
SCHEMA.add("households_renter", ["VIVIENDAS_ALQUILER"], relative_to="households")
SCHEMA.add("households_free", ["VIVIENDAS_CEDIDAS_GRATIS"], relative_to="households")
SCHEMA.add("households_other_tenure", ["VIVIENDAS_OTRO_REGIMEN"], relative_to="households")

# Housing type
SCHEMA.add("households_house", ["VIVIENDAS_CASA_INDEPENDIENTE"], relative_to="households")
SCHEMA.add("households_apartment", ["VIVIENDAS_PISO"], relative_to="households")
SCHEMA.add("households_semi_detached", ["VIVIENDAS_CASA_ADOSADA"], relative_to="households")
SCHEMA.add("households_other_type", ["VIVIENDAS_OTRO_TIPO"], relative_to="households")

# ---------------- Car Ownership / Vehicles ----------------
SCHEMA.add("households_no_vehicle", ["HOGARES_SIN_COCHE"], relative_to="households")
SCHEMA.add("households_1_vehicle", ["HOGARES_1_COCHE"], relative_to="households")
SCHEMA.add("households_2_vehicles", ["HOGARES_2_COCHES"], relative_to="households")
SCHEMA.add("households_3plus_vehicles", ["HOGARES_3_Y_MAS_COCHES"], relative_to="households")
SCHEMA.add("vehicles_per_household", ["COCHES_POR_HOGAR"], agg="mean", weight_by="households")

# Motorcycle ownership
SCHEMA.add("households_motorcycle", ["HOGARES_CON_MOTO"], relative_to="households")

# ---------------- Commuting Mode ----------------
# Mode of transportation to work (for employed population)
SCHEMA.add("workers_walk", ["OCUP_CAMINA"], relative_to="employed")
SCHEMA.add("workers_bike", ["OCUP_BICICLETA"], relative_to="employed")
SCHEMA.add("workers_car", ["OCUP_COCHE"], relative_to="employed")
SCHEMA.add("workers_motorcycle", ["OCUP_MOTO"], relative_to="employed")
SCHEMA.add("workers_public_transit", ["OCUP_TRANSPORTE_PUBLICO"], relative_to="employed")
SCHEMA.add("workers_train", ["OCUP_TREN"], relative_to="employed")
SCHEMA.add("workers_bus", ["OCUP_AUTOBUS"], relative_to="employed")
SCHEMA.add("workers_metro", ["OCUP_METRO"], relative_to="employed")
SCHEMA.add("workers_taxi", ["OCUP_TAXI"], relative_to="employed")
SCHEMA.add("workers_company_vehicle", ["OCUP_COCHE_EMPRESA"], relative_to="employed")
SCHEMA.add("workers_other", ["OCUP_OTRO_TRANSPORTE"], relative_to="employed")
SCHEMA.add("workers_home", ["OCUP_TRABAJA_EN_CASA"], relative_to="employed")

SCHEMA.add("commute_time_mean", ["TIEMPO_DESPLAZAMIENTO_PROMEDIO"], agg="mean", weight_by="employed")

# ---------------- Housing Amenities ----------------
# Access to basic services
SCHEMA.add("households_water_piped", ["VIVIENDAS_AGUA_CANALIZADA"], relative_to="households")
SCHEMA.add("households_water_well", ["VIVIENDAS_AGUA_POZO"], relative_to="households")
SCHEMA.add("households_no_water", ["VIVIENDAS_SIN_AGUA"], relative_to="households")

SCHEMA.add("households_sewer", ["VIVIENDAS_DESAGUE_CLOACAL"], relative_to="households")
SCHEMA.add("households_no_sewer", ["VIVIENDAS_SIN_DESAGUE"], relative_to="households")

SCHEMA.add("households_electricity", ["VIVIENDAS_ELECTRICIDAD"], relative_to="households")
SCHEMA.add("households_no_electricity", ["VIVIENDAS_SIN_ELECTRICIDAD"], relative_to="households")

# Heating
SCHEMA.add("households_central_heating", ["VIVIENDAS_CALEFACCION_CENTRAL"], relative_to="households")
SCHEMA.add("households_individual_heating", ["VIVIENDAS_CALEFACCION_INDIVIDUAL"], relative_to="households")
SCHEMA.add("households_no_heating", ["VIVIENDAS_SIN_CALEFACCION"], relative_to="households")

# Internet and technology access
SCHEMA.add("households_internet", ["VIVIENDAS_INTERNET"], relative_to="households")
SCHEMA.add("households_computer", ["VIVIENDAS_ORDENADOR"], relative_to="households")
SCHEMA.add("households_tablet", ["VIVIENDAS_TABLET"], relative_to="households")
SCHEMA.add("households_cellphone", ["VIVIENDAS_MOVIL"], relative_to="households")
SCHEMA.add("households_landline", ["VIVIENDAS_TELEFONO_FIJO"], relative_to="households")

# ---------------- Disability ----------------
SCHEMA.add("population_disability", ["POB_DISCAPACIDAD"], relative_to="population")
SCHEMA.add("population_disability_vision", ["POB_DISC_VISUAL"], relative_to="population_disability")
SCHEMA.add("population_disability_hearing", ["POB_DISC_AUDITIVA"], relative_to="population_disability")
SCHEMA.add("population_disability_mobility", ["POB_DISC_MOTRIZ"], relative_to="population_disability")
SCHEMA.add("population_disability_cognitive", ["POB_DISC_INTELECTUAL"], relative_to="population_disability")
SCHEMA.add("population_disability_psychological", ["POB_DISC_PSIQUICA"], relative_to="population_disability")

# ---------------- Health Insurance ----------------
# In Spain, healthcare is universal through the public system
SCHEMA.add("population_with_public_healthcare", ["POB_COBERTURA_SANITARIA_PUBLICA"], relative_to="population")
SCHEMA.add("population_with_private_healthcare", ["POB_SEGURO_MEDICO_PRIVADO"], relative_to="population")
SCHEMA.add("population_no_healthcare", ["POB_SIN_COBERTURA_SANITARIA"], relative_to="population")

# ---------------- Marital Status ----------------
SCHEMA.add("population_single", ["POB_SOLTERO"], relative_to="population_15plus")
SCHEMA.add("population_married", ["POB_CASADO"], relative_to="population_15plus")
SCHEMA.add("population_widowed", ["POB_VIUDO"], relative_to="population_15plus")
SCHEMA.add("population_divorced", ["POB_DIVORCIADO"], relative_to="population_15plus")
SCHEMA.add("population_separated", ["POB_SEPARADO"], relative_to="population_15plus")

# ---------------- Migration ----------------
# Internal migration
SCHEMA.add("population_same_municipality_5years", ["POB_MISMO_MUNICIPIO_5_ANOS"], relative_to="population")
SCHEMA.add("population_same_province_5years", ["POB_MISMA_PROVINCIA_5_ANOS"], relative_to="population")
SCHEMA.add("population_different_province_5years", ["POB_DISTINTA_PROVINCIA_5_ANOS"], relative_to="population")

# Foreign-born population
SCHEMA.add("population_foreign_born", ["POB_EXTRANJERO"], relative_to="population")
SCHEMA.add("population_naturalized", ["POB_NACIONALIZADO"], relative_to="population_foreign_born")

# ---------------- Housing Characteristics ----------------
# Building type
SCHEMA.add("buildings_single_family", ["EDIFICIOS_UNIFAMILIARES"], relative_to="households")
SCHEMA.add("buildings_multi_family", ["EDIFICIOS_PLURIFAMILIARES"], relative_to="households")
SCHEMA.add("buildings_apartment", ["EDIFICIOS_BLOQUE_PISOS"], relative_to="households")

# Construction period
SCHEMA.add("buildings_before_1900", ["EDIFICIOS_ANTES_1900"], relative_to="households")
SCHEMA.add("buildings_1900_1940", ["EDIFICIOS_1900_1940"], relative_to="households")
SCHEMA.add("buildings_1941_1960", ["EDIFICIOS_1941_1960"], relative_to="households")
SCHEMA.add("buildings_1961_1970", ["EDIFICIOS_1961_1970"], relative_to="households")
SCHEMA.add("buildings_1971_1980", ["EDIFICIOS_1971_1980"], relative_to="households")
SCHEMA.add("buildings_1981_1990", ["EDIFICIOS_1981_1990"], relative_to="households")
SCHEMA.add("buildings_1991_2000", ["EDIFICIOS_1991_2000"], relative_to="households")
SCHEMA.add("buildings_2001_2010", ["EDIFICIOS_2001_2010"], relative_to="households")
SCHEMA.add("buildings_2011_2021", ["EDIFICIOS_2011_2021"], relative_to="households")

# ---------------- Family Characteristics ----------------
# Family structure
SCHEMA.add("households_single_person", ["HOGARES_1_PERSONA"], relative_to="households")
SCHEMA.add("households_couple_no_children", ["HOGARES_PAREJA_SIN_HIJOS"], relative_to="households")
SCHEMA.add("households_couple_with_children", ["HOGARES_PAREJA_CON_HIJOS"], relative_to="households")
SCHEMA.add("households_single_parent", ["HOGARES_MONOPARENTAL"], relative_to="households")
SCHEMA.add("households_other_family", ["HOGARES_OTRO_TIPO_FAMILIA"], relative_to="households")

__all__ = ["SCHEMA"]
