import { QueryClient } from '@tanstack/react-query';
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { persistQueryClient } from '@tanstack/react-query-persist-client';
import { compress, decompress } from 'lz-string';

const STORAGE_KEY = 'psd-query-cache-v1';
const MAX_AGE = 1000 * 60 * 60 * 24; // 24 hours
const MAX_CACHE_SIZE = 5 * 1024 * 1024; // 5MB

/**
 * Custom storage with compression support
 */
const compressedStorage = {
  getItem: (key: string): string | null => {
    try {
      const compressed = localStorage.getItem(key);
      if (!compressed) return null;

      const decompressed = decompress(compressed);
      return decompressed;
    } catch (error) {
      console.error('[queryPersistence] Error reading from storage:', error);
      // Clear corrupted cache
      localStorage.removeItem(key);
      return null;
    }
  },
  setItem: (key: string, value: string): void => {
    try {
      const compressed = compress(value);

      // Check size before storing
      const size = new Blob([compressed]).size;
      if (size > MAX_CACHE_SIZE) {
        console.warn(`[queryPersistence] Cache size (${size} bytes) exceeds limit, clearing old cache`);
        localStorage.removeItem(key);
        return;
      }

      localStorage.setItem(key, compressed);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'QuotaExceededError') {
        console.warn('[queryPersistence] localStorage quota exceeded, clearing cache');
        localStorage.removeItem(key);
      } else {
        console.error('[queryPersistence] Error writing to storage:', error);
      }
    }
  },
  removeItem: (key: string): void => {
    localStorage.removeItem(key);
  },
};

/**
 * Determine if a query should be persisted to localStorage
 */
function shouldDehydrateQuery(query: any): boolean {
  const queryKey = query.queryKey;

  // Only persist successful queries
  if (query.state.status !== 'success') {
    return false;
  }

  // List of query key prefixes to persist
  const persistable = ['psd', 'msb', 'rules', 'fundamentals'];

  // Check if query key starts with any persistable prefix
  const keyString = Array.isArray(queryKey) ? queryKey[0] : queryKey;
  return persistable.some(prefix =>
    typeof keyString === 'string' && keyString.toLowerCase().includes(prefix.toLowerCase())
  );
}

/**
 * Setup React Query persistence with localStorage
 */
export function setupQueryPersistence(queryClient: QueryClient): void {
  try {
    const persister = createSyncStoragePersister({
      storage: compressedStorage,
      key: STORAGE_KEY,
    });
    type PersistOptions = Parameters<typeof persistQueryClient>[0];

    persistQueryClient({
      // TanStack packages can resolve to duplicate query-core types; align to expected type.
      queryClient: queryClient as unknown as PersistOptions["queryClient"],
      persister,
      maxAge: MAX_AGE,
      dehydrateOptions: {
        shouldDehydrateQuery,
      },
    });

    console.log('[queryPersistence] Query persistence initialized');
  } catch (error) {
    console.error('[queryPersistence] Failed to setup persistence:', error);
    // App will continue to work without persistence
  }
}

/**
 * Clear persisted query cache (useful for debugging or cache corruption)
 */
export function clearPersistedCache(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
    console.log('[queryPersistence] Cache cleared');
  } catch (error) {
    console.error('[queryPersistence] Error clearing cache:', error);
  }
}

/**
 * Get cache info for debugging
 */
export function getCacheInfo(): {
  exists: boolean;
  size: number;
  compressed: boolean;
} {
  try {
    const compressed = localStorage.getItem(STORAGE_KEY);
    if (!compressed) {
      return { exists: false, size: 0, compressed: false };
    }

    const size = new Blob([compressed]).size;
    return { exists: true, size, compressed: true };
  } catch (error) {
    console.error('[queryPersistence] Error getting cache info:', error);
    return { exists: false, size: 0, compressed: false };
  }
}
