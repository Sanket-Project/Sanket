import { beforeEach, expect, it, vi } from "vitest";
const get = vi.hoisted(() => vi.fn());
vi.mock("@/api/client", () => ({ apiClient: { get } }));
import { productsApi } from "@/api/products";
import { skusApi } from "@/api/skus";

beforeEach(() => get.mockReset());

it.each([productsApi, skusApi])("fetches the complete catalogue using supported page sizes", async (api) => {
  get.mockImplementation((_url, { params } = { params: { limit: 0, offset: 0 } }) => Promise.resolve({
    data: Array.from({ length: Math.min(params.limit, Math.max(0, 401 - params.offset)) },
      (_, i) => ({ id: String(params.offset + i) })),
  }));
  const rows = await api.listAll();
  expect(rows).toHaveLength(401);
  expect(get.mock.calls.map(([, { params }]) => params.offset)).toEqual([0, 200, 400]);
  expect(rows[400].id).toBe("400");
});

it.each([productsApi, skusApi])("rejects a partial catalogue when a later page fails", async (api) => {
  get.mockResolvedValueOnce({ data: Array.from({ length: 200 }, (_, i) => ({ id: String(i) })) })
    .mockRejectedValueOnce(new Error("Catalogue unavailable"));
  await expect(api.listAll()).rejects.toThrow("Catalogue unavailable");
});
