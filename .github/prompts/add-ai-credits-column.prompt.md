---
mode: agent
description: Add AI credits column to Users tab table and make all columns sortable by header click.
---

## Task

Add a total AI credits column to the user table on the Users tab and make every column header sortable (click to toggle ascending/descending).

## Backend

1. In `backend/app/analytics.py` → `users_list()`, query `billing_usage` for per-user AI credit totals within the window. Reuse `_COPILOT_BILLABLE_SKU_SQL`. Add `"ai_credits"` to each output dict.
2. Add a test in `backend/tests/test_analytics_extended.py` asserting `ai_credits` is present and correct.

## Frontend

3. Add `ai_credits: number` to the `UserRow` interface in `frontend/src/api.ts`.
4. In `frontend/src/components/UsersTab.tsx`:
   - Add `useState` for `sortCol` and `sortDir` (default: `prs` desc).
   - Sort the filtered array client-side before rendering.
   - Make each `<th>` clickable: toggle direction on same column, switch to desc on new column. Show ▲/▼ indicator.
   - Add "AI credits" column after "Net lines" using `fmtNum()`.
5. Add `.sortable-th` styles in `frontend/src/styles.css` (cursor pointer, hover highlight).

## Verification

- `pytest backend/tests/` passes
- `npm run build` in `frontend/` has no errors
- Column order: User | Status | PRs | Net lines | AI credits
- Click any header → rows re-sort; click again → direction toggles
