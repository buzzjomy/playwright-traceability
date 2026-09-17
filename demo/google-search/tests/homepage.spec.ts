import { test, expect } from '@playwright/test';
import { dismissConsentIfPresent } from './helpers';

test.describe('Google homepage', () => {
  // KAN-4
  test('Google homepage displays search box and logo', async ({ page }) => {
    await page.goto('/');
    await dismissConsentIfPresent(page);

    await expect(page).toHaveTitle(/Google/);
    await expect(page.getByRole('img', { name: 'Google' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: /Search/i })).toBeVisible();
  });

  // KAN-9
  test('Homepage footer exposes legal and info links', async ({ page }) => {
    await page.goto('/');
    await dismissConsentIfPresent(page);

    const privacyLink = page.getByRole('link', { name: 'Privacy' });
    const termsLink = page.getByRole('link', { name: 'Terms' });

    await expect(privacyLink).toBeVisible();
    await expect(termsLink).toBeVisible();
    await expect(privacyLink).toHaveAttribute('href', /.+/);
    await expect(termsLink).toHaveAttribute('href', /.+/);
  });

  // KAN-10
  test('Interface language can be changed from the homepage', async ({ page }) => {
    await page.goto('/');
    await dismissConsentIfPresent(page);

    const languageLinks = page.locator('#SIvCob a');
    await expect(languageLinks.first()).toBeVisible();
    expect(await languageLinks.count()).toBeGreaterThan(0);
  });

  // KAN-13
  test('Sign in link is visible for a logged-out visitor', async ({ page }) => {
    await page.goto('/');
    await dismissConsentIfPresent(page);

    await expect(page.getByRole('link', { name: /Sign in/i })).toBeVisible();
  });
});
