# Recreated synthetic legacy upgrade verification

This is **not** a restore of the original 25 October audit database. That database was unavailable. The evidence here recreates a small, explicitly labelled synthetic database at revision `0021`, including duplicate pre-fix upload rows, and verifies the actual `0022`–`0024` upgrade chain after a dump/restore.

Run from the repository root:

```powershell
backend/.venv/Scripts/python.exe docs/audit/2026-10-26-fashion-remediation/restore/verify_legacy_upgrade.py
```

The script requires the disposable `sanket-remediation-restore-db` container on port `55434` and the local fixture role/password documented in the script. It creates only `sanket_legacy_source` and `sanket_legacy_upgrade`, refuses to replace either database if it exists, and does not touch the separate `sanket` database reserved for the current E2E restore. Migration commands use `MIGRATION_DATABASE_URL`; fixture insertion and content/RLS checks use `sanket_app`, with `NOSUPERUSER` and `NOBYPASSRLS` verified.

Results (`legacy-upgrade-verification.json`):

- Read-only `pg_dump` of revision `0021`; source revision remained `0021`.
- Restored target upgraded successfully through `0022`, `0023`, `0024`.
- Both tenants' row counts, unit totals, and hashes of every original sale field were unchanged.
- Tenant A retained 5 rows and 24 units; tenant B retained 2 rows and 10 units.
- Tenant A's two duplicate groups and tenant B's one duplicate group acquired matching record keys with 2 copies each. No repair/delete was applied.
- The zero-demand non-upload row remained unkeyed.
- The same order/line key exists in both tenants; RLS still exposed zero foreign-tenant rows under each tenant context.

The binary dump is local evidence (`synthetic-legacy-0021.dump`, 480624 bytes) and is not committed. Its SHA-256 is recorded in the JSON. Logs and the reproducible script are committed; the live disposable databases are preserved for inspection.
