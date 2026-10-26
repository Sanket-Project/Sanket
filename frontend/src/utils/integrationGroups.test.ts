import { describe, expect, it } from "vitest";
import { connectionGroups } from "@/utils/integrationGroups";

// Deep audit F16: "Connections needing your attention" listed the healthy CSV
// upload alongside failures, so a working source read as a problem.

const connector = (key: string, status: string, connected: boolean) => ({ key, status, connected });

describe("connectionGroups", () => {
  it("separates problems from healthy connected sources", () => {
    const groups = connectionGroups([
      connector("csv_upload", "connected", true),
      connector("shopify", "error", true),
      connector("tally", "requested", false),
      connector("zoho", "disconnected", false),
    ]);

    expect(groups.attention.map((c) => c.key)).toEqual(["shopify", "tally"]);
    expect(groups.connected.map((c) => c.key)).toEqual(["csv_upload"]);
  });

  it("never lists a healthy connected source as needing attention", () => {
    const groups = connectionGroups([connector("csv_upload", "connected", true), connector("rest_api", "syncing", true)]);
    expect(groups.attention).toEqual([]);
    expect(groups.connected).toHaveLength(2);
  });
});
