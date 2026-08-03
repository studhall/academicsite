# Treatment Facility Dashboard QA Audit

Audit date: 2026-07-28

## Current assessment

The browser assets reproduce all national and state directory-listing totals, and the filter logic passes the automated consistency suite. The dashboard is appropriate for transparent exploratory use while year-level manual review continues. It is not yet a fully validated historical release.

## Resolved in this audit

- Replaced code-only harmonization with year-, category-, and label-aware rules.
- Prevented 1998 PV (Primary prevention) from being classified as private ownership.
- Prevented 2025 MI (Motivational interviewing) from being classified as military insurance.
- Prevented 2001 OA (Other assistance under detoxification) from being classified as payment assistance.
- Added 2025 aliases for TRICARE, CASH, and DoD.
- Added the general federal ownership code FED, present from 2022 onward.
- Suppressed the single 2015-directory OTP token; reliable directory OTP coding begins with the 2016 directory.
- Suppressed isolated pre-2004 buprenorphine tokens as OCR noise.
- Added a 95% directory-ownership coverage gate before ownership filters or counts are available.
- Rebuilt the public-use survey ownership series from raw files, including the previously omitted 2016 file and the correct 2021-2023 substance-use focus restriction.
- Separated public-use survey ownership shares from directory-coded address filters.
- Added explicit trend gaps for missing survey years and the 2020/2021 survey redesign.
- Added year-level QA assets and semantic regression tests.

## Cross-source ownership check

For overlapping survey years 2018-2023, directory and public-use survey ownership shares are close but not identical because the products have different inclusion rules. Across those years, the largest absolute difference is about 2.1 percentage points for government facilities and 1.8 percentage points for for-profit facilities. The PUF series is therefore shown as a separate national trend and is not merged into directory records.

## Open release risks

- Gold-sample review is incomplete for every PDF year except a partial 1998 review.
- Directory year 2004 has 9,907 U.S. listings, 11.4% above the 9,047-listing legacy parser fixture. The legacy count is not an independent benchmark, but the difference needs manual review.
- Parser warning rates exceed 5% for most PDF years.
- County assignment is below the 90% high-confidence gate. From survey year 2000 onward, current county geography is based on ZIP-to-county crosswalk fallback rather than street geocoding.
- N-SSATS and N-SUMHSS have different designs and should not be treated as one continuous statistical series.
- Directory listings and public-use survey facilities have different inclusion and public-listing rules.
- Facility linkage has not been validated, so rows are listing-years rather than confirmed continuing organizations.

## Automated checks

The dashboard suite verifies 26 year shards, national and state totals, annual populations, per-capita calculations, county accounting, filter-bit integrity, missing/not-asked behavior, ownership-series normalization, semantic code collisions, 2025 code aliases, and OTP year guards.
