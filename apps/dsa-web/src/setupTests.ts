import '@testing-library/jest-dom';

class IntersectionObserverMock implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = '';
  readonly thresholds = [0];

  disconnect() {}

  observe() {}

  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }

  unobserve() {}
}

Object.defineProperty(globalThis, 'IntersectionObserver', {
  writable: true,
  value: IntersectionObserverMock,
});

function installLocalStorageMockIfNeeded() {
  try {
    if (
      typeof globalThis.localStorage !== 'undefined' &&
      typeof globalThis.localStorage.getItem === 'function' &&
      typeof globalThis.localStorage.setItem === 'function' &&
      typeof globalThis.localStorage.clear === 'function'
    ) {
      return;
    }
  } catch {
    // jsdom can throw when localStorage is unavailable. Fall through to mock.
  }

  let store: Record<string, string> = {};
  const storage: Storage = {
    get length() {
      return Object.keys(store).length;
    },
    clear() {
      store = {};
    },
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
    key(index: number) {
      return Object.keys(store)[index] ?? null;
    },
    removeItem(key: string) {
      delete store[key];
    },
    setItem(key: string, value: string) {
      store[key] = String(value);
    },
  };

  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: storage,
  });
}

installLocalStorageMockIfNeeded();
