import { test, expect } from '@playwright/test';
import { dismissConsentIfPresent } from './helpers';

test.describe('Google search', () => {
  // KAN-5
  test('User can search and see results', async ({ page }) => {
    await page.goto('/');
    await dismissConsentIfPresent(page);

    const searchBox = page.getByRole('combobox', { name: /Search/i });
    await searchBox.fill('playwright testing');
    await searchBox.press('Enter');

    await expect(page).toHaveURL(/search\?/);
    await expect(page.locator('#search a').first()).toBeVisible();
    await expect(page.getByRole('combobox', { name: /Search/i })).toHaveValue('playwright testing');
  });

  // KAN-6
  test('Search box shows autocomplete suggestions while typing', async ({ page }) => {
    await page.goto('/');
    await dismissConsentIfPresent(page);

    const searchBox = page.getByRole('combobox', { name: /Search/i });
    await searchBox.pressSequentially('playwri', { delay: 50 });

    const suggestions = page.locator('ul[role="listbox"] li');
    await expect(suggestions.first()).toBeVisible();
    expect(await suggestions.count()).toBeGreaterThan(0);
  });

  // KAN-11
  test('User can clear and re-run a search from the results page', async ({ page }) => {
    await page.goto('/search?q=playwright');
    await dismissConsentIfPresent(page);

    const searchBox = page.getByRole('combobox', { name: /Search/i });
    await expect(searchBox).toHaveValue('playwright');

    await searchBox.fill('');
    await searchBox.fill('cypress testing');
    await searchBox.press('Enter');

    await expect(page).toHaveURL(/q=cypress/);
  });
});
