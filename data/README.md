# Input data (not redistributed)

Both sources are U.S. federal government publications and are free to download. Place the files in this directory.

## 1. SBA 7(a) FOIA loan-level files

Source: U.S. Small Business Administration, "7(a) & 504 FOIA" dataset (data.sba.gov). Download:

- `FOIA_7a_FY2010_FY2019_asof_<YYMMDD>.csv`
- `FOIA_7a_FY2020_Present_asof_<YYMMDD>.csv`
- the accompanying data dictionary (`7a_504_foia_data_dictionary.xlsx`)

The paper uses the files as of 30 June 2026. SBA refreshes them quarterly, so later vintages will shift the numbers
slightly; the qualitative results do not depend on the vintage.

## 2. Census NAICS concordance

Source: U.S. Census Bureau, NAICS concordances page. Download **"2022 to 2017 NAICS"** (XLSX) and save it as
`2022_to_2017_NAICS.xlsx`.

## File paths

`src/walkbench/sba.py` reads from this `data/` directory by default. To keep the files elsewhere, set the
`WB_DATA_DIR` environment variable to that directory. The code expects the file names of the 30 June 2026 vintage
(`..._asof_260630.csv`); rename a later vintage to match, or edit `FILES` in `sba.py`.

## Fields used

`NaicsCode`, `ApprovalDate`, `ApprovalFY`, `GrossApproval`, `TermInMonths`, `LoanStatus`, `ChargeOffDate`,
`GrossChargeOffAmount`, `PaidInFullDate`, `FirstDisbursementDate`, `RevolverStatus`, `ProcessingMethod`.
Borrower names and addresses are present in the source files but are never read by this code.
