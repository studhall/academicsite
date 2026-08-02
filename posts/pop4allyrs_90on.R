#!/usr/bin/env Rscript

# Rebuild the legacy RDS from the checked-in Census population contract.

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
})

population_path <- file.path("posts", "moud_1.23.26", "config", "state_population.csv")
state_pop_full <- read_csv(
  population_path,
  col_types = cols(state_abbr = col_character(), year = col_integer(), pop = col_double(), .default = col_character())
)

stopifnot(
  !anyDuplicated(state_pop_full[c("state_abbr", "year")]),
  all(state_pop_full$pop > 0),
  all(c(state.abb, "DC") %in% state_pop_full$state_abbr)
)

saveRDS(
  state_pop_full %>% select(state_abbr, year, pop),
  file.path("posts", "moud_1.23.26", "state_pop_full.rds")
)
message("Wrote state_pop_full.rds from ", population_path)
