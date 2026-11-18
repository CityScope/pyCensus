"""Canonical derived columns added next to the raw census counts (idempotent: a column that already exists is never replaced).

Names match the simplified template of `transitlos.map.col_select`. Shares are 0-1 (clipped). Source columns are found by name, bare global name
first, then any `<source>_<name>` twin (non-WorldPop sources before WorldPop):
  * under18_share, over65_share, foreign_born_share, male_share, female_share = count / population;
  * university_share, education_basic_or_less_share            = count / sum of the education-level counts present (fallback population);
  * population_density                                          = population / km2 (geometry area, else H3 cell area);
  * jobs, pop_jobs_total, jobs_density, pop_jobs_density        = first jobs source (LODES WAC, BA, StatCan, SII ...) [+ population] (/ km2);
  * cars_per_household_ratio, zero_vehicle_households_share, transit_commute_share  (mobility; only where the census has car ownership / commute mode).
"""
from __future__ import annotations

import re
from typing import List, Optional

import numpy as np
import pandas as pd

JOBS_SOURCES = ("jobs_total", "workplaceJobs", "lodes_wac_jobsTotal", "ba_jobsTotal", "statcan_jobsTotal", "sii_jobsTotal", "inegi_jobsTotal", "jobsTotal")
#: 1.0 = shares in 0-1 (global schema); the US study sets 100 because its H3 tables (`census_h3`) hold every share as a percentage.
SHARE_SCALE = 1.0
EDU = ("educationPrimaryOrLessPopulation", "educationSecondaryPopulation", "educationOtherTertiaryPopulation", "educationUniversityPopulation")


def _find(df, name: str) -> Optional[str]:
    if name in df.columns:
        return name
    twins = [c for c in df.columns if isinstance(c, str) and c.endswith("_" + name) and not c.startswith("worldpop_") and "_" not in c[: -len(name) - 1]]
    if twins:
        return sorted(twins)[0]
    w = "worldpop_" + name
    return w if w in df.columns else None


def _num(df, col):
    return pd.to_numeric(df[col], errors="coerce").to_numpy(float)


def _share(num, den):
    with np.errstate(all="ignore"):
        return np.clip(np.where(den > 0, num / den, np.nan), 0.0, 1.0) * SHARE_SCALE


def area_km2(df) -> Optional[np.ndarray]:
    """Cell / polygon area in km2: H3 id column (cell area at its resolution), else the geometry (equal-area projection).

    Args:
        df: Table with an H3 id column or a geometry.

    Returns:
        Areas in km2, or None.
    """
    for idc in ("h3", "h3_cell"):
        if idc in df.columns and len(df):
            import h3

            res = h3.get_resolution(str(df[idc].iloc[0]))
            return np.full(len(df), h3.average_hexagon_area(res, unit="km^2"))
    geom = getattr(df, "geometry", None) if hasattr(df, "geometry") else None
    try:
        if geom is not None and df.crs is not None and len(df):
            return geom.to_crs(6933).area.to_numpy(float) / 1e6
    except Exception:  # noqa: BLE001
        return None
    return None


def add_derived_columns(df):
    """Add the missing canonical derived columns to `df` in place and return it.

    Args:
        df: Table with global columns.

    Returns:
        The same table.
    """
    cols = df.columns
    pop_c = "population" if "population" in cols else None
    if pop_c is None:
        return df
    pop = _num(df, pop_c)

    def put(name, values):
        if name not in df.columns:
            df[name] = values

    for name, base in (("under18_share", "under18Population"), ("over65_share", "over65Population"), ("foreign_born_share", "foreignBornPopulation"), ("male_share", "malePopulation"), ("female_share", "femalePopulation")):
        if name in df.columns:
            continue
        c = _find(df, base)
        if c:
            den = _num(df, "worldpop_population") if c.startswith("worldpop_") and "worldpop_population" in cols else pop
            put(name, _share(_num(df, c), den))
    edu_cols = [c for c in (_find(df, e) for e in EDU) if c and not c.startswith("worldpop_")]
    if edu_cols:
        tot = np.nansum(np.column_stack([_num(df, c) for c in edu_cols]), axis=1) if len(edu_cols) >= 3 else pop
        for name, base in (("university_share", "educationUniversityPopulation"), ("education_basic_or_less_share", "educationPrimaryOrLessPopulation")):
            c = _find(df, base)
            if c and name not in df.columns and not c.startswith("worldpop_"):
                put(name, _share(_num(df, c), tot))
    area = area_km2(df)
    if area is not None and "population_density" not in df.columns and "pop_density" not in df.columns:
        put("population_density", pop / np.where(area > 0, area, np.nan))
    jobs_c = next((c for c in JOBS_SOURCES if c in cols), None) or next((c for s in JOBS_SOURCES for c in cols if isinstance(c, str) and c.endswith("_" + s)), None)
    if jobs_c is not None:
        jobs = _num(df, jobs_c)
        put("jobs", jobs)
        put("pop_jobs_total", np.nansum(np.column_stack([pop, jobs]), axis=1))
        if area is not None:
            a = np.where(area > 0, area, np.nan)
            put("jobs_density", jobs / a)
            put("pop_jobs_density", np.nansum(np.column_stack([pop, jobs]), axis=1) / a)
    hh = _find(df, "households")
    cars = "cars" if "cars" in cols else None
    if hh and cars:
        put("cars_per_household_ratio", np.where(_num(df, hh) > 0, _num(df, cars) / _num(df, hh), np.nan))
    if hh and "zero_vehicle_households_share" not in df.columns:
        z = next((c for c in ("vehiclesHouseholds0", "acs5_vehiclesHouseholds0") if c in cols), None)
        if z:
            put("zero_vehicle_households_share", _share(_num(df, z), _num(df, hh)))
        elif "carHouseholds" in cols:
            put("zero_vehicle_households_share", SHARE_SCALE - _share(_num(df, "carHouseholds"), _num(df, hh)))
    if "transit_commute_share" not in df.columns:
        modes = [c for c in ("carCommuters", "publicTransportCommuters", "walkCommuters", "bikeCommuters") if c in cols]
        if "publicTransportCommuters" in modes and len(modes) >= 2:
            put("transit_commute_share", _share(_num(df, "publicTransportCommuters"), np.nansum(np.column_stack([_num(df, c) for c in modes]), axis=1)))
        elif "transit_share" in cols:
            put("transit_commute_share", df["transit_share"].to_numpy())
    # Germany (Zensus 2022 grid): owner rate (percent of dwellings) -> owner / renter households; churches' members -> religious population
    hh_c = _find(df, "households")
    if "destatis_homeownerRate" in cols and hh_c:
        own = np.clip(_num(df, "destatis_homeownerRate") / 100.0, 0.0, 1.0)
        put("owner_households_share", own)
        put("renter_households_share", 1.0 - own)
        put("ownerHouseholds", own * _num(df, hh_c))
        put("renterHouseholds", (1.0 - own) * _num(df, hh_c))
    if "destatis_populationOtherOrNoReligion" in cols:
        # Zensus 2022 only records membership of public-law religious communities (Roman Catholic, Protestant); everyone else is "other, none or no answer"
        put("religiousPopulation", np.clip(pop - _num(df, "destatis_populationOtherOrNoReligion"), 0.0, None))
    # topic shares added for the simplified census (each only where the census has the count column)
    emp = _find(df, "employedResidents")
    lf = _find(df, "laborForce")
    ad = _find(df, "adultPopulation")
    for name, num, den in (("minority_ethnicity_share", "minorityEthnicityPopulation", pop_c), ("poverty_share", "povertyPopulation", pop_c),
                           ("religious_share", "religiousPopulation", pop_c), ("minority_religion_share", "minorityReligionPopulation", pop_c),
                           ("renter_households_share", "renterHouseholds", hh), ("owner_households_share", "ownerHouseholds", hh)):
        c = _find(df, num)
        d = den if den in cols else (_find(df, den) if den else None)
        if c and d and name not in df.columns and not c.startswith("worldpop_"):
            put(name, _share(_num(df, c), _num(df, d)))
    def usable(num, den):   # numerator with data that does not exceed its whole (2026-11-15: mixed-source labor force / working-age pairs)
        n, d = np.nansum(_num(df, num)), np.nansum(_num(df, den))
        return n > 0 and d > 0 and n <= 1.05 * d

    def same_source_pairs(num_name, den_names):   # (prefix_num, prefix_den) of one source first, then the canonical / found columns
        out = []
        for c in df.columns:
            if isinstance(c, str) and c.endswith("_" + num_name) and not c.startswith("worldpop_"):
                pre = c[: -len(num_name)]
                out += [(c, pre + dn) for dn in den_names if pre + dn in df.columns]
        return out

    un = _find(df, "unemployedResidents")
    if "unemployment_rate" not in df.columns:
        for a, b in ([(un, lf)] if un and lf else []) + same_source_pairs("unemployedResidents", ["laborForce"]):
            if usable(a, b):
                put("unemployment_rate", _share(_num(df, a), _num(df, b)))
                break
    if "labor_force_participation_rate" not in df.columns:
        p16 = _find(df, "population16plus")
        cands = same_source_pairs("laborForce", ["population16plus", "adultPopulation"]) + [(lf, d) for d in (p16, ad) if lf and d]
        for a, b in cands:   # labor force over the population 16+ (its universe in the ACS / Eustat), else over the adult population
            if usable(a, b):
                put("labor_force_participation_rate", _share(_num(df, a), _num(df, b)))
                break
    modes_all = [c for c in ("carCommuters", "publicTransportCommuters", "walkCommuters", "bikeCommuters") if c in cols]
    if len(modes_all) >= 2:
        tot_m = np.nansum(np.column_stack([_num(df, c) for c in modes_all]), axis=1)
        for name, base in (("car_commute_share", "carCommuters"), ("walk_commute_share", "walkCommuters"), ("bike_commute_share", "bikeCommuters")):
            if base in cols and name not in df.columns:
                put(name, _share(_num(df, base), tot_m))
    # US-template names (US cities): the template looks for these exact names on `us=True` maps.
    if any(isinstance(c, str) and c.startswith("acs5_") for c in cols):
        for scope in ("national", "state", "municipal"):
            for a, b in (("democrat_share", "left_share"), ("republican_share", "right_share")):
                if f"elec_{scope}_{a}" not in df.columns and f"elec_{scope}_{b}" in df.columns:
                    df[f"elec_{scope}_{a}"] = df[f"elec_{scope}_{b}"]
        for new, old in (("median_household_income", "medianHouseholdIncome"), ("mean_household_size", "acs5_householdSizeMean"), ("income_gini_index", "acs5_incomeGini")):
            if new not in df.columns and old in df.columns:
                df[new] = df[old]
        for new, old in (("white_share", "dhc_whitePopulation"), ("black_share", "dhc_blackPopulation")):
            if new not in df.columns and old in df.columns:
                df[new] = _share(_num(df, old), pop)
    add_gap_columns(df)
    return df


# ---------------------------------------------------------------------------------------------------------------------------
# Global columns that a source already carries under another (local) name or as a rate / sum of local columns. Each rule says where the
# value comes from; nothing is added when the global column exists or no source column is present (never from WorldPop, never made up).
_COPY_RULES = (   # global name <- first present local column (the same meaning; approximations are noted)
    ("ownerHouseholds", ("acs5_householdsOwner", "statcan_tenureOwner")),
    ("renterHouseholds", ("acs5_householdsRenter", "statcan_tenureRenter")),
    ("singlePersonHouseholds", ("acs5_livingAloneHouseholds", "statcan_hhTypeOnePersonHouseholds", "statcan_hhSize1Person", "destatis_households1Person", "moi_householdsSinglePerson")),
    ("incomePerCapitaMean", ("acs5_incomeMeanCapita", "ine_incomeGrossPersonMean")),
    ("giniIndex", ("acs5_incomeGini",)),
    ("births", ("acs5_womenWithBirthPast12Months",)),   # women who gave birth in the past 12 months (ACS B13002)
    ("femaleEmployedResidents", ("acs5_employedFemalePopulation16plus",)),
    ("disabledPopulation", ("acs5_disabilityPopulation", "inegi_populationDisability")),
    ("dwellings", ("acs5_housingUnits", "dhc_housingUnits")),
    ("christianPopulation", ("statcan_religionChristian",)),
    ("muslimPopulation", ("statcan_religionMuslim",)),
    ("noReligionPopulation", ("statcan_religionNoReligionAndSecularPerspectives", "inegi_populationNoReligion")),
    ("selfEmployedResidents", ("statcan_classWorkerSelfEmployed",)),
    ("residentsForMoreThan5Years", ("statcan_mobility5yNonMovers",)),   # non-movers over the last 5 years (same address)
    ("majorityEthnicityPopulation", ("statcan_visMinNotAVisibleMinority", "dhc_whitePopulation")),   # not a visible minority (Canada); white alone (US, includes Hispanic whites)
    ("rent_per_home_mean", ("statcan_tenantAverageMonthlyShelterCostsForRentedDwellings",)),   # average monthly shelter cost of tenants (includes utilities)
    ("employedResidents", ("ba_pendler_residentWorkers",)),   # employees subject to social insurance by place of residence (Germany)
)
_SUM_RULES = (    # global name <- sum of local columns (all must be present)
    ("lowIncomeHouseholds", ("acs5_incomeHouseholdsUnder10k", "acs5_incomeHouseholds10kTo25k")),   # households under 25,000 USD
    ("christianPopulation", ("inegi_populationCatholic", "inegi_populationEvangelicalProtestant")),
    ("christianPopulation", ("destatis_populationRomanCatholic", "destatis_populationProtestant")),   # members of the two large churches (Zensus 2022)
    ("motorizedCommuters", ("acs5_driveAloneCommuters", "acs5_carpoolCommuters", "acs5_motorcycleCommuters")),
    ("motorizedCommuters", ("carCommuters", "motorcycleCommuters")),
)
_RATE_RULES = (   # global count <- rate (0-1 or 0-100) x base column
    ("ownerHouseholds", "cbs_owner_rate", "households"), ("renterHouseholds", "cbs_renter_rate", "households"),
    ("ownerHouseholds", "ine_tenure_owned_share", "households"), ("renterHouseholds", "ine_tenure_rented_share", "households"),
    ("singlePersonHouseholds", "ine_singlePersonHouseholdsShare", "households"),
    ("twoCarHouseholds", "cbs_households_2plus_vehicle_rate", "households"),
)
_COMMUTE_BINS = (("statcan_commuteTimeLessThan15Minutes", 7.5), ("statcan_commuteTime15To29Minutes", 22.0), ("statcan_commuteTime30To44Minutes", 37.0),
                 ("statcan_commuteTime45To59Minutes", 52.0), ("statcan_commuteTime60MinutesAndOver", 75.0))   # bin mid-points (minutes; the open bin 75)


def add_gap_columns(df):
    """Add global columns that the data already holds under local names (see the rules above); idempotent, in place.

    Args:
        df: Table.

    Returns:
        The same table.
    """
    cols = df.columns

    def have(c):
        return c in df.columns

    for glob, cands in _COPY_RULES:
        if glob in df.columns:
            continue
        c = next((x for x in cands if have(x)), None)
        if c:
            df[glob] = df[c]
    for glob, parts in _SUM_RULES:
        if glob not in df.columns and all(have(p) for p in parts):
            df[glob] = np.nansum(np.column_stack([_num(df, p) for p in parts]), axis=1)
        elif glob == "motorizedCommuters" and glob not in df.columns:
            pass
    # motorized commuters: car (+ motorcycle where the source has it)
    if "motorizedCommuters" not in df.columns and have("carCommuters"):
        df["motorizedCommuters"] = df["carCommuters"]
    for glob, rate, base in _RATE_RULES:
        if glob in df.columns or not have(rate):
            continue
        b = _find(df, base)
        if b is None:
            continue
        r = _num(df, rate)
        r = np.where(np.nanmax(r) > 1.0001, r / 100.0, r)
        df[glob] = r * _num(df, b)
    if "carHouseholds" not in df.columns and have("cbs_no_vehicle_rate"):
        b = _find(df, "households")
        if b:
            r = _num(df, "cbs_no_vehicle_rate"); r = np.where(np.nanmax(r) > 1.0001, r / 100.0, r)
            df["carHouseholds"] = (1.0 - r) * _num(df, b)
    # Germany (Zensus 2022 grid): average rent per home = rent per m2 x average dwelling area; dwellings = occupied (households) / (1 - vacancy rate)
    if "rent_per_home_mean" not in df.columns and have("destatis_rentPerM2Mean") and have("destatis_homeSizeM2Mean"):
        df["rent_per_home_mean"] = _num(df, "destatis_rentPerM2Mean") * _num(df, "destatis_homeSizeM2Mean")
    if "dwellings" not in df.columns and have("destatis_vacancyRate"):
        hh_ = _find(df, "households")
        if hh_:
            v = _num(df, "destatis_vacancyRate"); v = np.where(np.nanmax(v) > 1.0001, v / 100.0, v)
            with np.errstate(all="ignore"):
                df["dwellings"] = np.where((v >= 0) & (v < 0.9), _num(df, hh_) / (1.0 - v), np.nan)
    # adults = residents - under 18 (wherever the census gives the under-18 count)
    if "adultPopulation" not in df.columns and "population" in df.columns and "under18Population" in df.columns:
        df["adultPopulation"] = np.clip(_num(df, "population") - _num(df, "under18Population"), 0.0, None)
    # workplace jobs / population + jobs from the jobs column of the source (LODES, BA, StatCan, ...)
    if "workplaceJobs" not in df.columns and "jobs" in df.columns:
        df["workplaceJobs"] = df["jobs"]
    if "populationAndJobs" not in df.columns and "pop_jobs_total" in df.columns:
        df["populationAndJobs"] = df["pop_jobs_total"]
    # mean commute time from the bins (Toronto: StatCan commuting duration), bin mid-points
    if "commuteTimeMean" not in df.columns and all(have(c) for c, _ in _COMMUTE_BINS):
        w = np.column_stack([_num(df, c) for c, _ in _COMMUTE_BINS]); m = np.array([v for _, v in _COMMUTE_BINS])
        tot = np.nansum(w, axis=1)
        with np.errstate(all="ignore"):
            df["commuteTimeMean"] = np.where(tot > 0, np.nansum(w * m, axis=1) / tot, np.nan)
    return df
