// Pure text for the Settings tab, kept out of the component so it's testable.

/** The backend this app talks to; must match remotes[].baseUrl in manifest.yml. */
export const BACKEND_URL = 'https://playwright-traceability.fly.dev';

/**
 * A copy-paste upload command for CI, matching scripts/push_test_inventory.py's
 * real flags. The key is read from the INGEST_API_KEY environment variable (a
 * CI secret) - the script falls back to it - so it never appears in the snippet.
 */
export function uploadCommand(backendUrl = BACKEND_URL) {
  return [
    '# INGEST_API_KEY: store the key above as a CI secret and expose it as this env var',
    'python -m scripts.push_test_inventory \\',
    `  --backend-url ${backendUrl} \\`,
    '  --report playwright-report.json \\',
    '  --specs-dir tests/',
  ].join('\n');
}
