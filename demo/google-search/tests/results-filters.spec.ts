import { test, expect } from '@playwright/test';
import { dismissConsentIfPresent } from './helpers';

test.describe('Search results filters', () => {
  // KAN-7
  test(`"I'm Feeling Lucky" navigates directly to a result`, async ({ page }) => {
    await page.goto('/');
    await dismissConsentIfPresent(page);

    const searchBox = page.getByRole('combobox', { name: /Search/i });
    await searchBox.fill('playwright');

    await Promise.all([page.waitForNavigation(), page.getByRole('button', { name: "I'm Feeling Lucky" }).click()]);

    await expect(page).not.toHaveURL(/\/search\?/);
  });

  // KAN-8
  test('Search results page shows filter tabs (All, Images, News, Videos)', async ({ page }) => {
    await page.goto('/search?q=playwright');
    await dismissConsentIfPresent(page);

    const allTab = page.getByRole('link', { name: 'All', exact: true });
    const imagesTab = page.getByRole('link', { name: 'Images', exact: true });

    await expect(allTab).toBeVisible();
    await expect(imagesTab).toBeVisible();

    await imagesTab.click();
    await expect(page).toHaveURL(/tbm=isch/);
  });

  // KAN-12
  test('Images tab displays a grid of image thumbnails', async ({ page }) => {
    await page.goto('/search?q=playwright&tbm=isch');
    await dismissConsentIfPresent(page);

    const thumbnails = page.locator('img[id^="dimg_"]');
    await expect(thumbnails.first()).toBeVisible();
    expect(await thumbnails.count()).toBeGreaterThan(1);
  });
});
