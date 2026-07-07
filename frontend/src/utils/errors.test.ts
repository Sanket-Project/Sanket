import { describe, expect, it } from "vitest";
import { getErrorMessage } from "./errors";

describe("getErrorMessage", () => {
  it("returns a string detail from an axios-style error", () => {
    const err = { response: { data: { detail: "Email already registered" } } };
    expect(getErrorMessage(err)).toBe("Email already registered");
  });

  it("joins FastAPI 422 array-of-objects detail into one string", () => {
    const err = {
      response: {
        data: {
          detail: [
            { type: "value_error", loc: ["body", "email"], msg: "invalid email" },
            { type: "missing", loc: ["body", "name"], msg: "field required" },
          ],
        },
      },
    };
    expect(getErrorMessage(err)).toBe("invalid email, field required");
  });

  it("handles a single object detail with a msg field", () => {
    const err = { response: { data: { detail: { msg: "boom" } } } };
    expect(getErrorMessage(err)).toBe("boom");
  });

  it("falls back to err.message when there is no response detail", () => {
    expect(getErrorMessage(new Error("Network Error"))).toBe("Network Error");
  });

  it("returns the provided fallback for an unknown/empty value", () => {
    expect(getErrorMessage({}, "Something went wrong")).toBe("Something went wrong");
    expect(getErrorMessage(null, "Fallback")).toBe("Fallback");
  });

  it("never returns a raw object (guards against React error #31)", () => {
    const err = { response: { data: { detail: { unexpected: "shape" } } } };
    expect(typeof getErrorMessage(err)).toBe("string");
  });
});
