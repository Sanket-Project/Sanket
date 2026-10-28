import type { PersistedForecast } from "@/api/forecasts";

export function ForecastRunStatus({ forecast, refreshing, generating, queued = false, waitingForOtherIndustry = false, stale = false, error }: {
  forecast: PersistedForecast | null;
  refreshing: boolean;
  generating: boolean;
  queued?: boolean;
  waitingForOtherIndustry?: boolean;
  stale?: boolean;
  error: string | null;
}) {
  const seconds = forecast?.age_seconds ?? 0;
  const age = seconds < 60 ? "just now" : seconds < 3600 ? `${Math.floor(seconds / 60)} minutes ago`
    : seconds < 86400 ? `${Math.floor(seconds / 3600)} hours ago` : `${Math.floor(seconds / 86400)} days ago`;
  return <div className="space-y-1 text-xs text-content-muted">
    <p role="status" aria-live="polite">
      {forecast ? <><time dateTime={forecast.completed_at} title={new Date(forecast.completed_at).toLocaleString()}>Generated {age}</time>
        {waitingForOtherIndustry ? " · Waiting for another forecast to finish…" : queued ? " · Forecast queued…" : refreshing && " · Refreshing…"}</>
        : waitingForOtherIndustry ? "Waiting for another forecast to finish before generating this industry's forecast…"
          : queued ? "Your first forecast is queued…" : generating ? "Generating your first forecast…"
          : refreshing ? "Requesting forecast generation…" : "No saved forecast yet."}
    </p>
    {forecast && stale && <p role="status">Saved forecast is out of date. Wait for a successful refresh before using it with your latest data.</p>}
    {error && <p role="alert">{forecast ? "Refresh failed; showing the saved forecast. It may not include your latest data. " : "Forecast could not be generated. "}{error}</p>}
    {forecast?.location_status !== "ready" && forecast && <p role="status">
      {forecast.location_reason || (forecast.location_status === "failed" ? "Location split failed; SKU forecasts remain available." : "Preparing location forecasts…")}
    </p>}
  </div>;
}
