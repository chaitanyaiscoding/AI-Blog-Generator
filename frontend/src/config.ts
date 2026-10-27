// Django backend address. Override with BUN_PUBLIC_API_URL if it runs elsewhere.
// Bun only inlines the variable when it is set; otherwise `process` doesn't
// exist in the browser, so fall back instead of crashing.
//
// The fallback reuses the page's hostname (localhost or 127.0.0.1) so the
// session cookie is sent: browsers treat localhost and 127.0.0.1 as different sites.
function getApiUrl(): string {
  const fallback = `${window.location.protocol}//${window.location.hostname}:8000`;
  try {
    return process.env.BUN_PUBLIC_API_URL ?? fallback;
  } catch {
    return fallback;
  }
}

export const API_URL = getApiUrl();
