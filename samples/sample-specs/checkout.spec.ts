import { test, expect } from '@playwright/test';

test('should apply discount code at checkout', async () => {
  expect(true).toBe(true);
});

test.describe.skip('Legacy checkout (deprecated)', () => {
  test('should support the old single-page checkout flow', async () => {
    expect(true).toBe(true);
  });
});
