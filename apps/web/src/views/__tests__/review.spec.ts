import { describe, expect, it, vi, beforeEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';
import { ApiError, type LexoriaApi } from '@lexoria/api-client';

vi.mock('@/lib/api', () => ({
  api: {
    reviews: {
      today: vi.fn(),
      submit: vi.fn(),
    },
    auth: { logout: vi.fn().mockResolvedValue(undefined) },
    me: { get: vi.fn().mockResolvedValue({ id: 'u1', username: 'tester', email: 't@x.io' }) },
    settings: { get: vi.fn().mockResolvedValue({}) },
    sources: { list: vi.fn().mockResolvedValue([]) },
    stats: { get: vi.fn().mockResolvedValue({}) },
    inbox: { list: vi.fn().mockResolvedValue({ items: [], total: 0 }) },
  } as unknown as LexoriaApi,
}));

import { api } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';
import { createPinia, setActivePinia } from 'pinia';
import ReviewView from '@/views/ReviewView.vue';

const todayMock = vi.mocked(api.reviews.today);
const submitMock = vi.mocked(api.reviews.submit);

function card(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'w1', // 聚合顶层 id = user_word_id
    user_word_id: 'w1',
    lemma: 'ephemeral',
    personal_phonetic: 'ɪfem(ə)rəl',
    status: 'active',
    familiarity: 3,
    senses: [
      {
        id: 's1',
        user_word_id: 'w1',
        part_of_speech: 'adj.',
        definition_zh: '短暂的，转瞬即逝的',
        definition_en: 'lasting a very short time',
        sort_order: 1,
        created_at: '2026-09-01T00:00:00Z',
        updated_at: '2026-09-01T00:00:00Z',
      },
    ],
    card: {
      id: 'rc1', // review-cards/:id 使用嵌套 card id
      state: 'review',
      difficulty: 1.5,
      stability_days: 1,
      due_at: null,
      lapse_count: 0,
      review_count: 3,
      last_review_at: null,
      suspended_at: null,
      version: 1,
    },
    ...overrides,
  };
}

async function mountReview() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = mount(ReviewView, {
    attachTo: document.body,
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient: qc }]],
    },
  });
  // Simulate a logged-in user so the review screen renders its session.
  const auth = useAuthStore();
  auth.user = { id: 'u1', username: 'tester', email: 't@x.io', created_at: new Date().toISOString() };
  useUiStore();
  await flushPromises();
  return wrapper;
}

function key(key: string): void {
  window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
}

describe('ReviewView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    todayMock.mockResolvedValue({ items: [card()], total: 1 } as never);
    submitMock.mockResolvedValue({ card: card().card } as never);
  });

  it('prompt → Space 显示答案 → 3 (Good) 提交评分并进入完成页', async () => {
    const wrapper = await mountReview();
    expect(wrapper.text()).toContain('ephemeral');
    expect(wrapper.text()).not.toContain('短暂的');

    key(' '); // reveal
    await flushPromises();
    expect(wrapper.text()).toContain('adj.');
    expect(wrapper.text()).toContain('短暂的，转瞬即逝的');

    key('3'); // good
    await flushPromises();
    expect(submitMock).toHaveBeenCalledTimes(1);
    const [cardId, body] = submitMock.mock.calls[0] ?? [];
    // 提交路径必须是嵌套的 card.id（rc1），而不是聚合顶层 user word id。
    expect(cardId).toBe('rc1');
    expect(cardId).not.toBe('w1');
    expect(body).toMatchObject({ rating: 'good', expected_card_version: 1 });
    expect(body?.client_event_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(wrapper.text()).toContain('今日复习完成');
  });

  it('评分前直接按 1-4 不触发提交', async () => {
    await mountReview();
    key('2');
    await flushPromises();
    expect(submitMock).not.toHaveBeenCalled();
  });

  it('版本冲突(409 version_conflict)：展示冲突面板，跳过此卡可继续', async () => {
    submitMock.mockRejectedValue(
      new ApiError(409, '卡片版本已变化', { code: 'version_conflict', details: { expected: 1, actual: 2 } }),
    );
    const wrapper = await mountReview();
    key(' ');
    await flushPromises();
    key('4');
    await flushPromises();

    expect(wrapper.text()).toContain('版本冲突');
    expect(wrapper.text()).toContain('v1');
    expect(wrapper.text()).toContain('v2');

    // 跳过此卡 → 会话结束进入完成页。
    const skip = [...wrapper.findAll('button')].find((b) => b.text().includes('跳过此卡'));
    expect(skip).toBeTruthy();
    await skip!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('今日复习完成');
  });

  it('无卡片时展示空状态', async () => {
    todayMock.mockResolvedValue({ items: [], total: 0 } as never);
    const wrapper = await mountReview();
    expect(wrapper.text()).toContain('今日没有到期的卡片');
  });
});
