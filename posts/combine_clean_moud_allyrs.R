#!/usr/bin/env Rscript

# Build MOUD dashboard extracts from annual CMS State Drug Utilization files.

suppressPackageStartupMessages({
  library(bit64)
  library(dplyr)
  library(janitor)
  library(readr)
  library(stringr)
})

main_folder <- file.path("posts", "moud_1.23.26")
moud_dir <- file.path(main_folder, "moud_year")
config_dir <- file.path(main_folder, "config")
qa_dir <- file.path(main_folder, "qa")
dir.create(qa_dir, recursive = TRUE, showWarnings = FALSE)

state_abbreviations <- c(state.abb, "DC")
headline_states <- c(state.abb, "DC")
metric_columns <- c(
  "number_of_prescriptions", "total_amount_reimbursed",
  "medicaid_amount_reimbursed", "non_medicaid_amount_reimbursed"
)

normalize_ndc <- function(data) {
  clean_segment <- function(x, width) {
    x <- str_replace_all(as.character(x), "[^0-9]", "")
    if_else(x == "", NA_character_, str_pad(x, width, pad = "0"))
  }
  from_segments <- paste0(
    clean_segment(data$labeler_code, 5), clean_segment(data$product_code, 4),
    clean_segment(data$package_size, 2)
  )
  from_segments[str_detect(from_segments, "NA")] <- NA_character_
  fallback <- str_replace_all(as.character(data$ndc), "[^0-9]", "")
  fallback <- if_else(fallback == "", NA_character_, str_pad(fallback, 11, pad = "0"))
  coalesce(from_segments, fallback)
}

read_moud_file <- function(path) {
  data <- readRDS(path)
  data[] <- lapply(data, function(column) {
    if (inherits(column, "integer64")) bit64::as.character.integer64(column) else column
  })
  data <- clean_names(as.data.frame(data))
  required <- c(
    "state", "year", "quarter", "utilization_type", "suppression_used",
    "product_name", "ndc", "labeler_code", "product_code", "package_size",
    "units_reimbursed", metric_columns
  )
  for (column in setdiff(required, names(data))) data[[column]] <- NA
  data %>%
    mutate(
      across(all_of(c("year", "quarter", "units_reimbursed", metric_columns)), as.numeric),
      across(all_of(c("ndc", "labeler_code", "product_code", "package_size")), as.character),
      state = as.character(state),
      utilization_type = as.character(utilization_type),
      product_name = as.character(product_name),
      suppression_used = as.logical(suppression_used),
      ndc = normalize_ndc(pick(everything()))
    ) %>%
    select(all_of(required), ndc)
}

normalize_product <- function(x) {
  x %>% str_to_lower() %>% str_replace_all("\\(.*?\\)", "") %>%
    str_replace_all("[^a-z0-9]+", " ") %>% str_squish()
}

classify_moud <- function(product_norm) {
  case_when(
    str_detect(product_norm, "bupren|bup nal|suboxone|subutex|sublocade|zubsolv|bunavail|probuphine|butrans|belbuca|brixadi") ~ "Buprenorphine",
    str_detect(product_norm, "methadon|methadose|diskets") ~ "Methadone",
    str_detect(product_norm, "naltrexone|vivitrol") & !str_detect(product_norm, "relistor|contrave") ~ "Naltrexone",
    TRUE ~ NA_character_
  )
}

rds_files <- list.files(moud_dir, pattern = "\\.rds$", full.names = TRUE)
if (!length(rds_files)) stop("No annual MOUD files found in ", moud_dir)

moud_panel <- bind_rows(lapply(rds_files, read_moud_file)) %>%
  mutate(product_norm = normalize_product(product_name), moud_generic = classify_moud(product_norm)) %>%
  filter(!is.na(moud_generic), !is.na(year), year > 0, year < 2025)

write_csv(moud_panel %>% filter(state == "XX"), file.path(qa_dir, "cms_national_rows_excluded.csv"))
moud_panel <- moud_panel %>% filter(state %in% state_abbreviations)

anomalies <- read_csv(
  file.path(config_dir, "source_anomalies.csv"),
  col_types = cols(.default = col_character(), year = col_integer(), quarter = col_integer())
)
moud_panel <- moud_panel %>% left_join(
  anomalies %>% select(state, year, quarter, ndc, anomaly_id, action, reason),
  by = c("state", "year", "quarter", "ndc")
)
excluded_anomalies <- moud_panel %>% filter(action == "exclude")
if (nrow(excluded_anomalies) != sum(anomalies$action == "exclude")) {
  stop("Not every configured CMS source anomaly matched exactly one source row")
}
write_csv(excluded_anomalies, file.path(qa_dir, "source_anomalies_excluded.csv"))
moud_panel <- moud_panel %>% filter(is.na(action) | action != "exclude")

population <- read_csv(
  file.path(config_dir, "state_population.csv"),
  col_types = cols(state_abbr = col_character(), year = col_integer(), pop = col_double(), .default = col_character())
)
if (anyDuplicated(population[c("state_abbr", "year")])) stop("Population keys are not unique")
moud_panel <- moud_panel %>% mutate(state_abbr = state) %>%
  left_join(population %>% select(state_abbr, year, pop), by = c("state_abbr", "year"))
if (any(is.na(moud_panel$pop))) stop("Population is missing for one or more state-year rows")

aggregate_metrics <- function(data, groups) {
  data %>% group_by(across(all_of(groups))) %>% summarise(
    across(all_of(metric_columns), ~ sum(.x, na.rm = TRUE)),
    pop = first(pop),
    suppressed_cells = sum(suppression_used %in% TRUE | is.na(number_of_prescriptions)),
    reported_cells = sum(!is.na(number_of_prescriptions)), .groups = "drop"
  ) %>% mutate(
    scripts_per100k = 1e5 * number_of_prescriptions / pop,
    total_reimb_per100k = 1e5 * total_amount_reimbursed / pop,
    medicaid_reimb_per100k = 1e5 * medicaid_amount_reimbursed / pop,
    nonmedicaid_reimb_per100k = 1e5 * non_medicaid_amount_reimbursed / pop
  )
}

state_groups <- c("state_abbr", "year", "quarter", "moud_generic", "utilization_type")
map_df_year <- aggregate_metrics(moud_panel, state_groups)
us_population <- population %>% filter(state_abbr %in% headline_states) %>%
  group_by(year) %>% summarise(pop = sum(pop), .groups = "drop")

map_df_national_year <- moud_panel %>% filter(state_abbr %in% headline_states) %>%
  group_by(year, quarter, moud_generic, utilization_type) %>% summarise(
    across(all_of(metric_columns), ~ sum(.x, na.rm = TRUE)),
    suppressed_cells = sum(suppression_used %in% TRUE | is.na(number_of_prescriptions)),
    reported_cells = sum(!is.na(number_of_prescriptions)), .groups = "drop"
  ) %>% left_join(us_population, by = "year") %>% mutate(
    state_abbr = "US",
    scripts_per100k = 1e5 * number_of_prescriptions / pop,
    total_reimb_per100k = 1e5 * total_amount_reimbursed / pop,
    medicaid_reimb_per100k = 1e5 * medicaid_amount_reimbursed / pop,
    nonmedicaid_reimb_per100k = 1e5 * non_medicaid_amount_reimbursed / pop
  )

ts_df_year <- bind_rows(map_df_year, map_df_national_year) %>%
  arrange(state_abbr, year, quarter, moud_generic, utilization_type)

ndc_df_year <- moud_panel %>%
  group_by(state_abbr, year, quarter, utilization_type, moud_generic, ndc) %>% summarise(
    scripts = sum(number_of_prescriptions, na.rm = TRUE),
    total_reimb = sum(total_amount_reimbursed, na.rm = TRUE),
    medicaid_reimb = sum(medicaid_amount_reimbursed, na.rm = TRUE),
    nonmedicaid_reimb = sum(non_medicaid_amount_reimbursed, na.rm = TRUE),
    suppressed_cells = sum(suppression_used %in% TRUE | is.na(number_of_prescriptions)), .groups = "drop"
  )
ndc_df_us_year <- ndc_df_year %>% filter(state_abbr %in% headline_states) %>%
  group_by(year, quarter, utilization_type, moud_generic, ndc) %>%
  summarise(across(c(scripts, total_reimb, medicaid_reimb, nonmedicaid_reimb, suppressed_cells), sum), .groups = "drop") %>%
  mutate(state_abbr = "US")
ndc_df_year <- bind_rows(ndc_df_year, ndc_df_us_year) %>%
  arrange(state_abbr, year, quarter, moud_generic, utilization_type, ndc)

annual_state_totals <- map_df_year %>% group_by(state_abbr, year) %>%
  summarise(number_of_prescriptions = sum(number_of_prescriptions), .groups = "drop") %>%
  group_by(state_abbr) %>% arrange(year, .by_group = TRUE) %>%
  mutate(previous_total = lag(number_of_prescriptions), year_over_year_ratio = number_of_prescriptions / previous_total) %>%
  ungroup()
write_csv(annual_state_totals, file.path(qa_dir, "annual_state_totals.csv"))

saveRDS(map_df_year, file.path(main_folder, "site_map_df_year.rds"))
saveRDS(ts_df_year, file.path(main_folder, "site_ts_df_year.rds"))
saveRDS(ndc_df_year, file.path(main_folder, "site_ndc_df_year.rds"))
message("MOUD dashboard build complete: ", nrow(map_df_year), " state rows; ", nrow(ts_df_year), " state/US rows")
