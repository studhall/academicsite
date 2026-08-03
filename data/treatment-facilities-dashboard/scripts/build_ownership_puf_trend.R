args <- commandArgs(trailingOnly = TRUE)
raw_dir <- if (length(args) >= 1) args[[1]] else file.path(
  "series", "TC_Ownership", "data", "raw"
)
output_path <- if (length(args) >= 2) args[[2]] else file.path(
  "data", "treatment-facilities-dashboard", "data", "ownership_puf_trends.csv"
)

states <- c(state.abb, "DC")
state_names <- setNames(state.abb, toupper(state.name))
state_names[["DISTRICT OF COLUMBIA"]] <- "DC"

clean_state <- function(data) {
  if ("LOCATIONSTATE" %in% names(data)) {
    value <- trimws(as.character(data$LOCATIONSTATE))
  } else if ("STATE" %in% names(data)) {
    value <- trimws(as.character(data$STATE))
  } else if ("STFIPS" %in% names(data)) {
    value <- trimws(sub("^\\([0-9]+\\)\\s*", "", as.character(data$STFIPS)))
  } else {
    return(rep(NA_character_, nrow(data)))
  }
  upper <- toupper(value)
  direct <- ifelse(upper %in% states, upper, NA_character_)
  from_name <- unname(state_names[upper])
  ifelse(is.na(direct), from_name, direct)
}

clean_owner <- function(value) {
  text <- tolower(trimws(as.character(value)))
  numeric_code <- suppressWarnings(as.integer(text))
  result <- rep(NA_character_, length(text))
  result[numeric_code == 1 | grepl("for-profit", text)] <- "For-profit"
  result[numeric_code == 2 | grepl("non-profit", text)] <- "Nonprofit"
  government <- numeric_code %in% 3:6 |
    grepl("government|tribal govt|state govt|federal govt|community govt", text)
  result[government] <- "Government"
  result
}

clean_year <- function(value) {
  text <- as.character(value)
  suppressWarnings(as.integer(sub(".*?([12][0-9]{3}).*", "\\1", text)))
}

focus_in_scope <- function(value) {
  text <- trimws(as.character(value))
  numeric_code <- suppressWarnings(as.integer(text))
  numeric_code %in% c(1L, 3L) | grepl("^\\((1|3)\\)", text)
}

read_first_object <- function(path) {
  environment <- new.env(parent = emptyenv())
  objects <- load(path, envir = environment)
  environment[[objects[[1]]]]
}

files <- list.files(
  raw_dir,
  pattern = "^(nssats|nsumhss)_.*\\.(rda|Rda|RData|rdata)$",
  full.names = TRUE
)
records <- list()

for (path in sort(files)) {
  data <- read_first_object(path)
  filename <- basename(path)

  if (grepl("1997_2011", filename)) {
    year <- clean_year(data$YEAR)
    keep <- focus_in_scope(data$FOCUS)
    source <- rep("N-SSATS public-use facility survey", nrow(data))
    segment <- rep("N-SSATS", nrow(data))
  } else {
    year_value <- as.integer(sub(".*?([0-9]{4}).*", "\\1", filename))
    year <- rep(year_value, nrow(data))
    keep <- rep(TRUE, nrow(data))
    if (grepl("^nsumhss_", filename)) {
      keep <- focus_in_scope(data$FOCUS)
    }
    source_label <- if (grepl("^nsumhss_", filename)) {
      "N-SUMHSS public-use facility survey"
    } else {
      "N-SSATS public-use facility survey"
    }
    source <- rep(source_label, nrow(data))
    segment <- rep(ifelse(year_value >= 2021, "N-SUMHSS", "N-SSATS"), nrow(data))
  }

  owner_field <- if ("OWNERSHP" %in% names(data)) {
    data$OWNERSHP
  } else if ("OWNERSHIP" %in% names(data)) {
    data$OWNERSHIP
  } else {
    rep(NA, nrow(data))
  }

  frame <- data.frame(
    survey_year = year,
    state = clean_state(data),
    ownership = clean_owner(owner_field),
    source = source,
    comparability_segment = segment,
    stringsAsFactors = FALSE
  )
  frame <- frame[
    keep & frame$survey_year >= 1998 & frame$state %in% states,
    ,
    drop = FALSE
  ]
  records[[length(records) + 1L]] <- frame
}

combined <- do.call(rbind, records)
year_total <- aggregate(
  list(total_facilities = combined$survey_year),
  list(survey_year = combined$survey_year),
  length
)
classified <- combined[!is.na(combined$ownership), , drop = FALSE]
counts <- aggregate(
  list(facility_count = classified$survey_year),
  list(
    survey_year = classified$survey_year,
    ownership = classified$ownership,
    source = classified$source,
    comparability_segment = classified$comparability_segment
  ),
  length
)
classified_total <- aggregate(
  list(classified_facilities = classified$survey_year),
  list(survey_year = classified$survey_year),
  length
)
output <- merge(counts, classified_total, by = "survey_year", all.x = TRUE)
output <- merge(output, year_total, by = "survey_year", all.x = TRUE)
output$missing_ownership <- output$total_facilities - output$classified_facilities
output$ownership_share <- output$facility_count / output$classified_facilities
output$universe <- paste(
  "Public-use survey facilities in the 50 states and DC;",
  "N-SUMHSS years retain substance-use or combined-focus facilities"
)
output <- output[
  order(output$survey_year, match(
    output$ownership,
    c("For-profit", "Nonprofit", "Government")
  )),
  c(
    "survey_year", "ownership", "facility_count", "ownership_share",
    "classified_facilities", "missing_ownership", "source",
    "comparability_segment", "universe"
  )
]

if (any(abs(aggregate(
  ownership_share ~ survey_year,
  data = output,
  sum
)$ownership_share - 1) > 1e-10)) {
  stop("Ownership shares do not sum to one")
}
if (!2016 %in% output$survey_year) {
  stop("The ownership trend is missing 2016")
}

dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
write.csv(output, output_path, row.names = FALSE, na = "")
