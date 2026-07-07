// Groups raw trend "drivers" (one row per source per keyword) into one entry
// per product, so the same keyword can't appear twice with opposite scores.
//
// The backend deliberately returns *raw evidence* — e.g. Sneakers can be +1.0
// on Reddit (social buzz) and -0.88 on Google (search interest) at the same
// time. Showing those as two separate rows invites users to read a conclusion
// off a single source. Here we reconcile them: a weighted consensus score plus
// an explicit "do the sources agree?" flag, with the per-source detail kept for
// drill-down. This is presentation only — the fused TrendScore is unchanged.

export interface RawDriver {
  series_key: string;
  source: string;
  score: number;
  weight?: number;
}

export interface DriverSource {
  /** Display source tag, e.g. "Reddit", "Google". */
  tag: string;
  score: number;
  weight: number;
}

export interface GroupedDriver {
  label: string;
  /** Weighted-mean score across sources, in [-1, +1]. */
  consensus: number;
  sources: DriverSource[];
  /** True when every non-flat source points the same direction. */
  agree: boolean;
  /** True when at least one source lifts and another drags. */
  conflict: boolean;
  /** Ranking metric — strongest single-source signal, so a loud-but-mixed
   *  product still surfaces instead of being averaged into invisibility. */
  impact: number;
}

const DEADZONE = 0.05;

function sign(v: number): -1 | 0 | 1 {
  return v > DEADZONE ? 1 : v < -DEADZONE ? -1 : 0;
}

/**
 * @param items   raw drivers (drivers and/or demand_factors)
 * @param labelOf maps a driver to its display label (the grouping key)
 * @param tagOf   maps a driver to its display source tag
 */
export function groupDrivers(
  items: RawDriver[],
  labelOf: (seriesKey: string, source: string) => string,
  tagOf: (seriesKey: string, source: string) => string,
): GroupedDriver[] {
  const groups = new Map<string, { label: string; sources: DriverSource[] }>();

  for (const d of items) {
    const label = labelOf(d.series_key, d.source) || d.source.replace(/_/g, " ");
    const key = label.toLowerCase().trim();
    let g = groups.get(key);
    if (!g) {
      g = { label, sources: [] };
      groups.set(key, g);
    }
    g.sources.push({
      tag: tagOf(d.series_key, d.source),
      score: d.score,
      weight: d.weight && d.weight > 0 ? d.weight : 1,
    });
  }

  const out: GroupedDriver[] = [];
  for (const { label, sources } of groups.values()) {
    sources.sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
    const totalW = sources.reduce((s, x) => s + x.weight, 0) || 1;
    const consensus = sources.reduce((s, x) => s + x.score * x.weight, 0) / totalW;
    const signs = sources.map((x) => sign(x.score)).filter((s) => s !== 0);
    const hasUp = signs.includes(1);
    const hasDown = signs.includes(-1);
    out.push({
      label,
      consensus,
      sources,
      conflict: hasUp && hasDown,
      agree: sources.length > 1 && !(hasUp && hasDown),
      impact: Math.abs(sources[0]?.score ?? 0),
    });
  }

  out.sort((a, b) => b.impact - a.impact);
  return out;
}
