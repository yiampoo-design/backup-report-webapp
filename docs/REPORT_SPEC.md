# Approved report specification

This document is the implementation contract extracted from the six approved
historical PDF reports. The historical files are intentionally not stored in
Git because they contain company information.

## Source priority

1. Active Backup rows and audit fields: only the NAS file
   `abb_daily_result_YYYY-MM-DD.csv` whose filename matches the report date.
   Download it through the visible File Station UI, or use an explicitly
   selected manual fallback. Never use `latest` or substitute a previous date.
2. Active Backup Audit detail: the appended `AUDIT` section of the same dated
   CSV. No Active Backup API or screen capture supplies report values.
3. Yard: dedicated Drive ShareSync Web API for synced folders and sync history.
4. HCI: verified Sangfor browser capture.

When sources disagree, preserve the CSV row and display a warning. Never alter
the authoritative CSV value to make the sources agree.

## Page sequence

### 1. Active Backup overview

The page contains the result table with exactly these columns and this order:

1. `No.`
2. `Group`
3. `Backup Task`
4. `Status`
5. `Source`
6. `Start` (the authoritative `Last Backup` value from the dated CSV)
7. `Duration`
8. `Size`
9. `File Count`
10. `Warning/Error`
11. `Unchanged`
12. `Same Size`
13. `Audit Same Size`
14. `Audit Status`

Do not calculate, reconstruct or fetch `End`; the approved daily source no
longer supplies it. Display rows in the approved DSM Task List order and
renumber `No.` for display. Preserve every other CSV value. Tasks not in the
approved list append in their original CSV order. Highlight rows requiring
attention without changing their values.

### 2. Conditional evidence pages

The dated CSV contains a human-readable `AUDIT` section after the main table.
Exclude that section from the backup row count. Create exactly one detail page
from the matching CSV `AUDIT` block for every row where:

- `Audit Status` is `Check`, or
- `Status` is not successful.

If five rows qualify, create five pages. If none qualify, create no evidence
page. These pages immediately follow the Active Backup overview.

### 3. Yard / Drive ShareSync

Display synced folders and recent sync history returned by the dedicated Yard
Drive ShareSync API. Keep folder order deterministic and show the corresponding
newest log rows beside it.

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
- Result row count matches the authoritative CSV; display order follows the
  approved DSM Task List order, with unknown tasks appended in CSV order.
- All 14 approved columns are present in the required order.
- Every displayed `Start` matches `Last Backup` exactly after formatting.
- No `End` value is synthesized or displayed.
- `Same Size`, `Audit Same Size`, and `Audit Status` match the CSV exactly.
- Evidence page count equals the number of qualifying rows.
- Yard is populated from the dedicated Drive ShareSync API module.
- No Synology API call is made to the primary NAS; the API client is Yard-only.
- HCI is last and its Latest Backup values are newest-to-oldest.
- Every PDF page is rendered and visually inspected before release.

## Source-rule change detection

Status: approved on 2026-08-13.

The application must detect material changes to the authoritative NAS report
contract, including the source filename/alias, CSV header and column count,
required fields, appended non-CSV sections, row shape, date coverage, and other
versioned schema characteristics. When a change is detected, the application
must:

1. stop final PDF generation instead of guessing, remapping or synthesizing data;
2. show a prominent warning identifying the observed and expected contract;
3. record the event in report history and the application log with timestamp,
   resolved NAS source path and a non-secret schema fingerprint; and
4. require an authorized person to approve the new rule before it becomes the
   report contract.

This detection is read-only and must not modify the NAS, its Task Scheduler,
packages, configuration or exported files.
