import { describe, expect, it, vi, beforeEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import type { LexoriaApi } from '@lexoria/api-client';

vi.mock('@/lib/api', () => ({
  api: {
    inbox: { create: vi.fn() },
  } as unknown as LexoriaApi,
}));

import { api } from '@/lib/api';
import QuickAddDialog from '@/components/QuickAddDialog.vue';

const inboxCreate = vi.mocked(api.inbox.create);

/** Modal renders through <Teleport to="body"> — query the live DOM. */
function input(): HTMLInputElement {
  const el = document.querySelector<HTMLInputElement>('#quick-word');
  if (!el) throw new Error('quick-word input not found in document');
  return el;
}

function submitForm(): void {
  const form = document.querySelector<HTMLFormElement>('#quick-word')?.closest('form');
  if (!form) throw new Error('quick add form not found');
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}

async function settle(): Promise<void> {
  await flushPromises();
  await new Promise((r) => setTimeout(r, 0));
}

async function mountDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mount(QuickAddDialog, {
    props: { open: true, sources: [] },
    attachTo: document.body,
    global: { plugins: [[VueQueryPlugin, { queryClient: qc }]] },
  });
  await settle();
}

function created(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'w9',
    word_id: 'dw9',
    lemma: 'serendipity',
    normalized_lemma: 'serendipity',
    personal_phonetic: null,
    status: 'inbox',
    familiarity: null,
    note: null,
    card: null,
    senses: [],
    first_seen_at: new Date().toISOString(),
    last_seen_at: null,
    encounter_count: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    user_word_created: true,
    replayed: false,
    ...overrides,
  };
}

describe('QuickAddDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    inboxCreate.mockResolvedValue(created() as never);
  });

  it('Enter 提交：直接 POST /inbox（无预查询），unclassified 类型 + client_event_id，清空并保留焦点', async () => {
    await mountDialog();
    expect(input()).toBe(document.activeElement); // 打开即自动聚焦

    input().value = 'serendipity';
    input().dispatchEvent(new Event('input', { bubbles: true }));
    submitForm();
    await settle();

    // 不做任何查重请求，只有一次捕获。
    expect(inboxCreate).toHaveBeenCalledTimes(1);
    const createArg = inboxCreate.mock.calls[0]?.[0];
    expect(createArg).toMatchObject({
      text: 'serendipity',
      source_id: null,
      encounter_type: 'unclassified',
    });
    expect(createArg?.client_event_id).toMatch(/^[0-9a-f-]{36}$/);

    expect(input().value).toBe(''); // 输入框清空
    expect(document.activeElement).toBe(input()); // 焦点保留
    expect(document.body.textContent ?? '').toContain('新建捕获');

    // 可连续添加
    input().value = 'ephemeral';
    input().dispatchEvent(new Event('input', { bubbles: true }));
    submitForm();
    await settle();
    expect(inboxCreate).toHaveBeenCalledTimes(2);
  });

  it('user_word_created=false → 显示「重复捕获」且仍只 POST 一次', async () => {
    inboxCreate.mockResolvedValue(created({ user_word_created: false, replayed: false, lemma: 'serendipity' }) as never);
    await mountDialog();
    input().value = 'serendipity';
    input().dispatchEvent(new Event('input', { bubbles: true }));
    submitForm();
    await settle();

    expect(inboxCreate).toHaveBeenCalledTimes(1);
    expect(inboxCreate.mock.calls[0]?.[0]?.encounter_type).toBe('unclassified');
    expect(document.body.textContent ?? '').toContain('重复捕获');
  });

  it('空输入不提交', async () => {
    await mountDialog();
    submitForm();
    await settle();
    expect(inboxCreate).not.toHaveBeenCalled();
  });
});
