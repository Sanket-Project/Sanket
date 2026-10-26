import type { Decision } from "@/api/decisions";

export function groupByRoute(items: Decision[]) {
  const groups = new Map<string, { key: string; source: string; destination: string; items: Decision[]; units: number }>();
  for (const item of items) {
    if (item.kind !== "allocation" && item.kind !== "transfer") continue;
    const source = item.source_location_code ?? "Unknown origin";
    const destination = item.location_code ?? "Unknown destination";
    const key = `${item.source_location_id ?? source}:${item.location_id ?? destination}`;
    const group = groups.get(key) ?? { key, source, destination, items: [], units: 0 };
    group.items.push(item);
    group.units += item.recommended_units;
    groups.set(key, group);
  }
  const rank = { critical: 0, high: 1, normal: 2, low: 3 };
  return [...groups.values()].sort((a, b) =>
    Math.min(...a.items.map((d) => rank[d.urgency])) - Math.min(...b.items.map((d) => rank[d.urgency])));
}
