# Size recognition and import layout

Approved design: wide import dialog; separate labelled code cards; backend alias
recognition; numeric/range classification; searchable full list with review filter.

Execute sequentially using RED → GREEN for each behavior:
1. (5 min) Test confirmed aliases and numeric/range/source-specific detection.
   Implement deterministic backend rules. Verify focused pytest cases, including
   original SKU identity and explicit blank overrides.
2. (5 min) Test all-code visibility, search, filtering, and corrected overrides.
   Implement labelled bordered cards and review controls. Verify Vitest cases.
3. (5 min) Test wide dialog sizing and bounded scrolling. Implement an opt-in
   wide modal used for file imports. Verify component tests and responsive render.
4. (5 min) Review scoped diff, run frontend typecheck/lint/tests and backend
   pytest; report actual results and any environmental blockers.

Numeric sizes and ranges have descriptive metadata; they are not converted to
letter sizes because the existing fashion attribute contract is a letter enum.
Keep original codes in SKU identity. Explicit user overrides take precedence.
No database migration or new dependency. Preserve unrelated workspace changes.
