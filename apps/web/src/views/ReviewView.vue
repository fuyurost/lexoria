<script setup lang="ts">
/**
 * 复习：prompt → reveal（Space/Enter）→ 1-4 评分（Again/Hard/Good/Easy）→ 下一张。
 * 会话内持有一份本地快照（队头弹出），避免与后台自动刷新互相错位；
 * 409 版本冲突时给出「载入最新 / 跳过此卡」处理。
 */
import { computed, onBeforeUnmount, onMounted, ref, watchEffect } from 'vue';
import { useRouter } from 'vue-router';
import { codeOf, messageOf, newClientEventId, type ReviewCard, type ReviewRating } from '@lexoria/api-client';
import { ratingKeys, ratingLabels, useSubmitReview, useTodayQueue } from '@/api/review';
import { cardStage, wordStatusMeta } from '@/lib/statusMeta';
import { useUiStore } from '@/stores/ui';
import { toastError } from '@/lib/toast';
import Icon from '@/components/Icon.vue';
import StateBlock from '@/components/StateBlock.vue';
import Tag from '@/components/Tag.vue';

const router = useRouter();
const ui = useUiStore();

const queueQuery = useTodayQueue();
const submitReview = useSubmitReview();

/** Cards still pending in this session (head = current card). */
const session = ref<ReviewCard[] | null>(null);
const startedTotal = ref(0);
const done = ref(false);
const revealed = ref(false);
const busy = ref(false);
const skipped = ref(0);
const conflict = ref<{ cardId: string; userWordId: string; expected: number; actual: number } | null>(null);

// Snapshot the fresh server queue exactly once per session.
watchEffect(() => {
  const data = queueQuery.data.value;
  if (data && data.items.length > 0 && !session.value && !done.value) {
    session.value = [...data.items];
    startedTotal.value = data.total > 0 ? data.total : data.items.length;
  }
});

const current = computed<ReviewCard | null>(() => session.value?.[0] ?? null);
const completed = computed(() => startedTotal.value > 0 ? startedTotal.value - (session.value?.length ?? 0) : 0);
const progressPct = computed(() =>
  startedTotal.value === 0 ? 0 : Math.min(100, Math.round((completed.value / startedTotal.value) * 100)),
);

const RATING_TONES: Record<ReviewRating, { btn: string; hint: string }> = {
  again: { btn: 'bg-red-500 text-white hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-500', hint: '忘记或几乎不会' },
  hard: { btn: 'bg-amber-500 text-white hover:bg-amber-600 dark:bg-amber-600 dark:hover:bg-amber-500', hint: '想了一会儿才想起' },
  good: { btn: 'bg-emerald-500 text-white hover:bg-emerald-600 dark:bg-emerald-600 dark:hover:bg-emerald-500', hint: '比较顺畅' },
  easy: { btn: 'bg-sky-500 text-white hover:bg-sky-600 dark:bg-sky-600 dark:hover:bg-sky-500', hint: '非常轻松' },
};

function reveal(): void {
  if (current.value && !revealed.value && !busy.value && !conflict.value) revealed.value = true;
}

async function rate(rating: ReviewRating): Promise<void> {
  const card = current.value;
  if (!card || !revealed.value || busy.value || conflict.value) return;
  busy.value = true;
  try {
    // review-cards/:id targets the NESTED card id — NOT the aggregation id.
    await submitReview.mutateAsync({
      cardId: card.card.id,
      body: { rating, client_event_id: newClientEventId(), expected_card_version: card.card.version },
    });
    advance();
  } catch (err) {
    if (codeOf(err) === 'version_conflict') {
      const details = err instanceof Error && 'details' in err ? ((err as { details?: unknown }).details as Record<string, unknown> | null) : null;
      conflict.value = {
        cardId: card.card.id,
        userWordId: card.id,
        expected: typeof details?.expected === 'number' ? details.expected : card.card.version,
        actual: typeof details?.actual === 'number' ? details.actual : -1,
      };
    } else {
      toastError(messageOf(err));
    }
  } finally {
    busy.value = false;
  }
}

function advance(): void {
  revealed.value = false;
  if (!session.value) return;
  session.value = session.value.slice(1);
  if (session.value.length === 0) done.value = true;
}

function skipConflicted(): void {
  const userWordId = conflict.value?.userWordId;
  conflict.value = null;
  revealed.value = false;
  skipped.value += 1;
  if (!userWordId || !session.value) {
    if (session.value?.length === 0) done.value = true;
    return;
  }
  // Session items share the aggregation key = user_word_id.
  session.value = session.value.filter((c) => c.id !== userWordId);
  if (session.value.length === 0) done.value = true;
}

async function reloadQueue(): Promise<void> {
  conflict.value = null;
  await queueQuery.refetch();
  if (queueQuery.data.value && queueQuery.data.value.items.length === 0) {
    session.value = [];
    done.value = true;
  } else {
    session.value = queueQuery.data.value ? [...queueQuery.data.value.items] : [];
    startedTotal.value = queueQuery.data.value?.total ?? session.value.length;
  }
  revealed.value = false;
}

async function startNextSession(): Promise<void> {
  await queueQuery.refetch();
  if (queueQuery.data.value && queueQuery.data.value.items.length > 0) {
    session.value = [...queueQuery.data.value.items];
    startedTotal.value = queueQuery.data.value.total;
    done.value = false;
    revealed.value = false;
  }
}

function onKey(e: KeyboardEvent): void {
  if (!current.value || conflict.value) return;
  if ((e.key === ' ' || e.key === 'Enter') && !revealed.value) {
    e.preventDefault();
    reveal();
    return;
  }
  if (!revealed.value || busy.value) return;
  const map: Record<string, ReviewRating> = { '1': 'again', '2': 'hard', '3': 'good', '4': 'easy' };
  const rating = map[e.key];
  if (rating) {
    e.preventDefault();
    void rate(rating);
  }
}

onMounted(() => window.addEventListener('keydown', onKey));
onBeforeUnmount(() => window.removeEventListener('keydown', onKey));
</script>

<template>
  <div class="mx-auto max-w-2xl">
    <div v-if="queueQuery.isPending.value" class="panel"><StateBlock state="loading" title="正在准备今天的卡片…" /></div>
    <div v-else-if="queueQuery.isError.value" class="panel">
      <StateBlock state="error" title="复习队列加载失败" :hint="queueQuery.error.value?.message" @retry="void queueQuery.refetch()" />
    </div>

    <template v-else>
      <!-- 无卡片 -->
      <div v-if="queueQuery.data.value && queueQuery.data.value.items.length === 0 && !session" class="panel">
        <StateBlock state="empty" title="今日没有到期的卡片" hint="所有卡片都复习完了，去捕获几个新词，或做一张练习纸吧。">
          <div class="flex justify-center gap-2">
            <button type="button" class="btn-primary" @click="ui.quickAddOpen = true">
              <Icon name="plus" :size="14" />快速添加
            </button>
            <button type="button" class="btn-ghost" @click="router.push('/dashboard')">返回仪表盘</button>
          </div>
        </StateBlock>
      </div>

      <!-- 完成页 -->
      <div v-else-if="done" class="panel p-8">
        <div class="flex flex-col items-center gap-4 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
            <Icon name="check" :size="26" />
          </span>
          <div>
            <h2 class="text-lg font-semibold">今日复习完成！</h2>
            <p class="mt-1 text-sm text-stone-500 dark:text-stone-400">
              完成 {{ startedTotal - skipped }} 张<span v-if="skipped">（跳过冲突 {{ skipped }} 张）</span>
            </p>
          </div>
          <div class="flex gap-2">
            <button type="button" class="btn-primary" @click="router.push('/dashboard')">返回仪表盘</button>
            <button type="button" class="btn-ghost" @click="startNextSession">看看还有没有新卡</button>
          </div>
        </div>
      </div>

      <div v-else-if="current" class="space-y-3">
        <!-- 进度 -->
        <div class="flex items-center gap-3">
          <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-800">
            <div class="h-full rounded-full bg-orange-500 transition-all" :style="{ width: `${progressPct}%` }" />
          </div>
          <span class="text-xs text-stone-500 tabular-nums dark:text-stone-400">{{ completed + 1 }} / {{ startedTotal }}</span>
          <button type="button" class="btn-ghost btn-sm" title="结束本次复习" @click="router.push('/dashboard')">
            <Icon name="x" :size="13" />退出
          </button>
        </div>

        <div v-if="conflict" class="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200">
          <p class="flex items-center gap-1.5 font-medium">
            <Icon name="alert" :size="14" />版本冲突：这张卡片已被更新
          </p>
          <p class="mt-1 text-[13px] opacity-80">
            你看到的是 v{{ conflict.expected }}，服务端已是 v{{ conflict.actual }} —— 载入最新状态后重新作答，或先跳过这张。
          </p>
          <div class="mt-2 flex gap-2">
            <button type="button" class="btn-danger btn-sm" @click="reloadQueue">载入最新卡片</button>
            <button type="button" class="btn-ghost btn-sm" @click="skipConflicted">跳过此卡</button>
          </div>
        </div>

        <!-- 卡片主体 -->
        <div class="panel overflow-hidden">
          <div class="flex items-center justify-between border-b border-stone-200 px-4 py-2 dark:border-stone-800">
            <Tag :label="`${cardStage(current.card).label} · v${current.card.version}`" :tone="cardStage(current.card).tone" dot />
            <span class="text-xs text-stone-400 dark:text-stone-500">{{ wordStatusMeta(current.status).label }}</span>
          </div>

          <template v-if="!revealed">
            <div class="flex min-h-52 flex-col items-center justify-center gap-4 px-6 py-10 text-center">
              <p class="text-3xl font-bold tracking-tight">{{ current.lemma }}</p>
              <p v-if="current.personal_phonetic" class="font-mono text-sm text-stone-400 dark:text-stone-500">/{{ current.personal_phonetic }}/</p>
              <p class="text-xs text-stone-400 dark:text-stone-500">想想它的意思……准备好了就翻面</p>
              <button type="button" class="btn-primary" @click="reveal">
                显示答案<span class="kbd !border-white/30 !bg-white/15 !text-white/80">Space</span>
              </button>
            </div>
          </template>

          <div v-else class="min-h-52 space-y-4 px-6 py-6">
            <div class="text-center">
              <p class="text-3xl font-bold tracking-tight">{{ current.lemma }}</p>
              <p v-if="current.personal_phonetic" class="mt-1 font-mono text-sm text-stone-500 dark:text-stone-400">/{{ current.personal_phonetic }}/</p>
            </div>

            <div v-if="current.senses.length" class="mx-auto max-w-md space-y-2">
              <p v-for="s in current.senses" :key="s.id" class="text-sm leading-relaxed">
                <span v-if="s.part_of_speech" class="mr-1.5 font-mono text-[12px] text-violet-600 italic dark:text-violet-300">{{ s.part_of_speech }}</span>
                <span v-if="s.definition_zh">{{ s.definition_zh }}</span>
                <span v-if="s.definition_zh && s.definition_en" class="mx-1 text-stone-300 dark:text-stone-600">·</span>
                <span v-if="s.definition_en" class="text-stone-500 italic dark:text-stone-400">{{ s.definition_en }}</span>
              </p>
            </div>
            <p v-else class="text-center text-sm text-amber-600 dark:text-amber-400">此词还没有义项，去词条页补一下吧。</p>

            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <button
                v-for="r in (['again', 'hard', 'good', 'easy'] as ReviewRating[])"
                :key="r"
                type="button"
                class="btn h-11 flex-col !gap-0 py-1 text-white"
                :class="RATING_TONES[r].btn"
                :disabled="busy"
                @click="rate(r)"
              >
                <span class="flex items-center gap-1 font-semibold">
                  {{ ratingLabels[r] }}
                  <span class="rounded bg-white/25 px-1 text-[10px] leading-4">{{ ratingKeys[r] }}</span>
                </span>
                <span class="text-[10px] font-normal opacity-85">{{ RATING_TONES[r].hint }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
