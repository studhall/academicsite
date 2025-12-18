## Data Cleaning for Replication of "Household Demand for Employer-Based Health Insurance"
## David Hall
## Started 12/17/25

# Setup

  ## Downloaded MEPS files HC-007, HC-012 and HC-017
    ### See link: https://meps.ahrq.gov/mepsweb/data_stats/download_data_files_results.jsp?buttonYearandDataType=Search&cboDataYear=1996&prfricon=yes&sortBy=datatypename&utm_source=chatgpt.com
    ### Note: download SAS transport format
  
  ## Libraries
    
    library(pacman)
    p_load(
      haven, # read in .ssp files (?)
      tidyverse,
      dplyr,
      here,
      fixest
    )
  
  ## Input Data
    
    ### Establish Folders 
    
    project_folder <- here("series", "BLP HH EHBI Replication")
    
    data_folder <- paste0(project_folder, "/data")
    
    ### Load Files 
    
    # hc007 <- read_xpt(paste0(data_folder, "/raw/HC007.SSP"))
    # hc012 <- read_xpt(paste0(data_folder, "/raw/HC012.SSP"))
    # hc017 <- read_xpt(paste0(data_folder, "/raw/HC017.SSP"))
    
    ### Immediate Save as .rds
    
    # saveRDS(hc007, paste0(data_folder, "/rds/hc007.rds"))
    # saveRDS(hc012, paste0(data_folder, "/rds/hc012.rds"))
    # saveRDS(hc017, paste0(data_folder, "/rds/hc017.rds"))
    
    hc007 <- readRDS(paste0(project_folder, "/data/rds/hc007.rds"))
    hc012 <- readRDS(paste0(project_folder, "/data/rds/hc012.rds"))
    hc017 <- readRDS(paste0(project_folder, "/data/rds/hc017.rds"))
    
  ## Cleaning the Data (In Accordance with Section IV)
    
    ### Clean HH file (012) based on par. 2 of pg. 10
    
      # 1+ members of DU is 19-64, employed, eligible
      hc012.1 <- hc012 %>%
        mutate(
          include = ifelse(
            AGE96X %in% c(19:64) & EMPST96 %in% c(1:3) & ELIGIBLE == 1, 1, 0
          )
        ) %>%
        group_by(
          DUID
        ) %>% 
        summarize(
          include2 = sum(include),
          .groups = "drop"
        ) %>% 
        filter(
          include2 > 0
        )
      
      # new df now has only the HH that should be included
      hc012_sub <- hc012 %>%
        semi_join(hc012.1, by = "DUID")

      
      # first determine eligibility of each person in hc007 job file
        # using EMPLINS and OFFRDINS -- either they were eligible and did or did not take :)
        # also note that union can offer, don't think this counts?
          
      hc007.1 <- hc007 %>%
        mutate(
          offer_or_take = (EMPLINS == 1 | OFFRDINS == 1)
        ) %>%
        group_by(DUPERSID) %>%
        summarize(
          offer_or_take_any = as.integer(any(offer_or_take, na.rm = TRUE)),
          .groups = "drop"
        )
      
      hc012_sub_wjobs <- hc012_sub %>%
        left_join(hc007.1, by = "DUPERSID") %>%
        mutate(
          offer_or_take_any = ifelse(is.na(offer_or_take_any), 0L, offer_or_take_any)
        )
      
      ## remove non eligible hh's
      hh_tokeep <- hc012_sub_wjobs %>%
        group_by(DUID) %>%
        summarize(
          any_elig = any(offer_or_take_any),
          .groups = "drop"
        ) %>%
        filter(any_elig)
      
      hc012_final <- hc012_sub_wjobs %>%
        semi_join(hh_tokeep, by = "DUID")
      
    ## HH Classification
      hh_sources <- hc012_final %>%
        mutate(
          source_worker = as.integer(
            AGE96X %in% 19:64 &
              EMPST96 %in% 1:3 &
              offer_or_take_any == 1
          )
        ) %>%
        group_by(DUID) %>%
        summarize(
          n_sources = sum(source_worker, na.rm = TRUE),
          .groups = "drop"
        ) %>%
        filter(n_sources %in% c(1, 2)) %>% 
        mutate(
          one_source = as.integer(n_sources == 1),
          two_source = as.integer(n_sources == 2)
        )
      
      hc017_sub <- hc017 %>%
        semi_join(
          hc012_final %>%
            filter(
              AGE96X %in% 19:64,
              EMPST96 %in% 1:3,
              offer_or_take_any == 1
            ) %>%
            select(DUPERSID),
          by = "DUPERSID"
        )
      
      hc017_sub <- hc017_sub %>%
        left_join(
          hc012_final %>% select(DUPERSID),
          by = "DUPERSID"
        )
      
      hh_plan_counts <- hc017_sub %>%
        distinct(DUID, EPRSIDX) %>%   # deduplicate plans within household
        count(DUID, name = "n_plans")
      
      hh_plan_counts <- hh_plan_counts %>%
        left_join(hh_sources %>% select(DUID, one_source, two_source), by = "DUID")
      
      table(hh_plan_counts$n_plans, hh_plan_counts$one_source)
      
      