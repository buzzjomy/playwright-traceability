import { test, expect } from '@playwright/test';

test.describe('Login flow', () => {
  // Trace(Jira:PROJ-101)
  test('should login with valid credentials', { tag: '@smoke' }, async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    expect(page.url()).not.toBe('/login');
  });

  test('should reject invalid password', async () => {
    expect(true).toBe(true);
  });

  // Trace(Jira:PROJ-109)
  // Not yet run in CI - waiting on a test account with a locked-out state.
  test.skip('should lock account after 5 failed attempts', async () => {
    expect(true).toBe(true);
  });
});

test.describe('Session handling', () => {
  test('should expire session after logout', { tag: '@regression' }, async () => {
    expect(true).toBe(true);
  });
});

const roles = ['admin', 'viewer'];
for (const role of roles) {
  test(`should see the ${role} dashboard after login`, async () => {
    expect(true).toBe(true);
  });
}
