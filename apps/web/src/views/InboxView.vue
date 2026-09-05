<script setup lang="ts">
/**
 * 收件箱：UserWord 聚合列表。激活 / 认识 / 归档都是 PATCH /user-words/:id
 * { status }；无义项时 ActivateWordDialog 先引导补充义项再允许激活。
 */
import { computed, reactive, ref } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { messageOf, newClientEventId, type UserWord, type WordStatus } from '@lexoria/api-client';
import { inboxTabs, useCreateInboxItem, useInboxPage, type InboxTab } from '@/api/inbox';
import { useSources } from '@/api/sources';
import { useUpdateWord } from '@/api/words';
import { relativeTime } from '@/lib/format';
import { toastError, toastSuccess } from '@/lib/toast';
import { wordStatusMeta } from '@/lib/statusMeta';
import Icon from '@/components/Icon.vue';
import ActivateWordDialog from '@/components/ActivateWordDialog.vue';
import PaginationBar from '@/components/PaginationBar.vue';
import SourceSelect from '@/components/SourceSelect.vue';
import StateBlock from '@/components/StateBlock.vue';
import Tag from '@/components/Tag.vue';

const router = useRouter();
const createItem = useCreateInboxItem();
const updateWord = useUpdateWord();
const { data: sources } = useSources(false);

const filters = reactive<{ tab: InboxTab; q: string; page: number; pageSize: number }>({
  tab: 'inbox',
  q: '',
  page: 1,
  pageSize: 20,
});

const inboxQuery = useInboxPage(filters);
const page = computed(() => inboxQuery.data.value);
const rows = computed(() => page.value?.items ?? []);

const selectedId = ref<string | null>(null);
const capture = reactive({ text: '', sourceId: null as string | null });
const capturing = ref(false);

const activeItem = ref<UserWord | null>(null);
const activateOpen = ref(false);

function openActivate(item: UserWord): void {
  activeItem.value = item;
  activateOpen.value = true;
}

function onActivated(wordId: string): void {
  activateOpen.value = false;
  activeItem.value = null;
  void router.push(`/words/${wordId}`);
}

async function setStatus(item: UserWord, status: WordStatus): Promise<void> {
  try {
    await updateWord.mutateAsync({ id: item.id, patch: { status } });
    toastSuccess(
      status === 'known' ? `「${item.lemma}」已标记为认识` : status === 'active' ? `「${item.lemma}」已激活` : status === 'inbox' ? `「${item.lemma}」已放回待处理` : `「${item.lemma}」已归档`,
    );
  } catch (err) {
    toastError(messageOf(err));
  }
}

async function captureWord(): Promise<void> {
  const text = capture.text.trim();
  if (!text || capturing.value) return;
  capturing.value = true;
  try {
    const created = await createItem.mutateAsync({
      text,
      source_id: capture.sourceId,
      encounter_type: 'unclassified',
      client_event_id: newClientEventId(),
    });
    filters.page = 1;
    toastSuccess(`已捕获「${created.lemma}」`);
    capture.text = '';
  } catch (err) {
    toastError(messageOf(err));
  } finally {
    capturing.value = false;
  }
}

function selectRow(e: KeyboardEvent): void {
  if (rows.value.length === 0) return;
  const idx = Math.max(0, rows.value.findIndex((r) => r.id === selectedId.value));
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
    const item = rows.value.find((r) => r.id === selectedId.value);
    if (item) openActivate(item);
  }
}

function recentSourceName(item: UserWord): string | null {
  const recent = item.recent_sources;
  if (!recent || recent.length === 0) return null;
  return recent.map((s) => s.name).join('、');
}
</script>

<template>
  <div class="space-y-3" @keydown="selectRow">
    <!-- 顶部：快速捕获（POST /inbox） -->
    <form class="panel flex flex-col gap-2 p-3 sm:flex-row sm:items-center" @submit.prevent="captureWord">
      <Icon name="inbox" :size="15" class="hidden text-stone-400 sm:block" />
      <input
        v-model="capture.text"
        class="field flex-1"
        placeholder="随手捕获一个词 / 短语（Enter 加入收件箱）"
        autocomplete="off"
        spellcheck="false"
      />
      <div class="sm:w-52">
        <SourceSelect v-model="capture.sourceId" :sources="sources ?? []" :allow-empty="false" />
      </div>
      <button type="submit" class="btn-primary shrink-0" :disabled="!capture.text.trim() || capturing">
        <Icon name="plus" :size="14" />捕获
      </button>
    </form>

    <!-- 标签页 + 搜索 -->
    <div class="flex flex-wrap items-center gap-1">
      <div class="flex items-center gap-0.5 rounded-md bg-stone-200/70 p-0.5 dark:bg-stone-800">
        <button
          v-for="t in inboxTabs"
          :key="t.value"
          type="button"
          class="rounded px-2.5 py-1 text-[13px] font-medium transition-colors"
          :class="filters.tab === t.value ? 'bg-white text-stone-900 shadow-sm dark:bg-stone-700 dark:text-white' : 'text-stone-500 hover:text-stone-800 dark:text-stone-400 dark:hover:text-stone-200'"
          @click="filters.tab = t.value; filters.page = 1"
        >
          {{ t.label }}
        </button>
      </div>
      <div class="ml-auto">
        <div class="relative">
          <Icon name="search" :size="13" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-stone-400" />
          <input
            v-model="filters.q"
            class="field !h-8 !w-44 !pl-7 !text-[13px]"
            placeholder="搜索收件箱…"
            @input="filters.page = 1"
          />
        </div>
      </div>
    </div>

    <!-- 列表 -->
    <StateBlock v-if="inboxQuery.isPending.value" state="loading" title="正在加载收件箱…" />
    <StateBlock v-else-if="inboxQuery.isError.value" state="error" title="收件箱加载失败" :hint="inboxQuery.error.value?.message" @retry="void inboxQuery.refetch()" />

    <div v-else-if="page" class="space-y-3">
      <StateBlock
        v-if="page.items.length === 0"
        state="empty"
        :title="filters.q ? '没有匹配的条目' : filters.tab === 'inbox' ? '收件箱空空如也' : '这里还没有条目'"
        :hint="filters.tab === 'inbox' ? '用上面的输入框快速捕获新词，或按 Ctrl+Shift+A。' : '换一个标签页看看？'"
      />
      <ul v-else class="panel divide-y divide-stone-100 dark:divide-stone-800">
        <li
          v-for="item in page.items"
          :key="item.id"
          class="group cursor-pointer px-3 py-2.5 transition-colors hover:bg-stone-50 dark:hover:bg-stone-800/50"
          :class="selectedId === item.id ? 'bg-orange-50/70 dark:bg-orange-950/25' : ''"
          tabindex="0"
          :aria-label="`${item.lemma}：${wordStatusMeta(item.status).label}`"
          @click="selectedId = item.id"
          @dblclick="openActivate(item)"
          @keydown.enter="openActivate(item)"
        >
          <div class="flex items-start gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span class="truncate text-[14.5px] font-semibold">{{ item.lemma }}</span>
                <Tag :label="wordStatusMeta(item.status).label" :tone="wordStatusMeta(item.status).tone" />
                <Tag v-if="item.senses.length === 0" label="缺义项" tone="red" dot />
                <span v-if="item.encounter_count > 0" class="text-xs text-stone-400 tabular-nums dark:text-stone-500">{{ item.encounter_count }} 次遇词</span>
              </div>
              <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-stone-500 dark:text-stone-400">
                <span v-if="recentSourceName(item)" class="inline-flex items-center gap-1">
                  <Icon name="folder" :size="11" />{{ recentSourceName(item) }}
                </span>
                <span class="inline-flex items-center gap-1"><Icon name="clock" :size="11" />{{ relativeTime(item.updated_at) }}</span>
                <RouterLink
                  v-if="item.status !== 'inbox'"
                  :to="`/words/${item.id}`"
                  class="link inline-flex items-center gap-0.5"
                  @click.stop
                >
                  查看词条<Icon name="arrow-right" :size="11" />
                </RouterLink>
              </div>
            </div>

            <div class="flex shrink-0 items-center gap-1 opacity-60 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
              <template v-if="item.status === 'inbox' || item.status === 'active'">
                <button
                  type="button"
                  class="btn-primary btn-sm !h-7"
                  :title="item.senses.length ? '激活' : '先添加义项再激活'"
                  @click.stop="openActivate(item)"
                >
                  <Icon name="check" :size="13" />激活
                </button>
                <button type="button" class="btn-icon btn-sm !h-7 !w-7" title="标记为认识" aria-label="标记为认识" @click.stop="setStatus(item, 'known')">
                  <Icon name="eye" :size="13" />
                </button>
                <button type="button" class="btn-icon btn-sm !h-7 !w-7" title="归档" aria-label="归档" @click.stop="setStatus(item, 'archived')">
                  <Icon name="trash" :size="13" />
                </button>
              </template>
              <template v-else-if="item.status === 'known'">
                <RouterLink :to="`/words/${item.id}`" class="btn-ghost btn-sm !h-7" @click.stop>
                  去词库<Icon name="arrow-right" :size="12" />
                </RouterLink>
                <button type="button" class="btn-icon btn-sm !h-7 !w-7" title="归档" aria-label="归档" @click.stop="setStatus(item, 'archived')">
                  <Icon name="trash" :size="13" />
                </button>
              </template>
              <template v-else>
                <button type="button" class="link text-xs" @click.stop="setStatus(item, 'inbox')">放回待处理</button>
              </template>
            </div>
          </div>
        </li>
      </ul>
      <div v-if="page.items.length" class="flex items-center justify-between gap-3">
        <PaginationBar
          :page="page.page"
          :page-size="page.page_size"
          :total="page.total"
          show-size
          @page="filters.page = $event"
          @page-size="filters.pageSize = $event; filters.page = 1"
        />
        <p class="hidden text-xs text-stone-400 sm:block">↑/↓ 移动选中 · Enter 激活</p>
      </div>
    </div>

    <ActivateWordDialog :open="activateOpen" :item="activeItem" @close="activateOpen = false" @activated="onActivated" />
  </div>
</template>
