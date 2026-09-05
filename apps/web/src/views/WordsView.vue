<script setup lang="ts">
/**
 * 词库：搜索 / 分页 / status / source / familiarity / 排序。
 * 「/」快捷键聚焦搜索；↑/↓ 选择行、Enter 打开详情。
 * 词行不假设 source 列（来源通过遇词关联，可按来源过滤）。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import type { WordStatus } from '@lexoria/api-client';
import { defaultWordFilters, useWordPage, type WordTableFilters } from '@/api/words';
import { useSources } from '@/api/sources';
import { dueLabel, relativeTime } from '@/lib/format';
import { useNavBus } from '@/lib/navBus';
import { wordStatusMeta } from '@/lib/statusMeta';
import Icon from '@/components/Icon.vue';
import FamiliarityDots from '@/components/FamiliarityDots.vue';
import PaginationBar from '@/components/PaginationBar.vue';
import StateBlock from '@/components/StateBlock.vue';
import Tag from '@/components/Tag.vue';

const router = useRouter();
const { data: sources } = useSources(false);

const filters: WordTableFilters = reactive(defaultWordFilters());
const wordQuery = useWordPage(filters);
const page = computed(() => wordQuery.data.value);

const SORT_OPTIONS: Array<{ value: WordTableFilters['sort']; label: string }> = [
  { value: 'created_at:desc', label: '最近添加' },
  { value: 'created_at:asc', label: '最早添加' },
  { value: 'lemma:asc', label: '字母序' },
  { value: 'familiarity:desc', label: '熟悉度 ↓' },
  { value: 'due:asc', label: '到期优先' },
];

const STATUS_OPTIONS: WordStatus[] = ['inbox', 'active', 'known', 'archived'];

const searchEl = ref<HTMLInputElement | null>(null);
let debounce: number | undefined;
const navBus = useNavBus();

function onSearchInput(e: Event): void {
  window.clearTimeout(debounce);
  const value = (e.target as HTMLInputElement).value;
  debounce = window.setTimeout(() => {
    if (filters.q !== value) filters.q = value;
    filters.page = 1;
  }, 250);
}

watch(
  () => navBus?.searchTick,
  (tick) => {
    if (tick && tick > 0) {
      searchEl.value?.focus();
      searchEl.value?.select();
    }
  },
);

onMounted(() => {
  if (navBus && navBus.searchTick > 0) searchEl.value?.focus();
});
onBeforeUnmount(() => window.clearTimeout(debounce));

// Keyboard row selection.
const rows = computed(() => page.value?.items ?? []);
const selectedId = ref<string | null>(null);
watch(
  rows,
  (r) => {
    if (!r.some((w) => w.id === selectedId.value)) selectedId.value = r[0]?.id ?? null;
  },
  { immediate: true },
);

function onRowKey(e: KeyboardEvent): void {
  const idx = rows.value.findIndex((w) => w.id === selectedId.value);
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    const next = rows.value[Math.min(idx + 1, rows.value.length - 1)];
    if (next) selectedId.value = next.id;
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    const prev = rows.value[Math.max(idx - 1, 0)];
    if (prev) selectedId.value = prev.id;
  } else if (e.key === 'Enter' && selectedId.value) {
    e.preventDefault();
    void router.push(`/words/${selectedId.value}`);
  }
}

function dueTone(dueAt: string | null | undefined): string {
  if (!dueAt) return '';
  const label = dueLabel(dueAt);
  if (label === null) return '';
  return label === '今天' ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';
}
</script>

<template>
  <div class="space-y-3" @keydown="onRowKey">
    <!-- 工具条 -->
    <div class="panel flex flex-wrap items-center gap-2 p-2.5">
      <div class="relative min-w-44 flex-1 sm:max-w-xs">
        <Icon name="search" :size="14" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-stone-400" />
        <input
          ref="searchEl"
          class="field !pl-8"
          placeholder="搜索词条（自动搜索）"
          autocomplete="off"
          spellcheck="false"
          :value="filters.q"
          @input="onSearchInput"
        />
      </div>
      <select v-model="filters.status" class="field-sm w-auto !h-8" aria-label="状态" @change="filters.page = 1">
        <option value="">全部状态</option>
        <option v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ wordStatusMeta(s).label }}</option>
      </select>
      <select v-model="filters.sourceId" class="field-sm w-auto !h-8" aria-label="来源" @change="filters.page = 1">
        <option value="">全部来源</option>
        <option v-for="s in sources ?? []" :key="s.id" :value="s.id">{{ s.name }}</option>
      </select>
      <select v-model="filters.familiarity" class="field-sm w-auto !h-8" aria-label="熟悉度" @change="filters.page = 1">
        <option value="">全部熟悉度</option>
        <option v-for="n in 5" :key="n" :value="n">{{ n }} ★</option>
      </select>
      <select v-model="filters.sort" class="field-sm w-auto !h-8" aria-label="排序">
        <option v-for="o in SORT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <span class="ml-auto hidden text-xs text-stone-400 sm:block">{{ page?.total ?? 0 }} 条</span>
    </div>

    <div v-if="wordQuery.isPending.value" class="panel">
      <StateBlock state="loading" title="正在加载词库…" />
    </div>
    <div v-else-if="wordQuery.isError.value" class="panel">
      <StateBlock state="error" title="词库加载失败" :hint="wordQuery.error.value?.message" @retry="void wordQuery.refetch()" />
    </div>
    <div v-else-if="!page || page.items.length === 0" class="panel">
      <StateBlock
        state="empty"
        :title="filters.q || filters.status || filters.sourceId || filters.familiarity ? '没有符合条件的词条' : '词库还是空的'"
        :hint="filters.q || filters.status || filters.sourceId || filters.familiarity ? '调整筛选条件或清空搜索试试。' : '用 Ctrl+Shift+A 快速捕获第一个词吧。'"
      />
    </div>
    <div v-else class="panel overflow-x-auto">
      <table class="w-full min-w-[560px] border-collapse text-sm">
        <thead>
          <tr class="border-b border-stone-200 text-left text-xs text-stone-500 dark:border-stone-800 dark:text-stone-400">
            <th class="px-3.5 py-2 font-semibold">词条</th>
            <th class="px-2 py-2 font-semibold">状态</th>
            <th class="px-2 py-2 font-semibold">熟悉度</th>
            <th class="px-2 py-2 font-semibold">义项</th>
            <th class="px-2 py-2 font-semibold">卡片</th>
            <th class="px-3.5 py-2 text-right font-semibold">更新时间</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-stone-100 dark:divide-stone-800">
          <tr
            v-for="w in page.items"
            :key="w.id"
            class="cursor-pointer transition-colors hover:bg-orange-50/60 dark:hover:bg-orange-950/20"
            :class="selectedId === w.id ? 'bg-orange-50/80 dark:bg-orange-950/30' : ''"
            tabindex="0"
            @click="selectedId = w.id"
            @dblclick="void router.push(`/words/${w.id}`)"
            @keydown.enter="void router.push(`/words/${w.id}`)"
          >
            <td class="max-w-[240px] px-3.5 py-2">
              <div class="flex items-baseline gap-2">
                <span class="truncate font-semibold">{{ w.lemma }}</span>
                <span v-if="w.personal_phonetic" class="truncate font-mono text-xs text-stone-500 dark:text-stone-400">/{{ w.personal_phonetic }}/</span>
              </div>
            </td>
            <td class="px-2 py-2">
              <Tag :label="wordStatusMeta(w.status).label" :tone="wordStatusMeta(w.status).tone" />
            </td>
            <td class="px-2 py-2">
              <FamiliarityDots :value="w.familiarity" />
              <span v-if="w.familiarity === null" class="ml-1 text-xs text-stone-300 dark:text-stone-600">未评估</span>
            </td>
            <td class="px-2 py-2 tabular-nums text-stone-500 dark:text-stone-400">{{ w.senses.length }}</td>
            <td class="px-2 py-2">
              <template v-if="w.card?.due_at">
                <span class="text-[13px] tabular-nums" :class="dueTone(w.card.due_at)">{{ dueLabel(w.card.due_at) }}</span>
              </template>
              <span v-else-if="w.card" class="text-[13px] text-stone-400 dark:text-stone-500">未排期</span>
              <span v-else class="text-[13px] text-stone-300 dark:text-stone-600">无卡片</span>
            </td>
            <td class="px-3.5 py-2 text-right text-xs whitespace-nowrap text-stone-400 dark:text-stone-500">{{ relativeTime(w.updated_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <PaginationBar
      v-if="page && page.items.length"
      :page="page.page"
      :page-size="page.page_size"
      :total="page.total"
      show-size
      @page="filters.page = $event"
      @page-size="filters.pageSize = $event; filters.page = 1"
    />
  </div>
</template>
