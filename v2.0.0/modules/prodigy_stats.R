# ----- Receive arguments -----

args <- commandArgs(trailingOnly = TRUE)

if (length(args) != 2) {
  stop("Usage: Rscript prodigy_stats.R <input_csv> <output_dir>")
}

input_csv <- args[1]
output_dir <- args[2]


# ----- Create output directory -----

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)


# ----- Read CSV file -----

df <- read.csv(
  input_csv,
  sep = ";",
  check.names = FALSE,
  fileEncoding = "UTF-8-BOM"
)

# Remove possible BOM character from first column name
names(df) <- sub("^\ufeff", "", names(df))


# ----- Convert numeric columns -----

text_cols <- c("complex", "structure")
numeric_cols <- setdiff(names(df), text_cols)

for (col in numeric_cols) {
  df[[col]] <- suppressWarnings(as.numeric(df[[col]]))
}


# ----- Descriptive statistics -----

summarise_variable <- function(x, variable_name) {
  x <- x[!is.na(x)]
  
  if (length(x) == 0) {
    return(data.frame(
      variable = variable_name,
      n = 0,
      mean = NA,
      median = NA,
      sd = NA,
      min = NA,
      p05 = NA,
      p25 = NA,
      p50 = NA,
      p75 = NA,
      p95 = NA,
      max = NA
    ))
  }
  
  data.frame(
    variable = variable_name,
    n = length(x),
    mean = mean(x),
    median = median(x),
    sd = sd(x),
    min = min(x),
    p05 = as.numeric(quantile(x, 0.05)),
    p25 = as.numeric(quantile(x, 0.25)),
    p50 = as.numeric(quantile(x, 0.50)),
    p75 = as.numeric(quantile(x, 0.75)),
    p95 = as.numeric(quantile(x, 0.95)),
    max = max(x)
  )
}

summary_list <- lapply(numeric_cols, function(col) {
  summarise_variable(df[[col]], col)
})

summary_stats <- do.call(rbind, summary_list)


# ----- Save descriptive statistics -----

write.csv2(
  summary_stats,
  file.path(output_dir, "prodigy_summary_stats.csv"),
  row.names = FALSE
)


# ----- PRODIGY plots -----

plot_dir <- file.path(output_dir, "plots")
dir.create(plot_dir, recursive = TRUE, showWarnings = FALSE)


# ----- Binding affinity histogram -----

affinity <- df$predicted_binding_affinity_kcal_mol
affinity <- affinity[!is.na(affinity)]

if (length(affinity) > 0) {
  
  png(
    file.path(plot_dir, "binding_affinity_histogram.png"),
    width = 1000,
    height = 800
  )
  
  par(mar = c(6, 5, 4, 2))
  
  hist(
    affinity,
    main = "Distribution of predicted binding affinity",
    xlab = "Predicted binding affinity (kcal/mol)",
    ylab = "Number of complexes"
  )
  
  mtext(
    "Each bar represents the number of complexes within a binding affinity interval.",
    side = 1,
    line = 4,
    cex = 0.8
  )
  
  dev.off()
}


# ----- Binding affinity boxplot -----

if (length(affinity) > 0) {
  
  png(
    file.path(plot_dir, "binding_affinity_boxplot.png"),
    width = 1000,
    height = 800
  )
  
  par(mar = c(5, 5, 4, 2))
  
  boxplot(
    affinity,
    main = "Predicted binding affinity",
    ylab = "Predicted binding affinity (kcal/mol)"
  )
  
  legend(
    "topright",
    legend = c("Black line = median", "Box = interquartile range"),
    bty = "n",
    cex = 0.8
  )
  
  dev.off()
}


# ----- Dissociation constant histogram -----

kd <- df$predicted_dissociation_constant_m
kd <- kd[!is.na(kd) & kd > 0]

if (length(kd) > 0) {
  
  log_kd <- log10(kd)
  
  png(
    file.path(plot_dir, "log10_dissociation_constant_histogram.png"),
    width = 1000,
    height = 800
  )
  
  par(mar = c(6, 5, 4, 2))
  
  hist(
    log_kd,
    main = "Distribution of log10 predicted dissociation constant",
    xlab = "log10 predicted dissociation constant (M)",
    ylab = "Number of complexes"
  )
  
  mtext(
    "Each bar represents the number of complexes within a log10(Kd) interval.",
    side = 1,
    line = 4,
    cex = 0.8
  )
  
  dev.off()
}


# ----- Binding affinity by complex -----

ranking_df <- df[!is.na(df$predicted_binding_affinity_kcal_mol), ]
ranking_df <- ranking_df[order(ranking_df$predicted_binding_affinity_kcal_mol), ]

required_cols <- c(
  "complex", 
  "predicted_binding_affinity_kcal_mol", 
  "predicted_dissociation_constant_m"
  )

if (nrow(ranking_df) > 0 && all(required_cols %in% names(ranking_df))) {
  
  # ----- Binding affinity ranking and report -----
  
  ranking_output <- ranking_df[, required_cols]
  
  write.csv2(
    ranking_output,
    file.path(output_dir, "prodigy_binding_affinity_ranking.csv"),
    row.names = FALSE
  )
  
  best_complex <- ranking_output[1, ]
  worst_complex <- ranking_output[nrow(ranking_output), ]
  
  report_lines <- c(
    "PRODIGY statistics report",
    "",
    paste0("Number of complexes analysed: ", nrow(ranking_output)),
    "",
    paste0("Best complex: ", best_complex$complex),
    paste0("Best binding affinity: ", best_complex$predicted_binding_affinity_kcal_mol, " kcal/mol"),
    paste0("Best predicted dissociation constant: ", best_complex$predicted_dissociation_constant_m, " M"),
    "",
    paste0("Worst complex: ", worst_complex$complex),
    paste0("Worst binding affinity: ", worst_complex$predicted_binding_affinity_kcal_mol, " kcal/mol"),
    paste0("Worst predicted dissociation constant: ", worst_complex$predicted_dissociation_constant_m, " M"),
    "",
    "Note: More negative binding affinity values indicate stronger predicted binding affinity.",
    "Note: Lower dissociation constant values indicate stronger predicted binding affinity."
  )
  
  writeLines(
    report_lines,
    file.path(output_dir, "prodigy_stats_report.txt")
  )
  

  ranking_df$complex_label <- as.character(ranking_df$complex)
  
  # Shorten labels only for this specific test naming pattern
  ranking_df$complex_label <- sub("^ataxin3IT_23786_", "", ranking_df$complex_label)
  
  png(
    file.path(plot_dir, "binding_affinity_by_complex.png"),
    width = 1400,
    height = max(900, 250 + 80 * nrow(ranking_df))
  )
  
  par(mar = c(6, 10, 4, 2))
  
  dotchart(
    ranking_df$predicted_binding_affinity_kcal_mol,
    labels = ranking_df$complex_label,
    main = "Predicted binding affinity by complex",
    xlab = "Predicted binding affinity (kcal/mol)",
    pch = 19,
    cex = 0.9
  )
  
  mtext(
    "Each point represents one complex. More negative values indicate stronger predicted binding affinity.",
    side = 1,
    line = 4,
    cex = 0.8
  )
  
  dev.off()
}



