# Approved report specification

This document is the implementation contract extracted from the six approved
historical PDF reports. The historical files are intentionally not stored in
Git because they contain company information.

## Source priority

1. Active Backup rows and audit fields: latest NAS-generated
   `/ABB_Backup/ABB_Report/abb_daily_result_latest.csv`.
2. Active Backup Web API: supplemental task metadata, cross-checks and evidence.
3. Yard: DSM Drive ShareSync APIs.
4. HCI: verified Sangfor browser capture.

When sources disagree, preserve the CSV row and display a warning. Never alter
the authoritative CSV value to make the sources agree.

## Page sequence

### 1. Active Backup overview

Top: the File Server task list, matching the legacy report presentation.

Bottom: the result table with exactly these columns and this order:

1. `No.`
2. `Group`
3. `Backup Task`
4. `Status`
5. `Source`
6. `Start`
7. `End`
8. `Duration`
9. `Size`
10. `File Count`
11. `Warning/Error`
12. `Unchanged`
13. `Same Size`
14. `Audit Same Size`
15. `Audit Status`

`Start` and `End` come directly from the CSV and are displayed as the full
`DD/MM/YYYY HH:MM:SS` datetime. Preserve row ordering from the CSV. Highlight
rows requiring attention without changing their values.

### 2. Conditional evidence pages

Create exactly one detail/evidence page for every Active Backup row where:

- `Audit Status` is `Check`, or
- `Status` is not successful.

If five rows qualify, create five pages. If none qualify, create no evidence
page. These pages immediately follow the Active Backup overview.

### 3. Yard / Drive ShareSync

Show the folder list in the same order returned by the NAS (the order visible
in the left-hand list). Beside it, show the same number of newest ShareSync
events so the folder and activity sections can be compared without jumping
between pages. Do not present an empty successful API response as a connection
failure; state the NAS status accurately.

### 4. Sangfor HCI

The HCI screenshot is the final report page. Before capture, sort the visible
`Latest Backup` column newest-to-oldest and verify that order. Do not attach a
capture when the ordering cannot be verified.

## Removed content

Do not add a standalone "Data Integrity and Audit Details" summary page. It was
removed because it duplicates the Active Backup overview. The per-task evidence
pages above are the only audit detail pages.

## Daily history summary

The web report history includes copyable daily text containing the report date,
File Backup result, Yard status, HCI status, and notes for tasks requiring
attention. Wording must describe measured status and must not claim a check was
performed when it was not.

## Acceptance checks

- Page order follows this document.
- Result row count and order match the authoritative CSV.
- All 15 columns are present in the required order.
- Every `Start` and `End` matches the CSV exactly after display formatting.
- `Same Size`, `Audit Same Size`, and `Audit Status` match the CSV exactly.
- Evidence page count equals the number of qualifying rows.
- Yard folder/event counts and ordering follow the rule above.
- HCI is last and its Latest Backup values are newest-to-oldest.
- Every PDF page is rendered and visually inspected before release.
