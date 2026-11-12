import { test, expect } from "@playwright/test";

// KAN-4
test("passes everywhere", async () => {
  expect(1 + 1).toBe(2);
});

test("fails always", { tag: ["@broken"] }, async () => {
  expect(1).toBe(2);
});

test.skip("is skipped", async () => {});

test("flaky until retried", async ({}, testInfo) => {
  expect(testInfo.retry).toBeGreaterThan(0);
});

test.describe("Checkout", () => {
  test("has a Jira annotation", async () => {
    test.info().annotations.push({ type: "jira", description: "SHOP-7" });
    expect("ok").toBe("ok");
  });
});
