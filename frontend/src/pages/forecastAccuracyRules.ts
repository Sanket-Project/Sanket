/** A Monday strictly before the current UTC week — the only valid backtest cutoff. */
export function backtestCutoffError(value: string, today: Date = new Date()): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return "Enter a date.";
  const d = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== value) return "Enter a valid date.";
  if (d.getUTCDay() !== 1) return "The cutoff must be a Monday — weeks start on Monday (UTC).";
  const thisMonday = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
  thisMonday.setUTCDate(thisMonday.getUTCDate() - ((thisMonday.getUTCDay() + 6) % 7));
  if (d >= thisMonday) return "The cutoff must be before the current week.";
  return null;
}
