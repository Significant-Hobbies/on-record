import { AsyncLocalStorage } from 'node:async_hooks';

const tracking = new AsyncLocalStorage<{ degraded: boolean }>();

export function runWithDegradedTracking<T>(
  fn: () => T | Promise<T>
): Promise<{ result: T; degraded: boolean }> {
  const store = { degraded: false };
  return tracking.run(store, async () => {
    const result = await fn();
    return { result, degraded: store.degraded };
  });
}

export function markDegraded(): void {
  const store = tracking.getStore();
  if (store) {
    store.degraded = true;
  }
}
