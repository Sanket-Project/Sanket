import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Skeleton, SkeletonCard } from "./Skeleton";

describe("Skeleton", () => {
  it("renders one pulse row by default", () => {
    const { container } = render(<Skeleton />);
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(1);
  });

  it("renders the requested number of rows", () => {
    const { container } = render(<Skeleton rows={4} />);
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(4);
  });

  it("applies a custom className to the wrapper", () => {
    const { container } = render(<Skeleton className="my-custom" />);
    expect(container.firstChild).toHaveClass("my-custom");
  });

  it("SkeletonCard renders without crashing", () => {
    const { container } = render(<SkeletonCard />);
    expect(container.firstChild).toBeInTheDocument();
  });
});
