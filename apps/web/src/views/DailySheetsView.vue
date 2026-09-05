<script setup lang="ts">
/**
 * 练习纸：配置（仅 Compact/Test × A4/A5 × 1/2 栏）→ 预览 → 生成；下方为历史列表。
 */
import { computed, reactive, ref, watchEffect } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { messageOf, type DailySheetPreview } from '@lexoria/api-client';
import { useSettings } from '@/api/settings';
import { useSources } from '@/api/sources';
import {
  clampCount,
  columnOptions,
  paperSizes,
  sheetTemplates,
  useCreateSheet,
  useDailySheets,
  usePreviewSheet,
  validateSheetDraft,
  type SheetConfigDraft,
} from '@/api/sheets';
import { formatDate, formatDateTime, relativeTime } from '@/lib/format';
import { toastError, toastSuccess } from '@/lib/toast';
import Icon from '@/components/Icon.vue';
import PaginationBar from '@/components/PaginationBar.vue';
import SheetPreview from '@/components/SheetPreview.vue';
import StateBlock from '@/components/StateBlock.vue';

const router = useRouter();
const settingsQuery = useSettings();
const { data: sources } = useSources(false);
const previewMutation = usePreviewSheet();
const createMutation = useCreateSheet();
const sheetsQuery = useDailySheets();

const draft = reactive<SheetConfigDraft>({
  template: 'compact',
  paper_size: 'a4',
  columns: 2,
  review_count: 20,
  new_count: 10,
  source_ids: [],
});

// Prefill from saved settings exactly once (avoid clobbering live edits).
let defaultsApplied = false;
watchEffect(() => {
  const s = settingsQuery.data.value;
  if (!s || defaultsApplied) return;
  defaultsApplied = true;
  draft.template = s.daily_template;
  draft.paper_size = s.paper_size;
  draft.columns = s.columns;
  draft.review_count = s.review_count;
  draft.new_count = s.new_count;
});

const sourceIds = computed({
  get: () => draft.source_ids,
  set: (v: string[]) => {
    draft.source_ids = v;
  },
});
const sourceError = ref(false);

const errors = computed(() => validateSheetDraft(draft));
const valid = computed(() => errors.value.length === 0 && !sourceError.value);

const previewData = ref<DailySheetPreview | null>(null);
const previewHtml = ref<string | null>(null);
const previewing = ref(false);
const generating = ref(false);
const previewError = ref('');

function toggleSource(id: string): void {
  const i = draft.source_ids.indexOf(id);
  if (i >= 0) draft.source_ids.splice(i, 1);
  else draft.source_ids.push(id);
  sourceError.value = draft.source_ids.length === 0 && (draft.review_count > 0 || draft.new_count > 0);
}

async function runPreview(): Promise<void> {
  previewError.value = '';
  previewData.value = null;
  previewHtml.value = null;
  if (!valid.value) return;
  previewing.value = true;
  try {
    const result = await previewMutation.mutateAsync({ ...draft, source_ids: [...draft.source_ids] });
    if ('html' in result && typeof result.html === 'string') {
      previewHtml.value = result.html;
    } else {
      previewData.value = result as DailySheetPreview;
    }
  } catch (err) {
    previewError.value = messageOf(err);
    toastError(messageOf(err));
  } finally {
    previewing.value = false;
  }
}

async function generate(): Promise<void> {
  if (!valid.value) return;
  generating.value = true;
  try {
    const summary = await createMutation.mutateAsync({ ...draft, source_ids: [...draft.source_ids] });
    toastSuccess('练习纸已生成');
    void router.push(`/daily-sheets/${summary.id}`);
  } catch (err) {
    toastError(messageOf(err));
  } finally {
    generating.value = false;
  }
}

function patchCounts(): void {
  draft.review_count = clampCount(draft.review_count);
  draft.new_count = clampCount(draft.new_count);
  sourceError.value = draft.source_ids.length === 0 && (draft.review_count > 0 || draft.new_count > 0);
}

const sheetPage = ref(1);
const sheetPageSize = ref(20);
const sheetPageData = computed(() => {
  const list = sheetsQuery.data.value;
  if (!list) return null;
  const start = (sheetPage.value - 1) * sheetPageSize.value;
  return {
    items: list.items.slice(start, start + sheetPageSize.value),
    total: list.total,
    page: sheetPage.value,
    page_size: sheetPageSize.value,
  };
});
</script>

<template>
  <div class="space-y-5">
    <div class="grid items-start gap-5 xl:grid-cols-2">
      <!-- 配置 -->
      <section class="panel space-y-4 p-4">
        <h3 class="microlabel">配置</h3>

        <div>
          <span class="microlabel mb-1.5 block">模板</span>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="t in sheetTemplates"
              :key="t.value"
              type="button"
              class="rounded-md border px-3 py-2.5 text-left transition-colors"
              :class="draft.template === t.value ? 'border-orange-500 bg-orange-50 dark:bg-orange-950/40' : 'border-stone-300 hover:border-stone-400 dark:border-stone-600'"
              @click="draft.template = t.value"
            >
              <span class="block text-sm font-semibold">{{ t.label }}</span>
              <span class="mt-0.5 block text-xs text-stone-500 dark:text-stone-400">{{ t.hint }}</span>
            </button>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="microlabel mb-1 block" for="sheet-paper">纸张</label>
            <select id="sheet-paper" v-model="draft.paper_size" class="field">
              <option v-for="p in paperSizes" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
          </div>
          <div>
            <span class="microlabel mb-1 block">栏数</span>
            <div class="grid grid-cols-2 gap-1 rounded-md bg-stone-100 p-1 dark:bg-stone-800">
              <button
                v-for="c in columnOptions"
                :key="c.value"
                type="button"
                class="rounded px-1 py-1.5 text-[13px] font-medium"
                :class="draft.columns === c.value ? 'bg-white shadow-sm dark:bg-stone-600' : 'text-stone-500 dark:text-stone-400'"
                @click="draft.columns = c.value"
              >
                {{ c.label }}
              </button>
            </div>
          </div>
          <div>
            <label class="microlabel mb-1 block" for="sheet-review-count">复习词数</label>
            <input id="sheet-review-count" type="number" min="0" max="100" class="field" v-model.number="draft.review_count" @blur="patchCounts" />
          </div>
          <div>
            <label class="microlabel mb-1 block" for="sheet-new-count">新词数</label>
            <input id="sheet-new-count" type="number" min="0" max="100" class="field" v-model.number="draft.new_count" @blur="patchCounts" />
          </div>
        </div>

        <div>
          <div class="mb-1.5 flex items-center justify-between">
            <span class="microlabel">选择来源（{{ draft.source_ids.length }}）</span>
            <span class="flex gap-2">
              <button type="button" class="link text-xs" @click="sourceIds = (sources ?? []).filter((s) => !s.archived_at).map((s) => s.id)">全选</button>
              <button type="button" class="link text-xs" @click="sourceIds = []">清空</button>
            </span>
          </div>
          <div class="max-h-36 space-y-1 overflow-y-auto rounded-md border border-stone-200 p-2 dark:border-stone-700">
            <p v-if="!sources || sources.length === 0" class="px-1 py-2 text-center text-xs text-stone-400">
              还没有来源 —— 先去「来源」页创建，或直接不选（全库抽取）。
            </p>
            <label v-for="s in sources" :key="s.id" class="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-[13px] hover:bg-stone-50 dark:hover:bg-stone-800/60" :class="s.archived_at ? 'text-stone-400 line-through dark:text-stone-600' : ''">
              <input type="checkbox" class="accent-orange-600" :checked="draft.source_ids.includes(s.id)" :disabled="Boolean(s.archived_at)" @change="toggleSource(s.id)" />
              <span class="min-w-0 flex-1 truncate">{{ s.name }}</span>
            </label>
          </div>
        </div>

        <div v-if="errors.length" class="space-y-1">
          <p v-for="(e, i) in errors" :key="i" class="text-xs text-red-600 dark:text-red-400">· {{ e }}</p>
        </div>
        <p v-else-if="sourceError" class="text-xs text-red-600 dark:text-red-400">· 词数大于 0 时至少要选一个来源（或清空来源表示全库抽取）</p>

        <div class="flex gap-2">
          <button type="button" class="btn-ghost flex-1" :disabled="!valid || previewing" @click="runPreview">
            <Icon v-if="previewing" name="refresh" :size="14" class="animate-spin" />
            <Icon v-else name="eye" :size="14" />预览
          </button>
          <button type="button" class="btn-primary flex-1" :disabled="!valid || generating" @click="generate">
            <span v-if="generating" class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            <Icon v-else name="plus" :size="14" />生成练习纸
          </button>
        </div>
      </section>

      <!-- 预览 -->
      <section class="space-y-2">
        <h3 class="microlabel px-1">预览</h3>
        <div v-if="previewError" class="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
          {{ previewError }}
        </div>
        <SheetPreview :preview="previewData" :html="previewHtml" />
      </section>
    </div>

    <!-- 历史 -->
    <section class="space-y-2">
      <h3 class="microlabel px-1">历史</h3>
      <StateBlock v-if="sheetsQuery.isPending.value" state="loading" title="正在加载历史…" />
      <StateBlock v-else-if="sheetsQuery.isError.value" state="error" title="历史加载失败" :hint="sheetsQuery.error.value?.message" @retry="void sheetsQuery.refetch()" />
      <div v-else-if="sheetsQuery.data.value && sheetsQuery.data.value.items.length === 0" class="panel">
        <StateBlock state="empty" title="还没有生成过练习纸" hint="配置好上面的选项，点「生成练习纸」即可。" />
      </div>
      <div v-else-if="sheetPageData" class="panel divide-y divide-stone-100 dark:divide-stone-800">
        <RouterLink
          v-for="s in sheetPageData.items"
          :key="s.id"
          :to="`/daily-sheets/${s.id}`"
          class="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-stone-50 dark:hover:bg-stone-800/60"
        >
          <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-400">
            <Icon name="file" :size="15" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium">
              {{ s.sheet_date || formatDate(s.created_at) }} ·
              {{ s.template === 'compact' ? 'Compact' : 'Test' }} · {{ s.paper_size.toUpperCase() }} · {{ s.columns }} 栏
            </span>
            <span class="block text-xs text-stone-400 dark:text-stone-500">
              <template v-if="s.actual_review_count !== undefined || s.actual_new_count !== undefined">
                {{ s.actual_review_count ?? 0 }} 复习 + {{ s.actual_new_count ?? 0 }} 新词 ·
              </template>
              {{ s.timezone_snapshot }} · {{ relativeTime(s.created_at) }}
            </span>
          </span>
          <span class="hidden text-xs text-stone-400 sm:block">{{ formatDateTime(s.created_at) }}</span>
          <Icon name="chevron-right" :size="14" class="text-stone-300 dark:text-stone-600" />
        </RouterLink>
      </div>
      <PaginationBar
        v-if="sheetsQuery.data.value && sheetsQuery.data.value.total > sheetPageSize"
        :page="sheetPage"
        :page-size="sheetPageSize"
        :total="sheetsQuery.data.value.total"
        @page="sheetPage = $event"
      />
    </section>
  </div>
</template>
