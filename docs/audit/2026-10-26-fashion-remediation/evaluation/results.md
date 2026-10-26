# Rolling-origin fashion evaluation

Synthetic diagnostic only; does not establish Swecha accuracy.

CPU · amazon/chronos-t5-small · 100 samples · seed 25102026 · Monday UTC · 8-week horizon.

| Model | Validation WAPE % | Test WAPE % | Test bias % | Interval coverage % | Test points |
| --- | --- | --- | --- | --- | --- |
| chronos | 20.959962081349325 | 7.4548518554536605 | -2.790908554133732 | 75.0 | 48 |
| last_value | 24.894514767932492 | 12.360939431396787 | -3.0902348578491967 | None | 48 |
| ma4 | 23.115024766097964 | 23.4548825710754 | -15.698393077873918 | None | 48 |
| seasonal_naive52 | 34.08548890111906 | 18.98470097357441 | -9.944367176634215 | None | 40 |
| croston_sba | 28.548295832720065 | 22.763125083510293 | -13.28222356701499 | None | 48 |
| adida | 23.43349844065309 | 23.007416563658836 | -8.533992583436337 | 56.25 | 48 |

Routing was selected from validation only; test evaluated once after freezing the rule.
Selected rule: per_sku. Production gate: False.

Full per-SKU, cohort, omission, spread and fixture hashes are in results.json.
Point-only baselines have no interval coverage; ADIDA intervals are the repository's approximate Poisson intervals.
