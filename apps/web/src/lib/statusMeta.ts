import type { CardInfo, SourceType, WordStatus } from '@lexoria/api-client';

export type Tone = 'sky' | 'amber' | 'emerald' | 'stone' | 'red' | 'orange' | 'violet';

export interface ToneStyle {
  dot: string;
  chip: string;
}

export const TONE_STYLES: Record<Tone, ToneStyle> = {
  sky: {
    dot: 'bg-sky-500',
    chip: 'bg-sky-50 text-sky-700 ring-sky-600/20 dark:bg-sky-950/50 dark:text-sky-300 dark:ring-sky-400/20',
  },
  amber: {
    dot: 'bg-amber-500',
    chip: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-950/50 dark:text-amber-300 dark:ring-amber-400/20',
  },
  emerald: {
    dot: 'bg-emerald-500',
    chip: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-400/20',
  },
  stone: {
    dot: 'bg-stone-400',
    chip: 'bg-stone-100 text-stone-600 ring-stone-500/20 dark:bg-stone-800 dark:text-stone-300 dark:ring-stone-400/20',
  },
  red: {
    dot: 'bg-red-500',
    chip: 'bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-950/50 dark:text-red-300 dark:ring-red-400/20',
  },
  orange: {
    dot: 'bg-orange-500',
    chip: 'bg-orange-50 text-orange-700 ring-orange-600/20 dark:bg-orange-950/50 dark:text-orange-300 dark:ring-orange-400/20',
  },
  violet: {
    dot: 'bg-violet-500',
    chip: 'bg-violet-50 text-violet-700 ring-violet-600/20 dark:bg-violet-950/50 dark:text-violet-300 dark:ring-violet-400/20',
  },
};

export function wordStatusMeta(status: WordStatus): { label: string; tone: Tone } {
  switch (status) {
    case 'inbox':
      return { label: '待处理', tone: 'sky' };
    case 'active':
      return { label: '学习中', tone: 'amber' };
    case 'known':
      return { label: '已认识', tone: 'emerald' };
    case 'archived':
      return { label: '已归档', tone: 'stone' };
  }
}

export const SOURCE_TYPE_OPTIONS: Array<{ value: SourceType | ''; label: string }> = [
  { value: '', label: '未分类' },
  { value: 'school', label: '课本' },
  { value: 'ielts', label: '雅思' },
  { value: 'cet4', label: '四级' },
  { value: 'exam', label: '考试' },
  { value: 'reading', label: '阅读材料' },
  { value: 'manual', label: '手动录入' },
  { value: 'other', label: '其他' },
];

export function sourceTypeLabel(type: SourceType | null): string {
  return SOURCE_TYPE_OPTIONS.find((o) => o.value === type)?.label ?? '未分类';
}

export function sourceTypeTone(type: SourceType | null): Tone {
  switch (type) {
    case 'school':
    case 'exam':
      return 'sky';
    case 'ielts':
    case 'cet4':
      return 'violet';
    case 'reading':
      return 'emerald';
    default:
      return 'stone';
  }
}

/** Card lifecycle label derived from the approved CardInfo fields. */
export function cardStage(card: CardInfo): { label: string; tone: Tone } {
  if (card.suspended_at) return { label: '已挂起', tone: 'stone' };
  if (card.review_count === 0) return { label: '新卡', tone: 'violet' };
  if (card.due_at && new Date(card.due_at).getTime() <= Date.now()) return { label: '到期复习', tone: 'amber' };
  return { label: '复习中', tone: 'violet' };
}
