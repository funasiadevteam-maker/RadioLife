// Currency-aware money formatter. Shows an ISO code prefix, e.g. "AED 20.00".
// Defaults to AED (the app's Dubai home market) when no currency is supplied.
export function money(cents?: number, currency?: string): string {
  const code = String(currency || 'AED').toUpperCase();
  return `${code} ${((cents || 0) / 100).toFixed(2)}`;
}
