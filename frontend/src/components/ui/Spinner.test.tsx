import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { PageLoader } from "./Spinner";

it("announces the pending page state to assistive technology", () => {
  render(<PageLoader />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
});
