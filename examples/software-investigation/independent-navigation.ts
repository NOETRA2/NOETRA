/** Independent pure boundary example; no Electron dependency and no UI. */
export const NAVIGATION_CHANNEL = 'navigation:open';
export function approvedNavigation(address: string): string {
  const url = new URL(address);
  if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Only HTTPS URLs without embedded credentials are accepted.');
  return url.href;
}
