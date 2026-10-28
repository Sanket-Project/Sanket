import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClientReports } from "./ClientReports";

const report = {
  industry: "fashion", currency: "INR", imported_at: "2026-10-27",
  sales: { period: "1–25 October 2026", net_amount: 1000, net_units: 10, rows: 1, stores: [{ name: "Client store", net_amount: 1000, net_units: 10 }] },
  gross_profit: { period: "1 January–25 October 2026", net_sales: 5000, sales_ex_tax: 4500, cogs_ex_tax: 3000, profit: 1500, margin_pct: 33.33, rows: 1, stores: [{ name: "Client store", profit: 1500, sales_ex_tax: 4500 }], top_skus: [{ sku: "SKU-1", profit: 1500, units: 40 }] },
  purchases: { period: "January–October 2026", net_amount: 3000, net_units: 30, rows: 1, suppliers: [{ name: "Supplier A", net_amount: 3000, net_units: 30 }] },
  limitations: ["Dated SKU sales are unavailable; forecasts require SKU-level sales history."],
  sources: ["Client sales.xlsx"],
};

describe("ClientReports", () => {
  it("separates source periods, stores and supplier totals and discloses forecast limitations", () => {
    render(<ClientReports report={report} />);
    expect(screen.getByRole("heading", { name: "Your sales, at a glance" })).toBeInTheDocument();
    expect(screen.getAllByText("1–25 October 2026").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 January–25 October 2026").length).toBeGreaterThan(0);
    expect(screen.getByText("Supplier A")).toBeInTheDocument();
    expect(screen.getByText("SKU-1")).toBeInTheDocument();
    expect(screen.getByText(/Dated SKU sales are unavailable/)).toBeInTheDocument();
    expect(screen.getByText("Client sales.xlsx")).toBeInTheDocument();
    expect(screen.queryByText(/live feed/i)).not.toBeInTheDocument();
  });

  it("shows branch sales as a ranked visual comparison with exact amounts", () => {
    render(<ClientReports report={{ ...report, sales: { ...report.sales, net_amount: 4000, stores: [
      { name: "South", net_amount: 1000, net_units: 10 },
      { name: "North", net_amount: 3000, net_units: 30 },
    ] } }} />);
    const branches = screen.getByRole("region", { name: "Sales by branch" });
    expect(branches.textContent!.indexOf("North")).toBeLessThan(branches.textContent!.indexOf("South"));
    expect(screen.getByText("75% of branch sales")).toBeInTheDocument();
    expect(screen.getByText(/North has the highest sales/)).toBeInTheDocument();
  });

  it("omits branch sections when the source has no named branches", () => {
    render(<ClientReports report={{ ...report,
      sales: { ...report.sales, stores: [{ name: "  ", net_amount: 1000, net_units: 10 }] },
      gross_profit: { ...report.gross_profit, stores: [] },
    }} />);
    expect(screen.queryByRole("region", { name: "Sales by branch" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Profit by branch" })).not.toBeInTheDocument();
  });

  it("does not turn negative branch sales into a positive share", () => {
    render(<ClientReports report={{ ...report, sales: { ...report.sales, stores: [
      { name: "Returns branch", net_amount: -100, net_units: -1 },
    ] } }} />);
    expect(screen.getByText(/Returns exceeded sales/)).toBeInTheDocument();
    expect(screen.queryByText(/100% of branch sales/)).not.toBeInTheDocument();
  });
});
