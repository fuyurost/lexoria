import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import type { Source, SourceCreate, SourcePatch } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { QK } from './common';

export function useSources(includeArchived = false) {
  return useQuery({
    queryKey: [QK.sources, includeArchived ? 'all' : 'active'],
    queryFn: async () => {
      const all = await api.sources.list();
      return includeArchived ? all : all.filter((s) => !s.archived_at);
    },
  });
}

export function useCreateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SourceCreate) => api.sources.create(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QK.sources });
    },
  });
}

export function useUpdateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: SourcePatch }) => api.sources.update(id, patch),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QK.sources });
      void qc.invalidateQueries({ queryKey: QK.words });
    },
  });
}

export type { Source };
