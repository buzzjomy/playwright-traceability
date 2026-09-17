import { Page } from '@playwright/test';

/** Dismiss Google's cookie-consent interstitial if it appears (EU/some locales only). */
export async function dismissConsentIfPresent(page: Page): Promise<void> {
  const acceptButton = page.getByRole('button', { name: /Accept all|I agree/i });
  try {
    await acceptButton.click({ timeout: 3000 });
  } catch {
    // No consent dialog shown for this session/locale - nothing to do.
  }
}
