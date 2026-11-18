"""Generate `schema/toronto_schema.json` from the City of Toronto "Neighbourhood Profiles 2021" workbook (one row per characteristic,
one column per neighbourhood). Run once after downloading the workbook; the loader then maps every feature to its workbook row.

    python -m pycensus.countries.canada.toronto.build_schema path/to/nbhd_2021_census_profile_full_158model.xlsx
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

# (workbook section title starts with, feature tag, max indent depth of children kept, unit/weight kind)
SECTIONS = [
    ("Total - Age groups of the population", "age", 2),
    ("Total - Persons in private households", "personsHh", 2),
    ("Total - Marital status", "marital", 3),
    ("Total - LIM low-income status", "limAt", 1),
    ("Total - LICO low-income status", "licoAt", 1),
    ("Total - Occupied private dwellings by structural type", "dwelling", 1),
    ("Total - Private households by household size", "hhSize", 1),
    ("Total - Household type", "hhType", 3),
    ("Total - Household total income groups in 2020", "hhIncome", 2),
    ("Total - Private households by tenure", "tenure", 1),
    ("Total - Occupied private dwellings by condominium status", "condo", 1),
    ("Total - Occupied private dwellings by number of bedrooms", "bedrooms", 1),
    ("Total - Private households by housing suitability", "suitability", 1),
    ("Total - Occupied private dwellings by period of construction", "built", 1),
    ("Total - Occupied private dwellings by dwelling condition", "condition", 1),
    ("Total - Occupied private dwellings by housing indicators", "housingIndicator", 1),
    ("Total - Owner households in non-farm", "owner", 1),
    ("Total - Tenant households in non-farm", "tenant", 1),
    ("Total - Citizenship for the population", "citizenship", 2),
    ("Total - Immigrant status and period of immigration", "immigration", 2),
    ("Total - Generation status", "generation", 1),
    ("Total - Visible minority", "visMin", 2),
    ("Total - Indigenous identity", "indigenous", 1),
    ("Total - Religion for the population", "religion", 2),
    ("Total - Mobility status 1 year ago", "mobility1y", 2),
    ("Total - Mobility status 5 years ago", "mobility5y", 2),
    ("Total - Knowledge of official languages", "officialLang", 1),
    ("Total - First official language spoken", "firstOfficialLang", 1),
    ("Total - Population aged 15 years and over by labour force status", "labour", 2),
    ("Total - Highest certificate, diploma or degree for the population aged 25 to 64", "edu25to64", 3),
    ("Total - Highest certificate, diploma or degree for the population aged 15 years and over", "edu15", 3),
    ("Total - Labour force aged 15 years and over by occupation - Broad category", "occupation", 1),
    ("Total - Labour force aged 15 years and over by industry - Sectors", "industry", 1),
    ("Total - Labour force aged 15 years and over by class of worker", "classWorker", 2),
    ("Total - Place of work status", "placeOfWork", 1),
    ("Total - Main mode of commuting", "commuteMode", 2),
    ("Total - Commuting duration", "commuteTime", 1),
    ("Total - Commuting destination", "commuteDest", 1),
]
SCALARS = {  # exact row label -> (feature name, type)
    "Average age of the population": ("ageMean", "mean"),
    "Median age of the population": ("medianAge", "median"),
    "Average household size": ("hhSizeMean", "mean"),
    "Average number of rooms per dwelling": ("roomsMean", "mean"),
    "Average size of census families": ("familySizeMean", "mean"),
    "Participation rate": ("participationRate", "rate"),
    "Employment rate": ("employmentRate", "rate"),
    "Unemployment rate": ("unemploymentRate", "rate"),
}


def camel(text: str) -> str:
    """CamelCase feature name from a census characteristic label (units and sample notes removed, at most 70 characters).

    Args:
        text: Characteristic label.

    Returns:
        The name.
    """
    text = re.sub(r"\s*\(%\)|\s*-\s*25% sample data|\$|,", "", text)
    text = text.replace("&", " and ")
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(w[:1].upper() + w[1:] for w in words)[:70]


def build(xlsx: str) -> list:
    """Schema features of the Toronto neighbourhood profile spreadsheet, one per characteristic row.

    Args:
        xlsx: Path of the profile spreadsheet.

    Returns:
        List of feature dicts.
    """
    ws = openpyxl.load_workbook(xlsx, read_only=True, data_only=True).worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True)]
    labels = [(r[0] or "") for r in rows]
    features, used = [], set()

    def add(name, row_label, section, kind, unit, definition, rel=None, cat="population"):
        base = name = name[:80]
        k = 2
        while name in used:
            name = f"{base}{k}"; k += 1
        used.add(name)
        f = {"category": cat, "feature_name": name, "original_name": row_label.strip(), "country": "canada", "source": "toronto",
             "codes": [f"{section}||{row_label.strip()}"], "definition": definition, "type": kind, "unit": unit}
        if kind == "count":
            f.update({"resampling_up": "sum", "resampling_down": "weighted_divide"})
            if rel:
                f["relative_to"] = rel
        else:
            f.update({"resampling_up": "weighted_mean", "resampling_down": "weighted_mean", "resampling_weight": rel or "population"})
        features.append(f)

    for i, label in enumerate(labels):
        if label in SCALARS:
            name, kind = SCALARS[label]
            add(name, label, "", kind, "%" if kind == "rate" else "", f"{label} (2021 Census, City of Toronto neighbourhood profile).")
    # income statistics sections hold several median/average rows
    for i, label in enumerate(labels):
        s = label.strip()
        m = re.match(r"^(Median|Average) (total|after-tax|market|employment)\s+income\s+in 2020\s+among recipients \(\$\)$", s)
        if m:
            kind = "median" if m.group(1) == "Median" else "mean"
            sec = next(labels[k] for k in range(i, -1, -1) if not labels[k].startswith(" "))   # the section header this row sits under
            add(f"income{m.group(2).replace('-', '').title()}{m.group(1)}Recipients", label, sec, kind, "CAD", f"{s} (2021 Census).", rel="population15plus", cat="income")
    for title, tag, depth in SECTIONS:
        start = next((i for i, l in enumerate(labels) if l.startswith(title)), None)
        if start is None:
            continue
        end = start + 1
        while end < len(labels) and labels[end].startswith(" "):
            end += 1
        add(f"{tag}Total", labels[start], "", "count", "", f"{labels[start].replace(' - 25% sample data', '')}: total (denominator).")
        features[-1]["codes"] = [f"{labels[start]}||{labels[start]}"]
        for j in range(start + 1, end):
            raw = labels[j]
            indent = (len(raw) - len(raw.lstrip(" "))) // 2
            if indent > depth or not raw.strip():
                continue
            add(f"{tag}{camel(raw)}", raw, labels[start], "count", "", f"{labels[start].replace(' - 25% sample data', '').replace('Total - ', '')}: {raw.strip()}.", rel=f"{tag}Total")
            features[-1]["codes"] = [f"{labels[start]}||{raw}"]
    return features


GLOBAL = [  # (global feature name, category, [codes: "section||label"; a leading "-" subtracts the row], definition)
    ("population", "population", ["Total - Age groups of the population - 25% sample data||Total - Age groups of the population - 25% sample data"], "Total population (2021 Census)."),
    ("over65Population", "population", ["Total - Age groups of the population - 25% sample data||65 years and over"], "Population aged 65 and over."),
    ("under18Population", "population", ["Total - LIM low-income status in 2020 for the population in private households - 25% sample data||0 to 17 years"], "Population under 18 in private households."),
    ("adultPopulation", "population", ["Total - LIM low-income status in 2020 for the population in private households - 25% sample data||18 to 64 years", "Total - LIM low-income status in 2020 for the population in private households - 25% sample data||65 years and over"], "Population aged 18 and over in private households."),
    ("households", "population", ["Total - Private households by household size - 25% sample data||Total - Private households by household size - 25% sample data"], "Private households."),
    ("medianHouseholdIncome", "income", ["Total - Income statistics for private households - 25% sample data||Median total income of household in 2020 ($)"], "Median total household income in 2020 (CAD)."),
    ("meanHouseholdIncome", "income", ["Total - Income statistics for private households - 25% sample data||Average total income of household in 2020 ($)"], "Average total household income in 2020 (CAD)."),
    ("povertyPopulation", "income", ["||In low income based on the Low-income measure, after tax (LIM-AT)"], "People in low income (LIM-AT)."),
    ("foreignBornPopulation", "migration", ["Total - Immigrant status and period of immigration for the population in private households - 25% sample data||Immigrants"], "Immigrant population (born abroad)."),
    ("minorityEthnicityPopulation", "raceEthinicity", ["Total - Visible minority for the population in private households - 25% sample data||Total visible minority population"], "Visible minority population."),
    ("religiousPopulation", "religion", ["Total - Religion for the population in private households - 25% sample data||Total - Religion for the population in private households - 25% sample data", "-Total - Religion for the population in private households - 25% sample data||No religion and secular perspectives"], "Population reporting a religion (total minus no religion)."),
    ("minorityReligionPopulation", "religion", [f"Total - Religion for the population in private households - 25% sample data||{r}" for r in ("Buddhist", "Hindu", "Jewish", "Muslim", "Sikh", "Traditional (North American Indigenous) spirituality", "Other religions and spiritual traditions")], "Population with a non-Christian religion."),
    ("laborForce", "employment", ["Total - Population aged 15 years and over by labour force status - 25% sample data||In the labour force"], "Labour force (employed + unemployed), aged 15+."),
    ("employedResidents", "employment", ["Total - Population aged 15 years and over by labour force status - 25% sample data||Employed"], "Employed residents aged 15+."),
    ("unemployedResidents", "employment", ["Total - Population aged 15 years and over by labour force status - 25% sample data||Unemployed"], "Unemployed residents aged 15+."),
    ("carCommuters", "transport", ["Total - Main mode of commuting for the employed labour force aged 15 years and over with a usual place of work or no fixed workplace address - 25% sample data||Car, truck or van"], "Employed residents commuting by car, truck or van."),
    ("publicTransportCommuters", "transport", ["Total - Main mode of commuting for the employed labour force aged 15 years and over with a usual place of work or no fixed workplace address - 25% sample data||Public transit"], "Employed residents commuting by public transit."),
    ("walkCommuters", "transport", ["Total - Main mode of commuting for the employed labour force aged 15 years and over with a usual place of work or no fixed workplace address - 25% sample data||Walked"], "Employed residents commuting on foot."),
    ("bikeCommuters", "transport", ["Total - Main mode of commuting for the employed labour force aged 15 years and over with a usual place of work or no fixed workplace address - 25% sample data||Bicycle"], "Employed residents commuting by bicycle."),
    ("educationPrimaryOrLessPopulation", "education", ["Total - Highest certificate, diploma or degree for the population aged 15 years and over in private households - 25% sample data||No certificate, diploma or degree"], "Population 15+ without a certificate, diploma or degree."),
    ("educationSecondaryPopulation", "education", ["Total - Highest certificate, diploma or degree for the population aged 15 years and over in private households - 25% sample data||High (secondary) school diploma or equivalency certificate"], "Population 15+ whose highest credential is secondary school."),
    ("educationOtherTertiaryPopulation", "education", ["Total - Highest certificate, diploma or degree for the population aged 15 years and over in private households - 25% sample data||Postsecondary certificate or diploma below bachelor level"], "Population 15+ with a postsecondary certificate/diploma below bachelor level."),
    ("educationUniversityPopulation", "education", ["Total - Highest certificate, diploma or degree for the population aged 15 years and over in private households - 25% sample data||Bachelor’s degree or higher"], "Population 15+ with a bachelor's degree or higher."),
]


def global_features() -> list:
    """Schema features of the global columns taken from the Toronto profile.

    Returns:
        List of feature dicts.
    """
    out = []
    for name, cat, codes, definition in GLOBAL:
        out.append({"category": cat, "feature_name": name, "original_name": codes[0].split("||")[-1], "country": "canada", "source": "toronto",
                    "codes": codes, "definition": definition + " (2021 Census, City of Toronto neighbourhood profile.)", "type": "count", "unit": "",
                    "resampling_up": "sum", "resampling_down": "weighted_divide", **({} if name in ("population", "households") else {"relative_to": "population"})})
        if name in ("medianHouseholdIncome", "meanHouseholdIncome"):
            out[-1].update({"type": "median" if name.startswith("median") else "mean", "resampling_up": "weighted_mean", "resampling_down": "weighted_mean", "resampling_weight": "households"})
            out[-1].pop("relative_to", None)
    return out


if __name__ == "__main__":
    have = None
    feats = global_features() + [f for f in build(sys.argv[1]) if f["feature_name"] not in {g[0] for g in GLOBAL}]
    out = Path(__file__).parent.parent / "schema" / "toronto_schema.json"
    out.write_text(json.dumps({"country": "canada", "source": "toronto", "full_name": "City of Toronto Neighbourhood Profiles (2021 Census of Population, 158 neighbourhoods)",
                               "description": "Statistics Canada 2021 Census characteristics aggregated by the City of Toronto to its 158 social-planning neighbourhoods (open data).",
                               "source_url": "https://open.toronto.ca/dataset/neighbourhood-profiles/", "years": [2021], "levels": ["neighbourhood"],
                               "features": feats}, ensure_ascii=False, indent=1))
    print(len(feats), "features ->", out)
