import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import type { Familiarity, UserWord, UserWordPatch, WordSort, WordStatus } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { QK } from './common';

export interface WordTableFilters {
  q: string;
  status: WordStatus | '';
  sourceId: string | '';
  familiarity: number | '';
  sort: WordSort;
  page: number;
  pageSize: number;
}

export const defaultWordFilters = (): WordTableFilters => ({
  q: '',
  status: '',
  sourceId: '',
  familiarity: '',
  sort: 'created_at:desc',
  page: 1,
  pageSize: 20,
});

export function useWordPage(filters: WordTableFilters) {
  return useQuery({
    queryKey: [QK.words, filters],
    queryFn: () =>
      api.words.list({
        q: filters.q || undefined,
        status: filters.status || undefined,
        source_id: filters.sourceId || undefined,
        familiarity: filters.familiarity === '' ? undefined : (filters.familiarity as Familiarity),
        page: filters.page,
        page_size: filters.pageSize,
        sort: filters.sort,
      }),
  });
}

export function useWord(id: string) {
  return useQuery({
    queryKey: QK.word(id),
    queryFn: () => api.words.get(id),
    enabled: id.length > 0,
  });
}

export function useWordEncounters(id: string) {
  return useQuery({
    queryKey: QK.wordEncounters(id),
    queryFn: () => api.encounters.forWord(id),
    enabled: id.length > 0,
  });
}

function invalidateWordNeighbors(qc: ReturnType<typeof useQueryClient>): void {
  void qc.invalidateQueries({ queryKey: QK.words });
  void qc.invalidateQueries({ queryKey: QK.stats });
  void qc.invalidateQueries({ queryKey: QK.reviewQueue });
  void qc.invalidateQueries({ queryKey: QK.inbox });
}

/** Shared status transition (inbox activate / known / archive, library edits). */
export function useUpdateWord() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: UserWordPatch }) => api.words.update(id, patch),
    onSuccess: (updated, { id }) => {
      qc.setQueryData<UserWord>(QK.word(id), updated);
      invalidateWordNeighbors(qc);
    },
  });
}

export function useDeleteSense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ senseId, wordId }: { senseId: string; wordId: string }) => api.senses.remove(senseId),
    onSuccess: (_v, { wordId }) => {
      void qc.invalidateQueries({ queryKey: QK.word(wordId) });
    },
  });
}

export function useCreateSense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ wordId, body }: { wordId: string; body: Parameters<typeof api.senses.create>[1] }) =>
      api.senses.create(wordId, body),
    onSuccess: (_v, { wordId }) => {
      void qc.invalidateQueries({ queryKey: QK.word(wordId) });
    },
  });
}

export function useUpdateSense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ senseId, wordId, patch }: { senseId: string; wordId: string; patch: Parameters<typeof api.senses.update>[1] }) =>
      api.senses.update(senseId, patch),
    onSuccess: (_v, { wordId }) => {
      void qc.invalidateQueries({ queryKey: QK.word(wordId) });
    },
  });
}

export { QK };
