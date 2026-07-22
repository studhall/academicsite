from __future__ import annotations

import argparse
import json
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd


STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}
FIPS_STATE = {value: key for key, value in STATE_FIPS.items()}
PRIORITY_YEARS = {1998, 2000, 2001, 2003, 2004, 2017, 2018, 2021}

POPULATION_SOURCES = {
    "1998": (
        "stch-icen1998.txt",
        "https://www2.census.gov/programs-surveys/popest/tables/"
        "1990-2000/intercensal/st-co/stch-icen1998.txt",
    ),
    "1999": (
        "stch-icen1999.txt",
        "https://www2.census.gov/programs-surveys/popest/tables/"
        "1990-2000/intercensal/st-co/stch-icen1999.txt",
    ),
    "2000_2010": (
        "st-est00int-alldata.csv",
        "https://www2.census.gov/programs-surveys/popest/datasets/"
        "2000-2010/intercensal/state/st-est00int-alldata.csv",
    ),
    "2010_2020": (
        "nst-est2020.csv",
        "https://www2.census.gov/programs-surveys/popest/datasets/"
        "2010-2020/state/totals/nst-est2020.csv",
    ),
    "2020_2024": (
        "NST-EST2024-ALLDATA.csv",
        "https://www2.census.gov/programs-surveys/popest/datasets/"
        "2020-2024/state/totals/NST-EST2024-ALLDATA.csv",
    ),
}

# These mappings are intentionally conservative. The year-specific raw code
# remains available even when it is not safe to harmonize across directories.
HARMONIZED = {
    "ownership": {
        "private_unspecified": ("Private (type unspecified)", {"PV", "PVT"}),
        "private_nonprofit": ("Private nonprofit", {"PVTN"}),
        "private_forprofit": ("Private for-profit", {"PVTP"}),
        "local_government": ("Local/county government", {"LCCG"}),
        "state_government": ("State government", {"STG"}),
        "tribal_government": ("Tribal government", {"TBG"}),
        "federal_dod": ("Federal: Department of Defense", {"DDF"}),
        "federal_ihs": ("Federal: Indian Health Service", {"IH", "IHS"}),
        "federal_va": ("Federal: Veterans Affairs", {"VAMC"}),
    },
    "center_type": {
        "substance_use": ("Substance use treatment", {"SA", "TX"}),
        "detoxification": ("Detoxification", {"DT"}),
        "transitional_housing": ("Transitional housing/halfway house", {"HH"}),
        "mental_health": ("Mental health treatment", {"MH"}),
        "cooccurring": ("Co-occurring mental health and substance use", {"SUMH"}),
    },
    "setting": {
        "outpatient": (
            "Outpatient",
            {"OP", "OD", "ODT", "OIT", "OMB", "ORT", "PH"},
        ),
        "residential": ("Residential", {"RES", "RD", "RL", "RS"}),
        "hospital_inpatient": ("Hospital inpatient", {"HI", "HID", "HIT"}),
    },
    "payment": {
        "medicare": ("Medicare", {"MC"}),
        "medicaid": ("Medicaid", {"MD"}),
        "military_insurance": ("Military insurance", {"MI"}),
        "private_insurance": ("Private health insurance", {"PI"}),
        "self_pay": ("Cash or self-payment", {"SF"}),
        "state_financed": ("State-financed insurance", {"SI"}),
        "payment_assistance": ("Payment assistance", {"PA", "OA"}),
        "sliding_fee": ("Sliding fee scale", {"SS"}),
    },
    "service_family": {
        "substance_use_treatment": ("Substance use treatment", {"SA", "TX"}),
        "detoxification": ("Detoxification", {"DT"}),
        "transitional_housing": ("Transitional housing/halfway house", {"HH"}),
        "cooccurring": (
            "Co-occurring mental health and substance use treatment",
            {"SUMH"},
        ),
        "outpatient_treatment": (
            "Outpatient treatment",
            {"OP", "OIT", "ORT", "OMB", "PH"},
        ),
        "residential_treatment": ("Residential treatment", {"RES", "RL", "RS"}),
        "hospital_inpatient": ("Hospital inpatient treatment", {"HI", "HID", "HIT"}),
        "opioid_treatment_program": (
            "SAMHSA-certified opioid treatment program",
            {"OTP"},
        ),
        "methadone": ("Methadone services", {"MU", "MM", "DM"}),
        "buprenorphine": ("Buprenorphine services", {"BU", "BUM", "UB"}),
        "naltrexone": ("Naltrexone services", {"NU", "NXN", "VTRL"}),
        "telehealth": ("Telehealth/telemedicine", {"TELE"}),
    },
}
FILTER_BITS = {
    group: {value: 1 << index for index, value in enumerate(values)}
    for group, values in HARMONIZED.items()
}


def split_codes(value: object) -> set[str]:
    if pd.isna(value):
        return set()
    return {part.strip() for part in str(value).split("|") if part.strip()}


def review_counts(review_path: Path | None) -> dict[int, int]:
    if review_path is None or not review_path.exists():
        return {}
    review = pd.read_csv(review_path, dtype=str).fillna("")
    completed = review.loc[review["review_complete"].str.lower().eq("yes")]
    return (
        completed.groupby(completed["directory_year"].astype(int))
        .size()
        .astype(int)
        .to_dict()
    )


def download_population_sources(cache_dir: Path) -> dict[str, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, (filename, url) in POPULATION_SOURCES.items():
        destination = cache_dir / filename
        if not destination.exists():
            print(f"Downloading {url}")
            urllib.request.urlretrieve(url, destination)
        paths[key] = destination
    return paths


def read_population(cache_dir: Path, survey_years: set[int]) -> pd.DataFrame:
    paths = download_population_sources(cache_dir)
    rows: list[dict[str, object]] = []

    for year in (1998, 1999):
        totals: dict[str, int] = defaultdict(int)
        with paths[str(year)].open(encoding="ascii") as source:
            for line in source:
                fields = line.split()
                if len(fields) != 6:
                    continue
                totals[fields[1][:2]] += int(fields[5])
        for state_fips, population in totals.items():
            if state_fips in FIPS_STATE:
                rows.append(
                    {
                        "survey_year": year,
                        "state": FIPS_STATE[state_fips],
                        "state_fips": state_fips,
                        "population": population,
                        "source": POPULATION_SOURCES[str(year)][1],
                        "vintage": "1990-2000 intercensal",
                    }
                )

    early = pd.read_csv(paths["2000_2010"], low_memory=False)
    early = early.loc[
        early["STATE"].astype(str).str.zfill(2).isin(FIPS_STATE)
        & early["SEX"].eq(0)
        & early["ORIGIN"].eq(0)
        & early["RACE"].eq(0)
        & early["AGEGRP"].eq(0)
    ].copy()
    for year in range(2000, 2010):
        column = f"POPESTIMATE{year}"
        for row in early.itertuples(index=False):
            state_fips = str(row.STATE).zfill(2)
            rows.append(
                {
                    "survey_year": year,
                    "state": FIPS_STATE[state_fips],
                    "state_fips": state_fips,
                    "population": int(getattr(row, column)),
                    "source": POPULATION_SOURCES["2000_2010"][1],
                    "vintage": "2000-2010 intercensal",
                }
            )

    late = pd.read_csv(paths["2010_2020"], dtype={"STATE": str})
    late = late.loc[
        late["SUMLEV"].astype(str).str.zfill(3).eq("040")
        & late["STATE"].astype(str).str.zfill(2).isin(FIPS_STATE)
    ].copy()
    for year in range(2010, 2021):
        column = f"POPESTIMATE{year}"
        for row in late.itertuples(index=False):
            state_fips = str(row.STATE).zfill(2)
            rows.append(
                {
                    "survey_year": year,
                    "state": FIPS_STATE[state_fips],
                    "state_fips": state_fips,
                    "population": int(getattr(row, column)),
                    "source": POPULATION_SOURCES["2010_2020"][1],
                    "vintage": "2010-2020 estimates",
                }
            )

    recent = pd.read_csv(paths["2020_2024"], dtype={"STATE": str})
    recent = recent.loc[
        recent["SUMLEV"].astype(str).str.zfill(3).eq("040")
        & recent["STATE"].astype(str).str.zfill(2).isin(FIPS_STATE)
    ].copy()
    for year in range(2021, 2025):
        column = f"POPESTIMATE{year}"
        for row in recent.itertuples(index=False):
            state_fips = str(row.STATE).zfill(2)
            rows.append(
                {
                    "survey_year": year,
                    "state": FIPS_STATE[state_fips],
                    "state_fips": state_fips,
                    "population": int(getattr(row, column)),
                    "source": POPULATION_SOURCES["2020_2024"][1],
                    "vintage": "2020-2024 estimates",
                }
            )
    population = pd.DataFrame(rows)
    population = population.loc[population["survey_year"].isin(survey_years)].copy()
    duplicates = population.duplicated(["survey_year", "state_fips"])
    if duplicates.any():
        raise ValueError("Duplicate state-year population rows")
    expected = len(survey_years) * len(STATE_FIPS)
    if len(population) != expected:
        raise ValueError(f"Expected {expected} population rows, found {len(population)}")
    return population.sort_values(["survey_year", "state_fips"]).reset_index(drop=True)


def asked_codes(availability: pd.DataFrame, offered_codes: set[str]) -> set[str]:
    asked = availability.loc[
        availability["asked"].astype(str).str.lower().eq("true"), "code"
    ].dropna()
    return set(asked.astype(str)) | offered_codes


def best_code_labels(availability: pd.DataFrame) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in availability.itertuples(index=False):
        code = str(row.code)
        label = "" if pd.isna(row.label) else str(row.label).strip()
        if label and len(label) <= 120 and code not in labels:
            labels[code] = label
    return labels


def harmonized_values(codes: set[str], group: str) -> str:
    values = [
        value
        for value, (_, mapped_codes) in HARMONIZED[group].items()
        if codes & mapped_codes
    ]
    return "|".join(values)


def harmonized_mask(codes: set[str], group: str) -> int:
    return sum(
        FILTER_BITS[group][value]
        for value, (_, mapped_codes) in HARMONIZED[group].items()
        if codes & mapped_codes
    )


def availability_rows(
    directory_year: int,
    survey_year: int,
    asked: set[str],
    labels: dict[str, str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group, values in HARMONIZED.items():
        for value, (label, mapped_codes) in values.items():
            notes = ""
            comparable = True
            if group == "ownership" and value == "private_unspecified":
                notes = "Earlier directories do not consistently separate private ownership type."
                comparable = False
            rows.append(
                {
                    "directory_year": directory_year,
                    "survey_year": survey_year,
                    "characteristic": group,
                    "value": value,
                    "label": label,
                    "asked": bool(asked & mapped_codes),
                    "comparable": comparable,
                    "notes": notes,
                }
            )
    for code in sorted(asked):
        rows.append(
            {
                "directory_year": directory_year,
                "survey_year": survey_year,
                "characteristic": "original_code",
                "value": code,
                "label": labels.get(code, code),
                "asked": True,
                "comparable": False,
                "notes": "Original SAMHSA directory code; meaning and availability may vary by year.",
            }
        )
    return rows


def build_crosswalk() -> pd.DataFrame:
    rows = []
    for group, values in HARMONIZED.items():
        for value, (label, codes) in values.items():
            for code in sorted(codes):
                rows.append(
                    {
                        "characteristic": group,
                        "harmonized_value": value,
                        "harmonized_label": label,
                        "original_code": code,
                        "notes": (
                            "Conservative dashboard harmonization; consult the "
                            "year-specific original code label before trend use."
                        ),
                    }
                )
    return pd.DataFrame(rows)


def build_year_shard(
    year_dir: Path,
    geocoding: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
    facilities = pd.read_csv(
        year_dir / "facilities.csv",
        dtype={"state": str, "zip": str},
        low_memory=False,
    )
    services = pd.read_csv(
        year_dir / "facility_services.csv",
        dtype={"listing_id": str, "code": str},
        low_memory=False,
    )
    availability = pd.read_csv(
        year_dir / "service_availability.csv",
        dtype={"code": str},
        low_memory=False,
    )

    services = services.loc[
        services["known_code"].astype(str).str.lower().eq("true")
    ].copy()
    codes_by_listing = (
        services.groupby("listing_id")["code"]
        .agg(lambda values: "|".join(sorted(set(values.dropna().astype(str)))))
        .to_dict()
    )
    offered = set(services["code"].dropna().astype(str))
    asked = asked_codes(availability, offered)
    labels = best_code_labels(availability)

    geo_columns = [
        "listing_id",
        "county_fips",
        "geocode_method",
        "geocode_confidence",
    ]
    if geocoding is not None and not geocoding.empty:
        facilities = facilities.drop(columns=geo_columns[1:], errors="ignore").merge(
            geocoding[[col for col in geo_columns if col in geocoding.columns]],
            on="listing_id",
            how="left",
        )
    for column in geo_columns[1:]:
        if column not in facilities:
            facilities[column] = ""
        facilities[column] = facilities[column].fillna("").astype(str)
    facilities["state"] = facilities["state"].fillna("").astype(str)
    facilities["headline_us"] = facilities["state"].isin(STATE_FIPS)
    facilities["has_warning"] = facilities["parser_warnings"].fillna("[]").ne("[]")
    facilities["service_codes"] = facilities["listing_id"].map(codes_by_listing).fillna("")
    facilities["code_set"] = facilities["service_codes"].map(split_codes)
    for group in HARMONIZED:
        facilities[group] = facilities["code_set"].map(
            lambda codes, selected_group=group: harmonized_values(codes, selected_group)
        )
        facilities[f"{group}_mask"] = facilities["code_set"].map(
            lambda codes, selected_group=group: harmonized_mask(codes, selected_group)
        )
    facilities["state_fips"] = facilities["state"].map(STATE_FIPS).fillna("")

    shard_columns = [
        "listing_id",
        "directory_year",
        "survey_year",
        "state",
        "state_fips",
        "census_region",
        "census_division",
        "headline_us",
        "has_warning",
        "county_fips",
        "geocode_method",
        "geocode_confidence",
        "ownership",
        "center_type",
        "setting",
        "payment",
        "service_family",
        "ownership_mask",
        "center_type_mask",
        "setting_mask",
        "payment_mask",
        "service_family_mask",
        "service_codes",
    ]
    shard = facilities.loc[:, shard_columns].copy()
    shard = shard.loc[shard["headline_us"]].drop(columns=["headline_us"])

    directory_year = int(facilities["directory_year"].iloc[0])
    survey_year = int(facilities["survey_year"].iloc[0])
    availability_output = availability_rows(
        directory_year, survey_year, asked, labels
    )
    return facilities.drop(columns=["code_set"]), shard, availability_output


def aggregate_outputs(
    facilities: pd.DataFrame,
    reviewed: dict[int, int],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    facilities["is_pnw"] = facilities["state"].isin(["WA", "OR", "ID"])
    us = facilities.loc[facilities["headline_us"]].copy()
    state_counts = (
        us.groupby(
            [
                "directory_year",
                "survey_year",
                "state",
                "census_region",
                "census_division",
            ],
            dropna=False,
        )
        .agg(
            facility_count=("listing_id", "size"),
            warning_count=("has_warning", "sum"),
        )
        .reset_index()
    )
    state_counts["state_fips"] = state_counts["state"].map(STATE_FIPS)
    state_counts["warning_share"] = (
        state_counts["warning_count"] / state_counts["facility_count"]
    )

    annual = (
        us.groupby(["directory_year", "survey_year"])
        .agg(
            facility_count=("listing_id", "size"),
            warning_count=("has_warning", "sum"),
        )
        .reset_index()
    )
    territories = (
        facilities.loc[~facilities["headline_us"]]
        .groupby(["directory_year", "survey_year"])
        .size()
        .rename("territory_count")
        .reset_index()
    )
    annual = annual.merge(
        territories, on=["directory_year", "survey_year"], how="left"
    )
    annual["territory_count"] = annual["territory_count"].fillna(0).astype(int)
    annual["warning_share"] = annual["warning_count"] / annual["facility_count"]
    annual["reviewed_listings"] = (
        annual["directory_year"].map(reviewed).fillna(0).astype(int)
    )
    annual["gold_target"] = annual["directory_year"].map(
        lambda year: 0 if int(year) >= 2022 else (100 if int(year) in PRIORITY_YEARS else 50)
    )
    annual["qa_status"] = annual.apply(
        lambda row: (
            "Official spreadsheet checks passed"
            if int(row["directory_year"]) >= 2022
            else ("Partial review" if int(row["reviewed_listings"]) > 0 else "Not reviewed")
        ),
        axis=1,
    )
    region_counts = (
        us.groupby(["directory_year", "survey_year", "census_region"])
        .size()
        .rename("facility_count")
        .reset_index()
    )
    pnw_counts = (
        us.loc[us["is_pnw"]]
        .groupby(["directory_year", "survey_year"])
        .size()
        .rename("facility_count")
        .reset_index()
    )
    pnw_counts["census_region"] = "PNW (WA, OR, ID)"
    region_counts = pd.concat([region_counts, pnw_counts], ignore_index=True)
    return annual, state_counts, region_counts


def build_characteristic_counts(
    shards: list[pd.DataFrame],
    availability: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    availability_lookup = {
        (int(row.survey_year), str(row.characteristic), str(row.value)): bool(row.asked)
        for row in availability.itertuples(index=False)
    }
    ownership_series = {
        "private_nonprofit": "Nonprofit",
        "private_forprofit": "For-profit",
        "government": "Government",
    }
    setting_series = {
        "outpatient": "Outpatient",
        "residential": "Residential",
        "hospital_inpatient": "Hospital inpatient",
    }
    government_values = [
        "local_government",
        "state_government",
        "tribal_government",
        "federal_dod",
        "federal_ihs",
        "federal_va",
    ]

    for shard in shards:
        year = int(shard["survey_year"].iloc[0])
        rows.append(
            {
                "survey_year": year,
                "metric": "total",
                "series": "total",
                "label": "All facilities",
                "facility_count": len(shard),
                "available": True,
            }
        )

        otp_bit = FILTER_BITS["service_family"]["opioid_treatment_program"]
        otp_available = availability_lookup.get(
            (year, "service_family", "opioid_treatment_program"), False
        )
        otp_count = int((shard["service_family_mask"] & otp_bit).ne(0).sum())
        for series, label, count in [
            ("otp", "OTP", otp_count),
            ("non_otp", "Non-OTP", len(shard) - otp_count),
        ]:
            rows.append(
                {
                    "survey_year": year,
                    "metric": "otp_status",
                    "series": series,
                    "label": label,
                    "facility_count": count if otp_available else pd.NA,
                    "available": otp_available,
                }
            )

        for series, label in ownership_series.items():
            if series == "government":
                bits = sum(FILTER_BITS["ownership"][value] for value in government_values)
                available = any(
                    availability_lookup.get((year, "ownership", value), False)
                    for value in government_values
                )
            else:
                bits = FILTER_BITS["ownership"][series]
                available = availability_lookup.get((year, "ownership", series), False)
            count = int((shard["ownership_mask"] & bits).ne(0).sum())
            rows.append(
                {
                    "survey_year": year,
                    "metric": "ownership",
                    "series": series,
                    "label": label,
                    "facility_count": count if available else pd.NA,
                    "available": available,
                }
            )

        for series, label in setting_series.items():
            bit = FILTER_BITS["setting"][series]
            available = availability_lookup.get((year, "setting", series), False)
            count = int((shard["setting_mask"] & bit).ne(0).sum())
            rows.append(
                {
                    "survey_year": year,
                    "metric": "setting",
                    "series": series,
                    "label": label,
                    "facility_count": count if available else pd.NA,
                    "available": available,
                }
            )
    return pd.DataFrame(rows)


def build_county_status(shards: list[pd.DataFrame]) -> pd.DataFrame:
    combined = pd.concat(shards, ignore_index=True)
    combined["county_assigned"] = combined["county_fips"].fillna("").ne("")
    combined["county_high_confidence"] = combined["geocode_confidence"].eq("high")
    combined["county_fallback"] = combined["geocode_method"].eq("zip_crosswalk")
    return (
        combined.groupby(["survey_year", "state"], dropna=False)
        .agg(
            facility_count=("listing_id", "size"),
            assigned_count=("county_assigned", "sum"),
            high_confidence_count=("county_high_confidence", "sum"),
            fallback_count=("county_fallback", "sum"),
        )
        .reset_index()
        .assign(
            unassigned_count=lambda frame: frame["facility_count"] - frame["assigned_count"],
            assigned_share=lambda frame: frame["assigned_count"] / frame["facility_count"],
            high_confidence_share=lambda frame: frame["high_confidence_count"] / frame["facility_count"],
        )
    )

def assert_shard_totals(
    shards: list[pd.DataFrame],
    annual: pd.DataFrame,
    states: pd.DataFrame,
) -> None:
    combined = pd.concat(shards, ignore_index=True)
    shard_annual = combined.groupby("survey_year").size().to_dict()
    expected_annual = annual.set_index("survey_year")["facility_count"].to_dict()
    if shard_annual != expected_annual:
        raise AssertionError("Dashboard shards do not reproduce annual totals")

    shard_states = (
        combined.groupby(["survey_year", "state"]).size().rename("count").reset_index()
    )
    expected_states = states[["survey_year", "state", "facility_count"]].rename(
        columns={"facility_count": "count"}
    )
    comparison = shard_states.merge(
        expected_states,
        on=["survey_year", "state"],
        how="outer",
        suffixes=("_shard", "_expected"),
    ).fillna(-1)
    if not comparison["count_shard"].eq(comparison["count_expected"]).all():
        raise AssertionError("Dashboard shards do not reproduce state totals")


def build(
    run_dir: Path,
    output_dir: Path,
    review_path: Path | None,
    population_cache: Path,
    geocoding_path: Path | None = None,
) -> None:
    year_dirs = [
        path
        for path in sorted((run_dir / "years").iterdir())
        if path.is_dir() and path.name.isdigit()
    ]
    if len(year_dirs) != 26:
        raise ValueError(f"Expected 26 parsed year directories, found {len(year_dirs)}")

    geocoding = (
        pd.read_csv(
            geocoding_path,
            dtype={"listing_id": str, "county_fips": str},
            low_memory=False,
        ).drop_duplicates("listing_id")
        if geocoding_path is not None and geocoding_path.exists()
        else pd.DataFrame()
    )
    facilities_frames: list[pd.DataFrame] = []
    shards: list[pd.DataFrame] = []
    availability_output: list[dict[str, object]] = []
    for year_dir in year_dirs:
        print(f"Building dashboard shard for directory year {year_dir.name}")
        facilities, shard, availability_rows_for_year = build_year_shard(year_dir, geocoding)
        facilities_frames.append(facilities)
        shards.append(shard)
        availability_output.extend(availability_rows_for_year)

    facilities = pd.concat(facilities_frames, ignore_index=True)
    reviewed = review_counts(review_path)
    annual, state_counts, region_counts = aggregate_outputs(facilities, reviewed)
    assert_shard_totals(shards, annual, state_counts)

    survey_years = set(annual["survey_year"].astype(int))
    population = read_population(population_cache, survey_years)
    population_keys = set(zip(population["survey_year"], population["state"]))
    state_keys = set(zip(state_counts["survey_year"], state_counts["state"]))
    if not state_keys.issubset(population_keys):
        raise AssertionError("Population denominators are missing facility state-years")

    output_dir.mkdir(parents=True, exist_ok=True)
    for shard in shards:
        survey_year = int(shard["survey_year"].iloc[0])
        shard.to_csv(output_dir / f"facility_dashboard_{survey_year}.csv", index=False)

    cube_columns = [
        "survey_year",
        "state",
        "state_fips",
        "census_region",
        "ownership_mask",
        "center_type_mask",
        "setting_mask",
        "payment_mask",
        "service_family_mask",
    ]
    filter_cube = (
        pd.concat(shards, ignore_index=True)
        .groupby(cube_columns, dropna=False)
        .size()
        .rename("facility_count")
        .reset_index()
    )
    if int(filter_cube["facility_count"].sum()) != int(annual["facility_count"].sum()):
        raise AssertionError("Filter cube does not reproduce annual totals")
    filter_cube.to_csv(output_dir / "facility_filter_cube.csv", index=False)

    annual.to_csv(output_dir / "annual_counts.csv", index=False)
    state_counts.to_csv(output_dir / "state_counts.csv", index=False)
    region_counts.to_csv(output_dir / "region_counts.csv", index=False)
    population.to_csv(output_dir / "state_population.csv", index=False)
    availability_frame = pd.DataFrame(availability_output)
    availability_frame.to_csv(
        output_dir / "attribute_availability.csv", index=False
    )
    build_characteristic_counts(shards, availability_frame).to_csv(
        output_dir / "national_characteristic_counts.csv", index=False
    )
    build_county_status(shards).to_csv(
        output_dir / "county_assignment_status.csv", index=False
    )
    build_crosswalk().to_csv(
        output_dir / "harmonization_crosswalk.csv", index=False
    )

    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    years = (
        annual.sort_values("survey_year")[
            [
                "directory_year",
                "survey_year",
                "qa_status",
                "reviewed_listings",
                "gold_target",
            ]
        ]
        .to_dict(orient="records")
    )
    metadata = {
        "version": "v1.1.0",
        "built_on": date.today().isoformat(),
        "run_id": run_metadata.get("run_id", run_dir.name),
        "release_status": "preliminary",
        "release_label": "Version 1.1",
        "downloads": {
            "repository": "https://github.com/studhall/samhsa-treatment-facility-directories",
            "release_base": "https://github.com/studhall/samhsa-treatment-facility-directories/releases/download/v1.1.0",
        },
        "years": years,
        "state_fips": STATE_FIPS,
        "filter_groups": {
            group: [
                {
                    "value": value,
                    "label": label,
                    "bit": FILTER_BITS[group][value],
                }
                for value, (label, _) in values.items()
            ]
            for group, values in HARMONIZED.items()
        },
        "comparability_warnings": [
            "Counts may change during year-level QA.",
            "N-SSATS and N-SUMHSS are not directly trend-comparable across the 2020/2021 survey transition.",
            "A gap means a selected characteristic was not asked or cannot be harmonized for that year.",
            "Historical listings are not a current treatment locator.",
        ],
        "population_sources": [
            {"key": key, "url": url} for key, (_, url) in POPULATION_SOURCES.items()
        ],
    }
    (output_dir / "dashboard_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    status = {
        "release_ready": False,
        "visualization_ready": True,
        "version": metadata["version"],
        "built_on": metadata["built_on"],
        "parsed_years": int(annual["directory_year"].nunique()),
        "reviewed_listings": int(annual["reviewed_listings"].sum()),
        "reviewed_1998": int(reviewed.get(1998, 0)),
        "target_1998": 100,
        "run_id": metadata["run_id"],
        "limitations": metadata["comparability_warnings"],
    }
    (output_dir / "status.json").write_text(
        json.dumps(status, indent=2), encoding="utf-8"
    )

    contract = {
        path.name: path.stat().st_size
        for path in sorted(output_dir.glob("*"))
        if path.is_file()
    }
    (output_dir / "asset_manifest.json").write_text(
        json.dumps(contract, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--geocoding", type=Path)
    parser.add_argument(
        "--population-cache",
        type=Path,
        help="Cache for downloaded Census source files.",
    )
    args = parser.parse_args()
    cache = args.population_cache or args.output_dir.parent / ".population-cache"
    build(args.run_dir, args.output_dir, args.review, cache, args.geocoding)


if __name__ == "__main__":
    main()


