from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

import pandas as pd


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = DASHBOARD_DIR / "data"
BUILDER_PATH = DASHBOARD_DIR / "scripts" / "build_preliminary_data.py"

SPEC = importlib.util.spec_from_file_location("dashboard_builder", BUILDER_PATH)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class DashboardDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.annual = pd.read_csv(DATA_DIR / "annual_counts.csv")
        cls.states = pd.read_csv(DATA_DIR / "state_counts.csv", dtype={"state_fips": str})
        cls.population = pd.read_csv(
            DATA_DIR / "state_population.csv", dtype={"state_fips": str}
        )
        cls.availability = pd.read_csv(DATA_DIR / "attribute_availability.csv")
        cls.cube = pd.read_csv(DATA_DIR / "facility_filter_cube.csv")
        cls.characteristics = pd.read_csv(DATA_DIR / "national_characteristic_counts.csv")
        cls.county_status = pd.read_csv(DATA_DIR / "county_assignment_status.csv")
        cls.metadata = json.loads(
            (DATA_DIR / "dashboard_metadata.json").read_text(encoding="utf-8")
        )

    def test_all_26_years_have_shards(self) -> None:
        years = {row["survey_year"] for row in self.metadata["years"]}
        shards = {
            int(path.stem.removeprefix("facility_dashboard_"))
            for path in DATA_DIR.glob("facility_dashboard_*.csv")
        }
        self.assertEqual(len(years), 26)
        self.assertEqual(max(years), 2024)
        self.assertEqual(shards, years)

    def test_shards_reproduce_annual_and_state_totals(self) -> None:
        annual_actual: dict[int, int] = {}
        state_frames = []
        for path in DATA_DIR.glob("facility_dashboard_*.csv"):
            shard = pd.read_csv(path, usecols=["survey_year", "state"])
            year = int(shard["survey_year"].iloc[0])
            annual_actual[year] = len(shard)
            state_frames.append(shard)

        annual_expected = self.annual.set_index("survey_year")[
            "facility_count"
        ].to_dict()
        self.assertEqual(annual_actual, annual_expected)

        states_actual = (
            pd.concat(state_frames)
            .groupby(["survey_year", "state"])
            .size()
            .sort_index()
        )
        states_expected = self.states.set_index(["survey_year", "state"])[
            "facility_count"
        ].sort_index()
        pd.testing.assert_series_equal(
            states_actual,
            states_expected,
            check_names=False,
            check_dtype=False,
        )

    def test_filter_cube_reproduces_annual_totals(self) -> None:
        cube_totals = self.cube.groupby("survey_year")["facility_count"].sum()
        expected = self.annual.set_index("survey_year")["facility_count"]
        pd.testing.assert_series_equal(
            cube_totals.sort_index(),
            expected.sort_index(),
            check_names=False,
            check_dtype=False,
        )

    def test_population_has_51_geographies_for_every_year(self) -> None:
        counts = self.population.groupby("survey_year")["state_fips"].nunique()
        self.assertTrue(counts.eq(51).all())
        self.assertEqual(set(counts.index), set(self.annual["survey_year"]))
        self.assertTrue(self.population["population"].gt(0).all())

    def test_per_capita_uses_annual_state_population(self) -> None:
        count = self.states.loc[
            self.states["survey_year"].eq(1998) & self.states["state"].eq("AL"),
            "facility_count",
        ].iloc[0]
        population = self.population.loc[
            self.population["survey_year"].eq(1998)
            & self.population["state"].eq("AL"),
            "population",
        ].iloc[0]
        expected = count / population * 100_000
        self.assertGreater(expected, 0)
        self.assertLess(expected, 100)

    def test_preview_characteristics_reproduce_annual_totals(self) -> None:
        totals = self.characteristics.loc[
            self.characteristics["metric"].eq("total")
            & self.characteristics["series"].eq("total")
        ].set_index("survey_year")["facility_count"]
        expected = self.annual.set_index("survey_year")["facility_count"]
        pd.testing.assert_series_equal(
            totals.sort_index(),
            expected.sort_index(),
            check_names=False,
            check_dtype=False,
        )

    def test_county_status_accounts_for_every_state_listing(self) -> None:
        self.assertTrue(
            (
                self.county_status["assigned_count"]
                + self.county_status["unassigned_count"]
                == self.county_status["facility_count"]
            ).all()
        )
        actual = self.county_status.set_index(["survey_year", "state"])["facility_count"]
        expected = self.states.set_index(["survey_year", "state"])["facility_count"]
        pd.testing.assert_series_equal(
            actual.sort_index(),
            expected.sort_index(),
            check_names=False,
            check_dtype=False,
        )

    def test_shards_include_preliminary_county_fields(self) -> None:
        expected = {"county_fips", "geocode_method", "geocode_confidence"}
        for path in DATA_DIR.glob("facility_dashboard_*.csv"):
            columns = set(pd.read_csv(path, nrows=0).columns)
            self.assertTrue(expected.issubset(columns), path.name)

    def test_filter_bits_are_nonoverlapping(self) -> None:
        for group, entries in self.metadata["filter_groups"].items():
            bits = [entry["bit"] for entry in entries]
            self.assertEqual(len(bits), len(set(bits)), group)
            self.assertTrue(all(bit > 0 and bit & (bit - 1) == 0 for bit in bits))

    def test_not_asked_is_explicit(self) -> None:
        ownership = self.availability.loc[
            self.availability["characteristic"].eq("ownership")
        ]
        early_nonprofit = ownership.loc[
            ownership["survey_year"].eq(1998)
            & ownership["value"].eq("private_nonprofit"),
            "asked",
        ].iloc[0]
        late_nonprofit = ownership.loc[
            ownership["survey_year"].eq(2020)
            & ownership["value"].eq("private_nonprofit"),
            "asked",
        ].iloc[0]
        self.assertFalse(bool(early_nonprofit))
        self.assertTrue(bool(late_nonprofit))

    def test_harmonized_service_all_and_any_logic(self) -> None:
        bits = BUILDER.FILTER_BITS["service_family"]
        row_mask = bits["methadone"] | bits["outpatient_treatment"]
        selected = bits["methadone"] | bits["telehealth"]
        self.assertNotEqual(row_mask & selected, 0)
        self.assertNotEqual(row_mask & selected, selected)


    def test_semantic_harmonization_rejects_code_collisions(self) -> None:
        ownership_entries = {("PV", "Unclassified", "Primary prevention")}
        self.assertEqual(
            BUILDER.harmonized_mask(ownership_entries, "ownership", 1998),
            0,
        )

        payment_entries = {("MI", "Treatment Approaches", "Motivational interviewing")}
        self.assertEqual(
            BUILDER.harmonized_mask(payment_entries, "payment", 2025),
            0,
        )

        assistance_entries = {("OA", "Detoxification", "Other assistance")}
        self.assertEqual(
            BUILDER.harmonized_mask(assistance_entries, "payment", 2001),
            0,
        )

    def test_early_buprenorphine_ocr_token_is_suppressed(self) -> None:
        entries = {("BU", "Medication Services", "Buprenorphine used in treatment")}
        bit = BUILDER.FILTER_BITS["service_family"]["buprenorphine"]
        self.assertEqual(
            BUILDER.harmonized_mask(entries, "service_family", 1998) & bit,
            0,
        )
        self.assertNotEqual(
            BUILDER.harmonized_mask(entries, "service_family", 2004) & bit,
            0,
        )

    def test_incomplete_directory_ownership_is_not_available(self) -> None:
        rows = BUILDER.availability_rows(
            directory_year=2016,
            survey_year=2015,
            asked={"PVT", "LCCG"},
            asked_entries={
                ("PVT", "Unclassified", ""),
                ("LCCG", "Facility Operation", "Local government"),
            },
            labels={},
            ownership_coverage=0.775,
        )
        ownership = [row for row in rows if row["characteristic"] == "ownership"]
        self.assertTrue(ownership)
        self.assertTrue(all(not row["asked"] for row in ownership))

    def test_public_use_ownership_series_is_complete_and_normalized(self) -> None:
        trend = pd.read_csv(DATA_DIR / "ownership_puf_trends.csv")
        self.assertIn(2016, set(trend["survey_year"]))
        shares = trend.groupby("survey_year")["ownership_share"].sum()
        self.assertTrue((shares.sub(1).abs() < 1e-10).all())
        self.assertEqual(
            set(trend["ownership"]),
            {"For-profit", "Nonprofit", "Government"},
        )

    def test_generated_assets_reject_known_code_collisions(self) -> None:
        early = pd.read_csv(DATA_DIR / "facility_dashboard_1998.csv")
        self.assertTrue(early["ownership_mask"].eq(0).all())

        latest = pd.read_csv(DATA_DIR / "facility_dashboard_2024.csv")
        military_bit = BUILDER.FILTER_BITS["payment"]["military_insurance"]
        expected_military = latest["service_codes"].fillna("").str.contains(
            r"(?:^|\\|)TRICARE(?:\\||$)", regex=True
        )
        actual_military = (latest["payment_mask"] & military_bit).ne(0)
        self.assertGreater(int(expected_military.sum()), 0)
        pd.testing.assert_series_equal(
            actual_military,
            expected_military,
            check_names=False,
        )

        self_pay_bit = BUILDER.FILTER_BITS["payment"]["self_pay"]
        expected_self_pay = latest["service_codes"].fillna("").str.contains(
            r"(?:^|\\|)CASH(?:\\||$)", regex=True
        )
        actual_self_pay = (latest["payment_mask"] & self_pay_bit).ne(0)
        pd.testing.assert_series_equal(
            actual_self_pay,
            expected_self_pay,
            check_names=False,
        )

        federal_bit = BUILDER.FILTER_BITS["ownership"]["federal_other"]
        expected_federal = latest["service_codes"].fillna("").str.contains(
            r"(?:^|\\|)FED(?:\\||$)", regex=True
        )
        actual_federal = (latest["ownership_mask"] & federal_bit).ne(0)
        pd.testing.assert_series_equal(
            actual_federal,
            expected_federal,
            check_names=False,
        )

    def test_otp_is_suppressed_before_reliable_directory_coding(self) -> None:
        entries = {("OTP", "Medication Services", "Opioid treatment program")}
        bit = BUILDER.FILTER_BITS["service_family"]["opioid_treatment_program"]
        self.assertEqual(
            BUILDER.harmonized_mask(entries, "service_family", 2015) & bit,
            0,
        )
        self.assertNotEqual(
            BUILDER.harmonized_mask(entries, "service_family", 2016) & bit,
            0,
        )
if __name__ == "__main__":
    unittest.main()




