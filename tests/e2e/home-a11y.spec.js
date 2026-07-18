const { expect, test } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test('home renders accessibly at each required viewport', async ({ page }) => {
  const response = await page.goto('/');
  expect(response).not.toBeNull();
  expect(response.ok()).toBe(true);
  await expect(page).toHaveURL(/\/$/);
  await expect(
    page.getByRole('main').getByRole('heading', {
      level: 1,
      name: '안전하게 연결되는 중고거래',
      exact: true,
    }),
  ).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
