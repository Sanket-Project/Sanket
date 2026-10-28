import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import config from "../tailwind.config";

let css: string;
test.beforeAll(async () => {
  css = (await postcss([tailwindcss(config)]).process(readFileSync("src/styles/index.css", "utf8"), { from: undefined })).css;
});

for (const dark of [false, true]) {
  test(`dropdown follows ${dark ? "dark" : "light"} surfaces, reserves arrow space, and keeps native selection`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.setContent(`<html class="${dark ? "dark" : ""}"><head><style>${css}</style></head><body><main style="padding:24px"><label>Period<select class="input" aria-label="Period"><option value="four">Four weeks</option><option value="eight">Eight weeks</option></select></label><select disabled aria-label="Unavailable period"><option>Unavailable</option></select></main></body></html>`);
    const select = page.getByRole("combobox", { name: "Period", exact: true });
    const style = await select.evaluate((element) => {
      const field = getComputedStyle(element);
      const picker = getComputedStyle(element, "::picker(select)");
      return { appearance: field.appearance, padding: parseFloat(field.paddingRight), background: field.backgroundColor, pickerBackground: picker.backgroundColor, pickerRadius: picker.borderRadius };
    });
    expect(style.appearance).toBe("base-select");
    expect(style.padding).toBeGreaterThanOrEqual(36);
    expect(style.pickerBackground).toBe(style.background);
    expect(parseFloat(style.pickerRadius)).toBeGreaterThanOrEqual(10);
    expect(await page.getByRole("combobox", { name: "Unavailable period" }).evaluate((element) => getComputedStyle(element).cursor)).toBe("not-allowed");
    await select.press("Space");
    await page.keyboard.press("End");
    await page.keyboard.press("Enter");
    await expect(select).toHaveValue("eight");
    expect(await select.evaluate((element) => element.getBoundingClientRect().right)).toBeLessThanOrEqual(375);
  });
}
