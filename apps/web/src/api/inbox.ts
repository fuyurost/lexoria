import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import type { WordStatus } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { QK } from './common';

export type InboxTab = 'all' | WordStatus;

export interface InboxFilters {
  tab: InboxTab;
  q: string;
  page: number;
  pageSize: number;
}

export const inboxTabs: Array<{ value: InboxTab; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'inbox', label: '待处理' },
  { value: 'active', label: '学习中' },
  { value: 'known', label: '已认识' },
  { value: 'archived', label: '已归档' },
];

/** Inbox rows ARE user-words; list through GET /inbox with an optional status. */
export function useInboxPage(filters: InboxFilters) {
  return useQuery({
    queryKey: [QK.inbox, filters],
    queryFn: () =>
      api.inbox.list({
        q: filters.q || undefined,
        status: filters.tab === 'all' ? undefined : filters.tab,
        page: filters.page,
        page_size: filters.pageSize,
      }),
  });
}

/** Capture → POST /inbox (the only way new words enter the system). */
export function useCreateInboxItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof api.inbox.create>[0]) => api.inbox.create(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QK.inbox });
      void qc.invalidateQueries({ queryKey: QK.words });
      void qc.invalidateQueries({ queryKey: QK.stats });
    },
  });
}
