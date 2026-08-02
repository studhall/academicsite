#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
})

input_dir <- "posts/moud_1.23.26"
out_dir <- "data/moud-dashboard/data"
download_dir <- "data/moud-dashboard/downloads"
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(download_dir, recursive = TRUE, showWarnings = FALSE)

read_tbl <- function(name) {
  readRDS(file.path(input_dir, paste0(name, ".rds"))) %>%
    mutate(across(where(is.factor), as.character))
}

map_df <- read_tbl("site_map_df_year")
ts_df <- read_tbl("site_ts_df_year")
ndc_df <- read_tbl("site_ndc_df_year") %>% mutate(ndc = as.character(ndc))

write_csv(map_df, file.path(out_dir, "site_map_df_year.csv"))
write_csv(ts_df, file.path(out_dir, "site_ts_df_year.csv"))
write_csv(ndc_df, file.path(out_dir, "site_ndc_df_year.csv"))
file.copy(file.path(input_dir, "config", "source_anomalies.csv"), out_dir, overwrite = TRUE)
file.copy(file.path(input_dir, "config", "state_population.csv"), out_dir, overwrite = TRUE)

write_csv(ts_df, file.path(download_dir, "moud_state_quarter_1991_2024.csv.gz"))
write_csv(ndc_df, file.path(download_dir, "moud_ndc_quarter_1991_2024.csv.gz"))

for (selected_year in sort(unique(ts_df$year))) {
  write_csv(
    filter(ts_df, year == selected_year),
    file.path(download_dir, paste0("moud_state_quarter_", selected_year, ".csv.gz"))
  )
  write_csv(
    filter(ndc_df, year == selected_year),
    file.path(download_dir, paste0("moud_ndc_quarter_", selected_year, ".csv.gz"))
  )
}

cat("Exported corrected dashboard and download files\n")
cat("Rows:", "map=", nrow(map_df), "ts=", nrow(ts_df), "ndc=", nrow(ndc_df), "\n")
