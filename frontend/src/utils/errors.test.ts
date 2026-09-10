import { describe, expect, it } from "vitest";
import { getErrorMessage, getServerErrorMessage, isServerError } from "./errors";

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

describe("server error handling", () => {
  it("recognises server responses so local handlers can avoid duplicate toasts", () => {
    expect(isServerError({ response: { status: 503 } })).toBe(true);
    expect(isServerError({ response: { status: 422 } })).toBe(false);
  });

  it("surfaces an intentional 502/503 detail but keeps unexpected 500s generic", () => {
    expect(
      getServerErrorMessage({
        response: {
          status: 503,
          data: { detail: "Razorpay rejected subscription setup. Please try again shortly." },
        },
      }),
    ).toBe("Razorpay rejected subscription setup. Please try again shortly.");
    expect(
      getServerErrorMessage({
        response: { status: 500, data: { detail: "internal implementation detail" } },
      }),
    ).toBe("Server error — try again shortly");
  });
});
