# Approved swecha-demo business-data reset

The user explicitly approved deleting all SKU samples, sales, stock, locations
and other business data, retaining credentials, login and settings. Other
workspaces and source-code test fixtures are outside this reset.

1. Inspect the exact recovered database and tenant; inventory every tenant table.
   Verify target slug/UUID and retained settings/account records (read only).
2. Stop the identified local dev-stack process tree so API/ML/workers cannot
   write fresh derived data during reset. Preserve existing stack logs.
3. Create a custom-format full database backup under backups/ and validate its
   archive listing. Do not print any credentials or password hashes.
4. Execute an explicit one-off data migration using MIGRATION_DATABASE_URL.
   Temporarily grant missing DELETE permissions inside its transaction, switch
   to sanket_app, set the tenant context, verify RLS is enforced, and delete only
   allowlisted business rows with an explicit tenant filter. Revoke the grants
   before committing; no privilege expansion survives the transaction.
5. First run the exact transaction with rollback and assert every targeted
   business table is empty while accounts/settings are identical. Then run it
   with commit and repeat those assertions on a fresh connection.
6. Remove only this tenant's queued forecast jobs and invalidate its response
   cache. Restart the normal local stack. Verify login still works and product,
   SKU, inventory, forecast and decision APIs show empty data.
7. Refresh the Chrome workspace and verify its empty inventory screen. Run
   repository verification commands and record actual results. Application
   source code and schemas are not changed by this data-only operation.

Preserve tenants/users, refresh tokens, industry profiles, subscriptions,
invitations, integration/webhook connection settings, alert rules, billing usage
and immutable security audit history. Delete uploaded catalogue/history/stock,
locations, POS rows, forecast runs/results/refresh state, recommendations,
shortage alerts, derived accuracy/quality data and tenant signal data.
