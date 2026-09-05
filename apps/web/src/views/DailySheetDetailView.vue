<script setup lang="ts">
/** 练习纸详情：摘要信息 + items 快照/预览 + 认证 Blob 下载 PDF。 */
import { computed, ref } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { messageOf, type SheetSnapshotItem } from '@lexoria/api-client';
import { useDailySheet } from '@/api/sheets';
import { api } from '@/lib/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { toastError, toastSuccess } from '@/lib/toast';
import Icon from '@/components/Icon.vue';
import SheetPreview from '@/components/SheetPreview.vue';
import StateBlock from '@/components/StateBlock.vue';
import Tag from '@/components/Tag.vue';

const route = useRoute();
const id = String(route.params.id ?? '');
const sheetQuery = useDailySheet(id);

const downloading = ref(false);

const sheet = computed(() => sheetQuery.data.value);
const reviewItems = computed(() => (sheet.value?.items ?? []).filter((x) => x.kind === 'review'));
const newItems = computed(() => (sheet.value?.items ?? []).filter((x) => x.kind === 'new'));

async function downloadPdf(): Promise<void> {
  downloading.value = true;
  try {
    const blob = await api.dailySheets.pdf(id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `lexiora-daily-sheet-${id.slice(0, 8)}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 4000);
    toastSuccess('PDF 已开始下载');
  } catch (err) {
    toastError(messageOf(err));
  } finally {
    downloading.value = false;
  }
}

function defsOf(item: SheetSnapshotItem): string {
  return [item.definition_zh?.trim(), item.definition_en?.trim()].filter(Boolean).join(' / ');
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-4">
    <div v-if="sheetQuery.isPending.value" class="panel"><StateBlock state="loading" title="正在加载练习纸…" /></div>
    <div v-else-if="sheetQuery.isError.value" class="panel">
      <StateBlock state="error" title="练习纸加载失败" :hint="sheetQuery.error.value?.message" @retry="void sheetQuery.refetch()" />
    </div>

    <template v-else-if="sheet">
      <div class="flex flex-wrap items-center gap-3">
        <RouterLink to="/daily-sheets" class="btn-icon" title="返回列表" aria-label="返回">
          <Icon name="chevron-left" :size="16" />
        </RouterLink>
        <div class="min-w-0 flex-1">
          <h2 class="flex flex-wrap items-center gap-2 text-lg font-bold tracking-tight">
            练习纸 · {{ sheet.template === 'compact' ? 'Compact' : 'Test' }}
          </h2>
          <p class="mt-0.5 text-xs text-stone-400 dark:text-stone-500">
            日期 {{ sheet.sheet_date || formatDate(sheet.created_at) }} · {{ formatDateTime(sheet.created_at) }}
          </p>
        </div>
        <button type="button" class="btn-primary" :disabled="downloading" @click="downloadPdf">
          <Icon v-if="downloading" name="refresh" :size="14" class="animate-spin" />
          <Icon v-else name="download" :size="14" />下载 PDF
        </button>
      </div>

      <dl class="panel grid grid-cols-2 gap-x-6 gap-y-2 px-4 py-3 text-sm sm:grid-cols-4">
        <div>
          <dt class="microlabel">模板</dt>
          <dd class="mt-0.5">{{ sheet.template === 'compact' ? 'Compact' : 'Test' }}</dd>
        </div>
        <div>
          <dt class="microlabel">纸张</dt>
          <dd class="mt-0.5">{{ sheet.paper_size.toUpperCase() }}</dd>
        </div>
        <div>
          <dt class="microlabel">栏数</dt>
          <dd class="mt-0.5">{{ sheet.columns }}</dd>
        </div>
        <div>
          <dt class="microlabel">词数</dt>
          <dd class="mt-0.5 tabular-nums">
            <template v-if="sheet.actual_review_count !== undefined || sheet.actual_new_count !== undefined">
              {{ sheet.actual_review_count ?? 0 }} 复习 + {{ sheet.actual_new_count ?? 0 }} 新词
            </template>
            <template v-else>{{ (sheet.items ?? []).length }} 个词</template>
          </dd>
        </div>
        <div>
          <dt class="microlabel">时区快照</dt>
          <dd class="mt-0.5">{{ sheet.timezone_snapshot }}</dd>
        </div>
      </dl>

      <!-- items 快照渲染（无 HTML 预览时的后备视图） -->
      <section v-if="!sheet.preview && !sheet.html && (sheet.items ?? []).length" class="panel divide-y divide-stone-100 dark:divide-stone-800">
        <div v-if="reviewItems.length" class="px-4 py-3">
          <h3 class="microlabel mb-2">复习 · Review（{{ reviewItems.length }}）</h3>
          <ol class="space-y-1.5">
            <li v-for="(item, i) in reviewItems" :key="i" class="flex flex-wrap items-baseline gap-x-2 text-sm">
              <span class="w-4 text-right font-mono text-xs text-stone-400">{{ i + 1 }}</span>
              <span class="font-medium">{{ item.lemma }}</span>
              <span v-if="item.part_of_speech" class="font-mono text-xs text-violet-600 italic dark:text-violet-300">{{ item.part_of_speech }}</span>
              <span class="text-[13px] text-stone-500 dark:text-stone-400">{{ defsOf(item) }}</span>
            </li>
          </ol>
        </div>
        <div v-if="newItems.length" class="px-4 py-3">
          <h3 class="microlabel mb-2">新词 · New（{{ newItems.length }}）</h3>
          <ol class="space-y-1.5">
            <li v-for="(item, i) in newItems" :key="i" class="flex flex-wrap items-baseline gap-x-2 text-sm">
              <span class="w-4 text-right font-mono text-xs text-stone-400">{{ i + 1 }}</span>
              <span class="font-medium">{{ item.lemma }}</span>
              <span v-if="item.part_of_speech" class="font-mono text-xs text-violet-600 italic dark:text-violet-300">{{ item.part_of_speech }}</span>
              <span class="text-[13px] text-stone-500 dark:text-stone-400">{{ defsOf(item) }}</span>
            </li>
          </ol>
        </div>
      </section>

      <SheetPreview v-if="sheet.preview || sheet.html" :preview="sheet.preview ?? null" :html="sheet.html ?? null" />
      <div v-else-if="!(sheet.items ?? []).length" class="panel">
        <StateBlock state="empty" title="暂无内容快照" hint="该练习纸的内容可能已过期或尚未生成；可从列表重新生成。" />
      </div>

      <div class="flex items-center gap-2 text-xs text-stone-400 dark:text-stone-500">
        <Tag label="快照仅存档词面信息" tone="stone" dot />
        <span>生成于 {{ formatDateTime(sheet.created_at) }}</span>
      </div>
    </template>
  </div>
</template>
