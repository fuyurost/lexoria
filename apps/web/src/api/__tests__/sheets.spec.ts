import { describe, expect, it } from 'vitest';
import { clampCount, toSheetConfig, validateSheetDraft, type SheetConfigDraft } from '@/api/sheets';

function draft(overrides: Partial<SheetConfigDraft> = {}): SheetConfigDraft {
  return {
    template: 'compact',
    paper_size: 'a4',
    columns: 2,
    review_count: 20,
    new_count: 10,
    source_ids: ['s1'],
    ...overrides,
  };
}

describe('daily sheet option limits (纯函数)', () => {
  it('只接受 compact / test 模板、a4 / a5 纸张、1 / 2 栏', () => {
    expect(validateSheetDraft(draft())).toEqual([]);
    expect(validateSheetDraft(draft({ template: 'test' }))).toEqual([]);
    expect(validateSheetDraft(draft({ paper_size: 'a5', columns: 1 }))).toEqual([]);

    expect(validateSheetDraft(draft({ template: 'weird' as never }))).toContain('模板必须是 compact 或 test');
    expect(validateSheetDraft(draft({ paper_size: 'letter' as never }))).toContain('纸张必须是 A4 或 A5');
    expect(validateSheetDraft(draft({ columns: 3 as never }))).toContain('栏数必须是 1 或 2');
  });

  it('数量约束：0–100 整数，且复习 + 新词至少 1', () => {
    expect(validateSheetDraft(draft({ review_count: 0, new_count: 0 }))).toContain('至少选择 1 个词（复习 + 新词）');
    expect(validateSheetDraft(draft({ review_count: -1 }))).toContain('复习词数需在 0–100 之间');
    expect(validateSheetDraft(draft({ new_count: 101 }))).toContain('新词数需在 0–100 之间');
    expect(validateSheetDraft(draft({ review_count: 2.5 }))).toContain('数量必须是整数');
  });

  it('clampCount 将任意输入收敛到 [0,100] 整数', () => {
    expect(clampCount(150)).toBe(100);
    expect(clampCount(-3)).toBe(0);
    expect(clampCount(12.9)).toBe(12);
    expect(clampCount(Number.NaN)).toBe(0);
    expect(clampCount(42)).toBe(42);
  });

  it('toSheetConfig 严格透传配置', () => {
    const d = draft({ template: 'test', paper_size: 'a5', columns: 1, review_count: 8, new_count: 3 });
    expect(toSheetConfig(d)).toEqual({
      template: 'test',
      paper_size: 'a5',
      columns: 1,
      review_count: 8,
      new_count: 3,
      source_ids: ['s1'],
    });
  });
});
