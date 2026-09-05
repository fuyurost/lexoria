<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink } from 'vue-router';
import { useStats } from '@/api/stats';
import { useUiStore } from '@/stores/ui';
import { dueLabel } from '@/lib/format';
import Icon from '@/components/Icon.vue';
import StateBlock from '@/components/StateBlock.vue';
import Tag from '@/components/Tag.vue';

const statsQuery = useStats();
const ui = useUiStore();

const stats = computed(() => statsQuery.data.value);
const empty = computed(() => {
  const s = stats.value;
  return s ? s.words_total === 0 && s.due_today === 0 && s.inbox_open === 0 && s.sources_total === 0 : false;
});

const STATUS_ROWS = computed(() => {
  const s = stats.value;
  if (!s) return [];
  const rows = [
    { key: 'inbox' as const, label: '待处理', tone: 'sky' as const },
    { key: 'active' as const, label: '学习中', tone: 'amber' as const },
    { key: 'known' as const, label: '已认识', tone: 'emerald' as const },
    { key: 'archived' as const, label: '已归档', tone: 'stone' as const },
  ];
  const max = Math.max(1, ...rows.map((r) => s.words_by_status[r.key] ?? 0));
  return rows.map((r) => ({ ...r, count: s.words_by_status[r.key] ?? 0, pct: Math.round(((s.words_by_status[r.key] ?? 0) / max) * 100) }));
});
</script>

<template>
  <div class="space-y-5">
    <StateBlock
      v-if="statsQuery.isPending.value"
      state="loading"
      title="正在加载统计…"
    />
    <StateBlock
      v-else-if="statsQuery.isError.value"
      state="error"
      title="统计加载失败"
      :hint="statsQuery.error.value?.message"
      @retry="void statsQuery.refetch()"
    />
    <template v-else-if="stats">
      <div v-if="empty" class="panel p-8">
        <div class="flex flex-col items-center gap-4 text-center sm:flex-row sm:justify-between sm:text-left">
          <div>
            <h2 class="text-lg font-semibold">欢迎来到 Lexiora</h2>
            <p class="mt-1 max-w-md text-sm text-stone-500 dark:text-stone-400">
              从<b>快速添加</b>捕获一个词开始（Ctrl+Shift+A），收件箱里激活它、补上义项，然后每天回来做几轮复习。
            </p>
          </div>
          <div class="flex gap-2">
            <button type="button" class="btn-primary" @click="ui.quickAddOpen = true">
              <Icon name="plus" :size="14" />快速添加
            </button>
            <RouterLink to="/sources" class="btn-ghost">先建来源</RouterLink>
          </div>
        </div>
      </div>

      <div v-else class="grid grid-cols-2 gap-3 md:grid-cols-4">
        <RouterLink to="/review" class="panel p-4 transition-shadow hover:shadow-md">
          <div class="flex items-center justify-between">
            <span class="microlabel">今日待复习</span>
            <Icon name="repeat" :size="15" class="text-stone-400" />
          </div>
          <p class="mt-2 text-3xl font-bold tabular-nums" :class="stats.due_today > 0 ? 'text-orange-600 dark:text-orange-400' : ''">
            {{ stats.due_today }}
          </p>
          <p class="mt-1 text-xs text-stone-500 dark:text-stone-400">
            {{ stats.due_today > 0 ? '现在开始 →' : '今日已完成 ✅' }}
          </p>
        </RouterLink>

        <div class="panel p-4">
          <div class="flex items-center justify-between">
            <span class="microlabel">今日已复习</span>
            <Icon name="check" :size="15" class="text-emerald-500" />
          </div>
          <p class="mt-2 text-3xl font-bold tabular-nums">{{ stats.reviewed_today }}</p>
          <p class="mt-1 text-xs text-stone-500 dark:text-stone-400">
            连续打卡 <b class="tabular-nums">{{ stats.streak_days }}</b> 天
          </p>
        </div>

        <RouterLink to="/inbox" class="panel p-4 transition-shadow hover:shadow-md">
          <div class="flex items-center justify-between">
            <span class="microlabel">收件箱待处理</span>
            <Icon name="inbox" :size="15" class="text-stone-400" />
          </div>
          <p class="mt-2 text-3xl font-bold tabular-nums">{{ stats.inbox_open }}</p>
          <p class="mt-1 text-xs text-stone-500 dark:text-stone-400">去激活新词 →</p>
        </RouterLink>

        <div class="panel p-4">
          <div class="flex items-center justify-between">
            <span class="microlabel">词库总量</span>
            <Icon name="book" :size="15" class="text-stone-400" />
          </div>
          <p class="mt-2 text-3xl font-bold tabular-nums">{{ stats.words_total }}</p>
          <p class="mt-1 text-xs text-stone-500 dark:text-stone-400">{{ stats.sources_total }} 个来源</p>
        </div>
      </div>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="panel p-4">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="microlabel">词库构成</h3>
            <RouterLink to="/words" class="link text-xs">全部词条</RouterLink>
          </div>
          <div v-if="stats.words_total === 0" class="py-6 text-center text-sm text-stone-400">词库还是空的</div>
          <ul v-else class="space-y-2">
            <li v-for="row in STATUS_ROWS" :key="row.key" class="flex items-center gap-2 text-sm">
              <Tag :label="row.label" :tone="row.tone" dot />
              <span class="w-14 text-right font-mono text-[13px] tabular-nums">{{ row.count }}</span>
              <span class="h-1.5 flex-1 overflow-hidden rounded-full bg-stone-100 dark:bg-stone-800">
                <span class="block h-full rounded-full" :class="{ 'bg-sky-400': row.key === 'inbox', 'bg-amber-400': row.key === 'active', 'bg-emerald-400': row.key === 'known', 'bg-stone-300 dark:bg-stone-600': row.key === 'archived' }" :style="{ width: `${row.pct}%` }" />
              </span>
            </li>
          </ul>
        </section>

        <section class="panel p-4">
          <h3 class="microlabel mb-3">今日行动</h3>
          <ul class="divide-y divide-stone-100 dark:divide-stone-800">
            <li v-if="stats.due_today > 0">
              <RouterLink to="/review" class="flex items-center gap-3 py-2.5 hover:text-orange-700 dark:hover:text-orange-400">
                <span class="flex h-8 w-8 items-center justify-center rounded-md bg-orange-100 text-orange-700 dark:bg-orange-950/60 dark:text-orange-300"><Icon name="repeat" :size="15" /></span>
                <span class="flex-1 text-sm">开始今天的复习</span>
                <span class="text-xs text-stone-400">{{ stats.due_today }} 张卡片</span>
              </RouterLink>
            </li>
            <li v-else class="py-2.5 text-sm text-stone-400">今日没有到期的卡片，去休息或捕获新词吧。</li>
            <li v-if="stats.inbox_open > 0">
              <RouterLink to="/inbox" class="flex items-center gap-3 py-2.5 hover:text-orange-700 dark:hover:text-orange-400">
                <span class="flex h-8 w-8 items-center justify-center rounded-md bg-sky-100 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300"><Icon name="inbox" :size="15" /></span>
                <span class="flex-1 text-sm">整理收件箱</span>
                <span class="text-xs text-stone-400">{{ stats.inbox_open }} 条待处理</span>
              </RouterLink>
            </li>
            <li>
              <button type="button" class="flex w-full items-center gap-3 py-2.5 text-left hover:text-orange-700 dark:hover:text-orange-400" @click="ui.quickAddOpen = true">
                <span class="flex h-8 w-8 items-center justify-center rounded-md bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"><Icon name="plus" :size="15" /></span>
                <span class="flex-1 text-sm">捕获一个新词</span>
                <span class="kbd">Ctrl⇧A</span>
              </button>
            </li>
            <li>
              <RouterLink to="/daily-sheets" class="flex items-center gap-3 py-2.5 hover:text-orange-700 dark:hover:text-orange-400">
                <span class="flex h-8 w-8 items-center justify-center rounded-md bg-violet-100 text-violet-700 dark:bg-violet-950/60 dark:text-violet-300"><Icon name="file" :size="15" /></span>
                <span class="flex-1 text-sm">生成今日练习纸</span>
                <Icon name="arrow-right" :size="14" class="text-stone-400" />
              </RouterLink>
            </li>
          </ul>
        </section>
      </div>
    </template>
  </div>
</template>
