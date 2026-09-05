import { useQuery } from '@tanstack/vue-query';
import { api } from '@/lib/api';
import { QK } from './common';

export function useStats() {
  return useQuery({
    queryKey: QK.stats,
    queryFn: () => api.stats.get(),
  });
}
