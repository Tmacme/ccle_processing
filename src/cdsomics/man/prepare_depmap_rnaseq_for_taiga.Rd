% Generated by roxygen2: do not edit by hand
% Please edit documentation in R/prepare_depmap_rnaseq_for_taiga.R
\name{prepare_depmap_rnaseq_for_taiga}
\alias{prepare_depmap_rnaseq_for_taiga}
\title{Prepare DepMap RNAseq data for upload to Taiga}
\usage{
prepare_depmap_rnaseq_for_taiga(rnaseq_data, log_transform = F,
  noisy_floor = NULL, just_protein_coding = F,
  gencode_file = "~/data_files/gene_annotations/gencode.v19.annotation.gtf")
}
\arguments{
\item{rnaseq_data:}{expression matrix}

\item{log_transform:}{whether or not to log2 transform the data}

\item{noisy_floor:}{if using a noisy floor, what value should be used}

\item{just_protein_coding:}{whether or not to just subset to protein coding genes and use entrez ids}

\item{gencode_file:}{path to the gencode file with Ensembl ID and HGNC symbol pairings}
}
\description{
Assumes that RNAseq data arrive in .gct file (tab-delimited) 
with `Name`, `Description`, and CCLE cell line names as columns. The `Name` field contains
the Ensembl ID (with version number appended) for each gene, and the `Description` field 
contains the HUGO gene symbol.
}
