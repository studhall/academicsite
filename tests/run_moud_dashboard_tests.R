#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
})

root <- normalizePath(".", winslash = "/", mustWork = TRUE)
source_dir <- file.path(root, "posts", "moud_1.23.26")
map <- readRDS(file.path(source_dir, "site_map_df_year.rds"))
series <- readRDS(file.path(source_dir, "site_ts_df_year.rds"))
population <- read_csv(file.path(source_dir, "config", "state_population.csv"), show_col_types = FALSE)
anomalies <- read_csv(file.path(source_dir, "config", "source_anomalies.csv"), show_col_types = FALSE)
excluded <- read_csv(file.path(source_dir, "qa", "source_anomalies_excluded.csv"), show_col_types = FALSE)

headline_states <- c(state.abb, "DC")
group_key <- c("state_abbr", "year", "quarter", "moud_generic", "utilization_type")
metric_columns <- c(
  "number_of_prescriptions", "total_amount_reimbursed",
  "medicaid_amount_reimbursed", "non_medicaid_amount_reimbursed"
)

stopifnot(
  nrow(anomalies) == 10,
  nrow(excluded) == 10,
  !any(map$state_abbr %in% c("US", "XX")),
  !any(series$state_abbr == "XX"),
  all(map$year > 0 & map$year < 2025),
  all(series$year > 0 & series$year < 2025),
  all(map$pop > 0),
  all(series$pop > 0),
  !anyDuplicated(map[group_key]),
  !anyDuplicated(series[group_key])
)

rate_error <- abs(map$scripts_per100k - 1e5 * map$number_of_prescriptions / map$pop)
stopifnot(max(rate_error, na.rm = TRUE) < 1e-9)

series_states <- series %>% filter(state_abbr != "US") %>% arrange(across(all_of(group_key)))
map_sorted <- map %>% arrange(across(all_of(group_key)))
stopifnot(identical(series_states[group_key], map_sorted[group_key]))
for (metric in metric_columns) {
  stopifnot(isTRUE(all.equal(series_states[[metric]], map_sorted[[metric]], tolerance = 1e-10)))
}

expected_us <- map %>%
  filter(state_abbr %in% headline_states) %>%
  group_by(year, quarter, moud_generic, utilization_type) %>%
  summarise(across(all_of(metric_columns), sum), .groups = "drop")
actual_us <- series %>%
  filter(state_abbr == "US") %>%
  select(year, quarter, moud_generic, utilization_type, all_of(metric_columns))
us_keys <- c("year", "quarter", "moud_generic", "utilization_type")
comparison <- inner_join(expected_us, actual_us, by = us_keys, suffix = c("_expected", "_actual"))
stopifnot(nrow(comparison) == nrow(expected_us), nrow(comparison) == nrow(actual_us))
for (metric in metric_columns) {
  stopifnot(max(abs(comparison[[paste0(metric, "_expected")]] - comparison[[paste0(metric, "_actual")]])) < 1e-6)
}

expected_population <- population %>%
  filter(state_abbr %in% headline_states) %>%
  group_by(year) %>%
  summarise(pop = sum(pop), .groups = "drop")
actual_population <- series %>%
  filter(state_abbr == "US") %>%
  distinct(year, pop)
population_comparison <- inner_join(
  expected_population, actual_population, by = "year", suffix = c("_expected", "_actual")
)
stopifnot(
  nrow(actual_population) == nrow(expected_population),
  max(abs(population_comparison$pop_expected - population_comparison$pop_actual)) == 0
)

wa_sd <- map %>%
  filter(state_abbr %in% c("WA", "SD"), year %in% c(2006, 2007)) %>%
  group_by(state_abbr, year) %>%
  summarise(rx = sum(number_of_prescriptions), .groups = "drop")
stopifnot(
  wa_sd$rx[wa_sd$state_abbr == "WA" & wa_sd$year == 2006] == 10349,
  wa_sd$rx[wa_sd$state_abbr == "SD" & wa_sd$year == 2007] == 69
)

annual <- read_csv(file.path(source_dir, "qa", "annual_state_totals.csv"), show_col_types = FALSE)
stopifnot(!any(annual$previous_total >= 1000 & annual$year_over_year_ratio > 10, na.rm = TRUE))

dashboard_source <- paste(readLines(file.path(root, "data", "moud-dashboard", "index.qmd"), warn = FALSE), collapse = "\n")
stopifnot(
  grepl('const scoped = tsRows.filter((r) => r.state_abbr === stateKey)', dashboard_source, fixed = TRUE),
  !grepl('stateKey === "US" ? tsRows', dashboard_source, fixed = TRUE),
  grepl(paste0('r.state_abbr}|', '$', '{r.year}'), dashboard_source, fixed = TRUE)
)

cat("MOUD dashboard tests passed\n")
