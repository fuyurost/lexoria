import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query';
import type { DailySheetConfig, SheetColumns, SheetTemplate, PaperSize } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { QK } from './common';

export const sheetTemplates: Array<{ value: SheetTemplate; label: string; hint: string }> = [
  { value: 'compact', label: 'Compact', hint: '词条回顾表（词 → 释义）' },
  { value: 'test', label: 'Test', hint: '测试填空表（释义 → 默写）' },
];

export const paperSizes: Array<{ value: PaperSize; label: string }> = [
  { value: 'a4', label: 'A4' },
  { value: 'a5', label: 'A5' },
];

export const columnOptions: Array<{ value: SheetColumns; label: string }> = [
  { value: 1, label: '单栏' },
  { value: 2, label: '双栏' },
];

export interface SheetConfigDraft {
  template: SheetTemplate;
  paper_size: PaperSize;
  columns: SheetColumns;
  review_count: number;
  new_count: number;
  source_ids: string[];
}

export const sheetBounds = { min: 0, max: 100 } as const;

export function toSheetConfig(draft: SheetConfigDraft): DailySheetConfig {
  return {
    template: draft.template,
    paper_size: draft.paper_size,
    columns: draft.columns,
    review_count: draft.review_count,
    new_count: draft.new_count,
    source_ids: draft.source_ids,
  };
}

/** Pure validation → error list (unit-testable, drives the form UI). */
export function validateSheetDraft(draft: SheetConfigDraft): string[] {
  const errors: string[] = [];
  if (draft.template !== 'compact' && draft.template !== 'test') errors.push('模板必须是 compact 或 test');
  if (draft.paper_size !== 'a4' && draft.paper_size !== 'a5') errors.push('纸张必须是 A4 或 A5');
  if (draft.columns !== 1 && draft.columns !== 2) errors.push('栏数必须是 1 或 2');
  const clamp = (n: number) => (Number.isFinite(n) ? Math.trunc(n) : 0);
  if (!Number.isInteger(draft.review_count) || !Number.isInteger(draft.new_count)) errors.push('数量必须是整数');
  else {
    if (draft.review_count < sheetBounds.min || draft.review_count > sheetBounds.max) errors.push(`复习词数需在 ${sheetBounds.min}–${sheetBounds.max} 之间`);
    if (draft.new_count < sheetBounds.min || draft.new_count > sheetBounds.max) errors.push(`新词数需在 ${sheetBounds.min}–${sheetBounds.max} 之间`);
  }
  if (clamp(draft.review_count) + clamp(draft.new_count) < 1) errors.push('至少选择 1 个词（复习 + 新词）');
  return errors;
}

/** Clamp user-typed counts into the allowed range (pure). */
export function clampCount(n: number): number {
  if (!Number.isFinite(n)) return 0;
  const t = Math.trunc(n);
  return Math.min(sheetBounds.max, Math.max(sheetBounds.min, t));
}

export function useDailySheets() {
  return useQuery({
    queryKey: QK.sheets,
    queryFn: () => api.dailySheets.list(),
    staleTime: 30_000,
  });
}

export function useDailySheet(id: string) {
  return useQuery({
    queryKey: QK.sheet(id),
    queryFn: () => api.dailySheets.get(id),
    enabled: id.length > 0,
  });
}

export function usePreviewSheet() {
  return useMutation({
    mutationFn: (draft: SheetConfigDraft) => api.dailySheets.preview(toSheetConfig(draft)),
  });
}

export function useCreateSheet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (draft: SheetConfigDraft) => api.dailySheets.create(toSheetConfig(draft)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: QK.sheets });
      void qc.invalidateQueries({ queryKey: QK.stats });
    },
  });
}
