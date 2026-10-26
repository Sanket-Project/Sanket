import { apiClient } from "./client";

export type LocationKind = "warehouse" | "store" | "unconfirmed";

export interface Location {
  id: string;
  code: string;
  name: string;
  kind: LocationKind;
  parent_location_id: string | null;
  lead_time_days_from_parent: number | null;
  is_active: boolean;
}

export interface Network {
  allocation_ready: boolean;
  transfers_ready: boolean;
  missing: string[];
}

export interface LocationsResponse {
  locations: Location[];
  network: Network;
}

export type LocationPatch = Partial<
  Pick<Location, "name" | "kind" | "parent_location_id" | "lead_time_days_from_parent" | "is_active">
>;

export const locationsApi = {
  list: () => apiClient.get<LocationsResponse>("/locations").then((r) => r.data),
  update: (id: string, patch: LocationPatch) =>
    apiClient
      .patch<{ location: Location; network: Network }>(`/locations/${id}`, patch)
      .then((r) => r.data),
};
