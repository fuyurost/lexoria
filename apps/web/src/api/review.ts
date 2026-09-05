import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import type { ReviewRating, ReviewSubmission } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { QK } from './common';

/** Today's review queue. staleTime 0 — the queue must reflect submissions. */
export function useTodayQueue() {
  return useQuery({
    queryKey: QK.reviewQueue,
    queryFn: () => api.reviews.today(),
    staleTime: 0,
  });
}

export function useSubmitReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ cardId, body }: { cardId: string; body: ReviewSubmission }) => api.reviews.submit(cardId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QK.reviewQueue });
      void qc.invalidateQueries({ queryKey: QK.stats });
      void qc.invalidateQueries({ queryKey: QK.words });
    },
    onError: () => {
      // 409 version conflicts are handled by the review screen (refresh card);
      // other errors surface through the shared error path there.
    },
  });
}

export const ratingLabels: Record<ReviewRating, string> = {
  again: '重来',
  hard: '困难',
  good: '良好',
  easy: '简单',
};

export const ratingKeys: Record<ReviewRating, string> = {
  again: '1',
  hard: '2',
  good: '3',
  easy: '4',
};
