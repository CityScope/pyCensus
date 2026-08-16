"""Common-schema column definitions for Euskadi Census 2021.

Technical aspects:
    Maps common cross-country wording (``population``, ``income``, ...) to
    Eustat Census 2021 variable codes. Unlike the US ACS which uses letter
    codes (B01003_001), Eustat data uses Basque/Spanish column names that we map
    to the common schema.

    The Census 2021 (Censo de Poblacion y Viviendas 2021) includes:
    - Person-level data: demographics, education, employment, migration, language
    - Household-level data: composition, income, housing conditions
    - Housing-level data: characteristics, amenities, ownership

    For aggregated data, we use Eustat's tabulated results which provide
    counts at various geographic levels (autonomous_community, territory,
    comarca, municipality, district, section).

    Note: Eustat variable codes may vary depending on the specific dataset and
    aggregation level. The codes below are placeholders based on typical Eustat
    variable naming conventions and should be verified against actual data files.

Source:
    Eustat Census 2021: https://www.eustat.eus/temas/12001/tema_12001/es_definiciones.html
"""

from ...schema import ColumnSchema

SCHEMA = ColumnSchema(prefix="census2021")

# ---------------- Population / Households ----------------
# Population counts from person-level data
SCHEMA.add("population", ["TOTAL_POB"])  # Total population
SCHEMA.add("population_male", ["POB_HOMBRES"], relative_to="population")
SCHEMA.add("population_female", ["POB_MUJERES"], relative_to="population")

# Age groups (5-year age groups, standard in Spain/Euskadi)
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
SCHEMA.add("sex_ratio", ["RATIO_HOMBRES_MUJERES"], agg="mean", weight_by="population")

# ---------------- Ethnicity / Nationality ----------------
# In Euskadi/Espain, nationality data is collected
SCHEMA.add("population_spanish_nationality", ["POB_NACIONALIDAD_ESPANOLA"], relative_to="population")
SCHEMA.add("population_foreign_nationality", ["POB_NACIONALIDAD_EXTRANJERA"], relative_to="population")

# Foreign population by continent of birth
SCHEMA.add("population_born_africa", ["POB_NACIDOS_AFRICA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_born_america", ["POB_NACIDOS_AMERICA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_born_asia", ["POB_NACIDOS_ASIA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_born_europe", ["POB_NACIDOS_EUROPA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_born_oceania", ["POB_NACIDOS_OCEANIA"], relative_to="population_foreign_nationality")

# Specific nationalities common in Euskadi
SCHEMA.add("population_romanian", ["POB_NACIONALIDAD_RUMANA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_moroccan", ["POB_NACIONALIDAD_MARROQUI"], relative_to="population_foreign_nationality")
SCHEMA.add("population_portuguese", ["POB_NACIONALIDAD_PORTUGUESA"], relative_to="population_foreign_nationality")
SCHEMA.add("population_french", ["POB_NACIONALIDAD_FRANCESA"], relative_to="population_foreign_nationality")

# ---------------- Language (Basque and Spanish) ----------------
# Unique to Euskadi - Basque language skills
SCHEMA.add("population_basque_speakers", ["POB_EUSKALDUN"], relative_to="population")
SCHEMA.add("population_basque_understands", ["POB_ENTIENDE_EUSKERA"], relative_to="population")
SCHEMA.add("population_basque_speaks", ["POB_HABLA_EUSKERA"], relative_to="population_basque_speakers")
SCHEMA.add("population_basque_reads", ["POB_LEE_EUSKERA"], relative_to="population_basque_speakers")
SCHEMA.add("population_basque_writes", ["POB_ESCRIBE_EUSKERA"], relative_to="population_basque_speakers")

# Population by first language
SCHEMA.add("population_first_language_basque", ["POB_LENGUA_MATERNA_EUSKERA"], relative_to="population")
SCHEMA.add("population_first_language_spanish", ["POB_LENGUA_MATERNA_CASTELLANO"], relative_to="population")
SCHEMA.add("population_first_language_other", ["POB_LENGUA_MATERNA_OTRA"], relative_to="population")

# Population by usual language
SCHEMA.add("population_usual_language_basque", ["POB_LENGUA_HABITUAL_EUSKERA"], relative_to="population")
SCHEMA.add("population_usual_language_spanish", ["POB_LENGUA_HABITUAL_CASTELLANO"], relative_to="population")
SCHEMA.add("population_usual_language_both", ["POB_LENGUA_HABITUAL_AMBAS"], relative_to="population")
SCHEMA.add("population_usual_language_other", ["POB_LENGUA_HABITUAL_OTRA"], relative_to="population")

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
SCHEMA.add("income_median_household", ["RENTA_MEDIANA_HOGAR"], agg="mean", weight_by="households")
SCHEMA.add("income_mean_household", ["RENTA_MEDIA_HOGAR"], agg="mean", weight_by="households")

# Income ranges
SCHEMA.add("households_no_income", ["HOGARES_SIN_RENTAS"], relative_to="households")
SCHEMA.add("households_income_1", ["HOGARES_RENTA_MENOS_6000"], relative_to="households")
SCHEMA.add("households_income_2", ["HOGARES_RENTA_6000_12000"], relative_to="households")
SCHEMA.add("households_income_3", ["HOGARES_RENTA_12000_18000"], relative_to="households")
SCHEMA.add("households_income_4", ["HOGARES_RENTA_18000_24000"], relative_to="households")
SCHEMA.add("households_income_5", ["HOGARES_RENTA_24000_30000"], relative_to="households")
SCHEMA.add("households_income_6", ["HOGARES_RENTA_30000_36000"], relative_to="households")
SCHEMA.add("households_income_7", ["HOGARES_RENTA_36000_42000"], relative_to="households")
SCHEMA.add("households_income_8", ["HOGARES_RENTA_42000_48000"], relative_to="households")

# Income per capita
SCHEMA.add("income_per_capita", ["RENTA_POR_HABITANTE"], agg="mean", weight_by="population")

# ---------------- Employment / Labor Force ----------------
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

# Contract type (important in Euskadi)
SCHEMA.add("employed_permanent_contract", ["OCUP_CONTRATO_INDEFINIDO"], relative_to="employed")
SCHEMA.add("employed_temporary_contract", ["OCUP_CONTRATO_TEMPORAL"], relative_to="employed")
SCHEMA.add("employed_self_employed", ["OCUP_AUTONOMO"], relative_to="employed")

# Employment status
SCHEMA.add("employed_full_time", ["OCUP_JORNADA_COMPLETA"], relative_to="employed")
SCHEMA.add("employed_part_time", ["OCUP_JORNADA_PARCIAL"], relative_to="employed")

# ---------------- Housing / Tenure ----------------
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
SCHEMA.add("population_same_municipality_5years", ["POB_MISMO_MUNICIPIO_5_ANOS"], relative_to="population")
SCHEMA.add("population_same_territory_5years", ["POB_MISMO_TERRITORIO_5_ANOS"], relative_to="population")
SCHEMA.add("population_different_territory_5years", ["POB_DISTINTO_TERRITORIO_5_ANOS"], relative_to="population")

# Foreign-born population
SCHEMA.add("population_foreign_born", ["POB_EXTRANJERO"], relative_to="population")
SCHEMA.add("population_naturalized", ["POB_NACIONALIZADO"], relative_to="population_foreign_born")

# Internal migration within Euskadi
SCHEMA.add("population_from_other_territory", ["POB_DE_OTRO_TERRITORIO"], relative_to="population")
SCHEMA.add("population_from_outside_euskadi", ["POB_DE_FUERA_EUSKADI"], relative_to="population")

# ---------------- Family Characteristics ----------------
SCHEMA.add("households_single_person", ["HOGARES_1_PERSONA"], relative_to="households")
SCHEMA.add("households_couple_no_children", ["HOGARES_PAREJA_SIN_HIJOS"], relative_to="households")
SCHEMA.add("households_couple_with_children", ["HOGARES_PAREJA_CON_HIJOS"], relative_to="households")
SCHEMA.add("households_single_parent", ["HOGARES_MONOPARENTAL"], relative_to="households")
SCHEMA.add("households_other_family", ["HOGARES_OTRO_TIPO_FAMILIA"], relative_to="households")

# ---------------- Euskadi-specific: Place of birth within Euskadi ----------------
SCHEMA.add("population_born_in_territory", ["POB_NACIDO_EN_TERRITORIO"], relative_to="population")
SCHEMA.add("population_born_in_other_territory", ["POB_NACIDO_EN_OTRO_TERRITORIO"], relative_to="population")
SCHEMA.add("population_born_in_spain", ["POB_NACIDO_EN_RESTO_ESPANA"], relative_to="population")

# ---------------- Euskadi-specific: Identification with Basque culture ----------------
SCHEMA.add("population_feels_basque", ["POB_SE_SIENTE_VASCO"], relative_to="population")
SCHEMA.add("population_feels_more_basque_than_spanish", ["POB_SE_SIENTE_MAS_VASCO_QUE_ESPANOL"], relative_to="population")
SCHEMA.add("population_feels_equally_basque_and_spanish", ["POB_SE_SIENTE_TANTO_VASCO_COMO_ESPANOL"], relative_to="population")
SCHEMA.add("population_feels_more_spanish_than_basque", ["POB_SE_SIENTE_MAS_ESPANOL_QUE_VASCO"], relative_to="population")
SCHEMA.add("population_feels_only_spanish", ["POB_SE_SIENTE_SOLO_ESPANOL"], relative_to="population")

# ---------------- Housing Characteristics (Basque-specific) ----------------
# Building type
SCHEMA.add("buildings_single_family", ["EDIFICIOS_UNIFAMILIARES"], relative_to="households")
SCHEMA.add("buildings_multi_family", ["EDIFICIOS_PLURIFAMILIARES"], relative_to="households")
SCHEMA.add("buildings_apartment", ["EDIFICIOS_BLOQUE_PISOS"], relative_to="households")

# Traditional Basque farmhouses (caserios)
SCHEMA.add("buildings_caserios", ["EDIFICIOS_CASERIOS"], relative_to="households")

__all__ = ["SCHEMA"]
