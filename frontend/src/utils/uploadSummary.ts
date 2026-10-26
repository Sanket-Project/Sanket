import type { UploadResult } from "@/api/integrations";

/**
 * One line describing what an upload actually changed.
 *
 * Sales uploads are replay-safe, so "imported" alone would hide the useful
 * part: how many rows were new, how many were already there (a re-upload), and
 * how many corrected an earlier value.
 */
export function describeUploadResult(r: UploadResult): string {
  if (r.kind !== "sales" || r.identity_mode == null) {
    return `Imported ${r.rows_imported} of ${r.rows_total} rows`;
  }
  const parts = [
    `${r.rows_inserted} new`,
    `${r.rows_unchanged} already imported`,
    `${r.rows_updated} corrected`,
  ];
  if (r.rows_skipped > 0) parts.push(`${r.rows_skipped} skipped`);
  return parts.join(" · ");
}
