export class ApiError extends Error {
  constructor(public code: string, message: string, public details: any = {}) { super(message); }
}
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.method && options.method !== 'GET') {
    headers.set('X-Reconcile-Client', 'web');
    if (!path.startsWith('/api/auth/')) headers.set('Idempotency-Key', headers.get('Idempotency-Key') || crypto.randomUUID());
    if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 401 && path !== '/api/auth/login') window.dispatchEvent(new Event('session-expired'));
    throw new ApiError(body?.error?.code || 'REQUEST_FAILED', body?.error?.message || 'The request failed. Please try again.', body?.error?.details);
  }
  return response.status === 204 ? undefined as T : await response.json();
}
export const post = (path: string, body: any = {}) => api(path, { method: 'POST', body: JSON.stringify(body) });
export const labels: Record<string, string> = {
  ready_for_approval: 'Ready for approval', needs_review: 'Needs review', hold: 'On hold', approved: 'Approved',
  rejected: 'Rejected', processing: 'Processing', processing_failed: 'Processing failed',
};
export function money(value?: string | null, currency = 'INR') {
  if (value == null) return 'Not found';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value));
}
export const date = (value: string) => new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' });
