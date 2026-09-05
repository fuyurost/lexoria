<script setup lang="ts">
/**
 * 激活一个收件箱条目（该条目即 UserWord 聚合，id 就是 user_word_id）：
 * 前置条件——至少有 1 个义项；没有义项时先引导填写义项。
 * 激活 = PATCH /user-words/:id { status: 'active' }（无任何 ASSUMED ROUTE）。
 */
import { ref, watch } from 'vue';
import { useQueryClient } from '@tanstack/vue-query';
import { messageOf, type UserWord } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { QK } from '@/api/common';
import { toastError, toastSuccess } from '@/lib/toast';
import { hasDefinition, emptySenseDraft, type SenseDraft } from '@/lib/senseDraft';
import Icon from './Icon.vue';
import Modal from './Modal.vue';
import SenseFields from './SenseFields.vue';
import StateBlock from './StateBlock.vue';
import Tag from './Tag.vue';

const props = defineProps<{ open: boolean; item: UserWord | null }>();
const emit = defineEmits<{ close: []; activated: [wordId: string] }>();

type Stage = 'busy' | 'direct' | 'senses' | 'failed';

const stage = ref<Stage>('busy');
const word = ref<UserWord | null>(null);
const errorMsg = ref('');
const draft = ref<SenseDraft>(emptySenseDraft());
const adding = ref(false);
const activating = ref(false);
const queryClient = useQueryClient();

watch(
  () => [props.open, props.item] as const,
  async ([open, item]) => {
    if (!open || !item) return;
    stage.value = 'busy';
    word.value = null;
    errorMsg.value = '';
    draft.value = emptySenseDraft();
    try {
      // Inbox rows are user-words: fetch by the same id.
      const target = await api.words.get(item.id);
      word.value = target;
      stage.value = target.senses.length > 0 ? 'direct' : 'senses';
    } catch (err) {
      errorMsg.value = messageOf(err);
      stage.value = 'failed';
    }
  },
);

async function addSense(): Promise<void> {
  const w = word.value;
  if (!w || !hasDefinition(draft.value) || adding.value) return;
  adding.value = true;
  try {
    const sense = await api.senses.create(w.id, {
      part_of_speech: draft.value.part_of_speech.trim() || null,
      definition_zh: draft.value.definition_zh.trim() || undefined,
      definition_en: draft.value.definition_en.trim() || undefined,
    });
    w.senses.push(sense);
    draft.value = emptySenseDraft();
    if (w.senses.length >= 1) stage.value = 'direct';
  } catch (err) {
    toastError(messageOf(err));
  } finally {
    adding.value = false;
  }
}

async function activate(): Promise<void> {
  const w = word.value;
  const item = props.item;
  if (!w || !item || activating.value) return;
  if (w.senses.length === 0) {
    stage.value = 'senses';
    return;
  }
  activating.value = true;
  try {
    await api.words.update(item.id, { status: 'active' });
    toastSuccess(`「${w.lemma}」已激活`);
    void queryClient.invalidateQueries({ queryKey: QK.inbox });
    void queryClient.invalidateQueries({ queryKey: QK.words });
    void queryClient.invalidateQueries({ queryKey: QK.stats });
    void queryClient.invalidateQueries({ queryKey: QK.reviewQueue });
    emit('activated', w.id);
  } catch (err) {
    toastError(messageOf(err));
  } finally {
    activating.value = false;
  }
}

function definitionLine(s: { definition_zh: string; definition_en: string }): string {
  const parts = [s.definition_zh.trim(), s.definition_en.trim()].filter(Boolean);
  return parts.join(' / ');
}
</script>

<template>
  <Modal :open="open" :title="`激活：${props.item?.lemma ?? ''}`" width="max-w-lg" @close="emit('close')">
    <div class="space-y-4">
      <StateBlock v-if="stage === 'busy'" state="loading" title="正在读取词条…" />

      <div v-else-if="stage === 'failed'" class="space-y-3">
        <p class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/50 dark:text-red-300">{{ errorMsg }}</p>
        <div class="flex justify-end">
          <button type="button" class="btn-ghost" @click="emit('close')">关闭</button>
        </div>
      </div>

      <template v-else-if="word">
        <div class="flex flex-wrap items-center gap-2 rounded-md bg-stone-50 px-3 py-2 dark:bg-stone-800/60">
          <span class="text-[15px] font-semibold">{{ word.lemma }}</span>
          <span v-if="word.personal_phonetic" class="font-mono text-[13px] text-stone-500 dark:text-stone-400">/{{ word.personal_phonetic }}/</span>
          <span class="flex-1" />
          <Tag label="已在词库" tone="emerald" />
        </div>

        <template v-if="stage === 'senses'">
          <div class="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            <p class="flex items-center gap-1.5"><Icon name="info" :size="13" />「{{ word.lemma }}」还没有义项 —— 先补至少 1 条义项再激活。</p>
          </div>
          <div>
            <div class="microlabel mb-1.5">添加义项</div>
            <SenseFields :value="draft" compact @update:value="draft = $event" />
            <div class="mt-2 flex justify-end">
              <button type="button" class="btn-ghost btn-sm" :disabled="!hasDefinition(draft) || adding" @click="addSense">
                <Icon name="plus" :size="13" />添加义项
              </button>
            </div>
          </div>
        </template>

        <div v-if="word.senses.length" class="space-y-1.5">
          <p class="microlabel">现有义项（{{ word.senses.length }}）</p>
          <ol class="list-inside list-decimal space-y-1 text-sm text-stone-600 dark:text-stone-300">
            <li v-for="s in word.senses" :key="s.id">
              <span v-if="s.part_of_speech" class="mr-1 text-[12px] text-violet-600 italic dark:text-violet-300">{{ s.part_of_speech }}</span>
              {{ definitionLine(s) }}
            </li>
          </ol>
        </div>

        <p v-if="stage === 'direct'" class="rounded-md bg-emerald-50 px-3 py-2 text-[13px] text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
          义项齐备，激活后词条进入「学习中」并参与复习排期。
        </p>

        <div class="flex items-center justify-end gap-2 border-t border-stone-200 pt-3 dark:border-stone-800">
          <button type="button" class="btn-ghost" :disabled="activating" @click="emit('close')">取消</button>
          <button type="button" class="btn-primary" :disabled="word.senses.length === 0 || activating" @click="activate">
            <span v-if="activating" class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            <Icon v-else name="check" :size="14" />
            激活
          </button>
        </div>
      </template>
    </div>
  </Modal>
</template>
