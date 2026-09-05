import { QueryClient } from '@tanstack/vue-query';

/**
 * App-wide QueryClient. Server state lives exclusively in TanStack Query
 * (except the current user, which is client state in the auth store).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 20_000,
      gcTime: 5 * 60_000,
    },
  },
});

/** Stable query-key prefixes (invalidation targets). */
export const QK = {
  settings: ['settings'] as const,
  sources: ['sources'] as const,
  stats: ['stats'] as const,
  words: ['words'] as const,
  word: (id: string) => ['word', id] as const,
  wordEncounters: (id: string) => ['word-encounters', id] as const,
  inbox: ['inbox'] as const,
  reviewQueue: ['review-queue'] as const,
  sheets: ['daily-sheets'] as const,
  sheet: (id: string) => ['daily-sheet', id] as const,
};

export type QueryClientLike = {
  invalidateQueries: (opts: { queryKey: readonly unknown[] | string }) => Promise<void>;
};
