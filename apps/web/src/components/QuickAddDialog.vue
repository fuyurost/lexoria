<script setup lang="ts">
/**
 * Global Quick Add (Ctrl+Shift+A): 输入词 + 可选来源 → Enter 提交。
 * 焦点保留、可连续添加；逐条展示「新建捕获 / 重复捕获」结果。
 */
import { nextTick, ref, watch } from 'vue';
import { useQueryClient } from '@tanstack/vue-query';
import { newClientEventId, type Source } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { QK } from '@/api/common';
import { toastError } from '@/lib/toast';
import Icon from './Icon.vue';
import Modal from './Modal.vue';
import SourceSelect from './SourceSelect.vue';

interface CaptureResult {
  id: number;
  kind: 'new' | 'dup' | 'error';
  text: string;
  message: string;
}

const props = defineProps<{ open: boolean; sources: Source[] }>();
const emit = defineEmits<{ close: [] }>();

const word = ref('');
const sourceId = ref<string | null>(null);
const busy = ref(false);
const results = ref<CaptureResult[]>([]);
const inputEl = ref<HTMLInputElement | null>(null);
const queryClient = useQueryClient();
let seq = 0;

watch(
  () => props.open,
  async (open) => {
    if (open) {
      results.value = [];
      await nextTick();
      inputEl.value?.focus();
    }
  },
  { immediate: true },
);

function sourceName(id: string | null): string | null {
  if (!id) return null;
  return props.sources.find((s) => s.id === id)?.name ?? null;
}

function pushResult(kind: CaptureResult['kind'], text: string, message: string): void {
  results.value = [{ id: ++seq, kind, text, message }, ...results.value].slice(0, 6);
}

async function submit(): Promise<void> {
  const text = word.value.trim();
  if (!text || busy.value) return;
  busy.value = true;
  try {
    // 直接捕获（POST /inbox）：不做词库预查（避免延迟与竞态）。
    // 新建/重复由服务端响应的 user_word_created 决定。
    const created = await api.inbox.create({
      text,
      source_id: sourceId.value,
      encounter_type: 'unclassified',
      client_event_id: newClientEventId(),
    });
    const src = sourceName(sourceId.value);
    const suffix = src ? ` · 来源：${src}` : '';
    const isNew = created.user_word_created === true;
    pushResult(
      isNew ? 'new' : 'dup',
      text,
      isNew
        ? `新建捕获：已加入收件箱待处理${suffix}`
        : `重复捕获：词库中已有「${created.lemma || text}」，已记录一次遇词${suffix}`,
    );
    word.value = '';
    void queryClient.invalidateQueries({ queryKey: QK.inbox });
    void queryClient.invalidateQueries({ queryKey: QK.stats });
    void queryClient.invalidateQueries({ queryKey: QK.words });
  } catch (err) {
    const message = err instanceof Error ? err.message : '快速添加失败';
    pushResult('error', text, message);
    toastError(message);
  } finally {
    busy.value = false;
  }
  // Focus only once the field is re-enabled (macrotask: any disabled→enabled
  // patch and focus steal by the browser have settled).
  await nextTick();
  window.setTimeout(() => {
    inputEl.value?.focus();
  }, 0);
}
</script>

<template>
  <Modal :open="open" title="快速添加" width="max-w-md" @close="emit('close')">
    <form class="space-y-3" @submit.prevent="submit">
      <div>
        <label class="microlabel mb-1 block" for="quick-word">单词 / 短语</label>
        <input
          id="quick-word"
          ref="inputEl"
          v-model="word"
          class="field"
          placeholder="输入单词或短语，Enter 提交"
          autocomplete="off"
          spellcheck="false"
          :disabled="busy"
        />
      </div>
      <div>
        <label class="microlabel mb-1 block" for="quick-source">来源（可选）</label>
        <SourceSelect id="quick-source" v-model="sourceId" :sources="sources" />
      </div>
      <div class="flex items-center justify-end gap-2">
        <button type="button" class="btn-ghost" :disabled="busy" @click="emit('close')">关闭 (Esc)</button>
        <button type="submit" class="btn-primary" :disabled="busy || !word.trim()">
          <span v-if="busy" class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
          <Icon v-else name="plus" :size="14" />
          捕获
        </button>
      </div>
    </form>

    <div v-if="results.length" class="mt-3 border-t border-stone-200 pt-3 dark:border-stone-800">
      <p class="microlabel mb-1.5">本次结果</p>
      <ul class="max-h-44 space-y-1.5 overflow-y-auto">
        <li
          v-for="r in results"
          :key="r.id"
          class="flex items-start gap-2 rounded-md px-2 py-1.5 text-[13px]"
          :class="r.kind === 'error' ? 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300' : r.kind === 'dup' ? 'bg-amber-50/70 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200' : 'bg-emerald-50/70 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200'"
        >
          <Icon
            :name="r.kind === 'error' ? 'alert' : r.kind === 'dup' ? 'info' : 'check'"
            :size="14"
            class="mt-0.5 shrink-0"
          />
          <div class="min-w-0">
            <span class="font-semibold">{{ r.text }}</span>
            <p class="text-xs opacity-80">{{ r.message }}</p>
          </div>
        </li>
      </ul>
    </div>
  </Modal>
</template>
