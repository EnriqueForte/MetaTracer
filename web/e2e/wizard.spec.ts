import { expect, test } from "@playwright/test";

test("scope modal stays closed until the checkbox is checked", async ({ page }) => {
  await page.goto("/v2");
  await page.getByRole("button", { name: "Start scan" }).click();
  await expect(page.getByText("Enter at least one target.")).toBeVisible();

  await page.getByLabel("Targets").fill("example.com");
  await page.getByLabel("Authorized scope domains").fill("example.com");
  await page.getByRole("button", { name: "Start scan" }).click();

  await expect(page.getByRole("heading", { name: "Confirm authorized scope" })).toBeVisible();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Confirm and start scan" })).toBeDisabled();
});
