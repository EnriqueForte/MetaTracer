import { expect, test } from "@playwright/test";

test("scope modal stays closed until the checkbox is checked", async ({ page }) => {
  // T11: Web V2 serves from the origin root, so there is no /v2 prefix.
  await page.goto("/");
  await page.getByRole("button", { name: "Iniciar escaneo" }).click();
  await expect(page.getByText("Indica al menos un objetivo.")).toBeVisible();

  await page.getByLabel("Objetivos").fill("example.com");
  await page.getByLabel("Dominios de alcance autorizado").fill("example.com");
  await page.getByRole("button", { name: "Iniciar escaneo" }).click();

  await expect(page.getByRole("heading", { name: "Confirmar alcance autorizado" })).toBeVisible();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Confirmar e iniciar escaneo" })).toBeDisabled();
});
