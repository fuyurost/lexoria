<script setup lang="ts">
/**
 * 词条详情（UserWord 聚合）：
 * lemma / personal_phonetic / 义项 CRUD（中英释义）、状态 / 熟悉度 / note、
 * 卡片（difficulty / stability / due_at …）、遇词历史与记录。
 * 来源不挂在词上（无 source_id 假设）；通过遇词关联。
 */
import { computed, reactive, ref, watchEffect } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { messageOf, newClientEventId, type Familiarity, type Sense, type WordStatus } from '@lexoria/api-client';
import {
  useCreateSense,
  useDeleteSense,
  useUpdateSense,
  useUpdateWord,
  useWord,
  useWordEncounters,
} from '@/api/words';
import { dueLabel, formatDateTime, relativeTime } from '@/lib/format';
import { toastError, toastSuccess } from '@/lib/toast';
import { cardStage, wordStatusMeta } from '@/lib/statusMeta';
import { hasDefinition, emptySenseDraft, type SenseDraft } from '@/lib/senseDraft';
import { api } from '@/lib/api';
import Icon from '@/components/Icon.vue';
import FamiliarityDots from '@/components/FamiliarityDots.vue';
import SenseFields from '@/components/SenseFields.vue';
import SourceSelect from '@/components/SourceSelect.vue';
import StateBlock from '@/components/StateBlock.vue';
import Tag from '@/components/Tag.vue';
import { useSources } from '@/api/sources';

const route = useRoute();
const router = useRouter();
const wordId = computed(() => String(route.params.id ?? ''));

const wordQuery = useWord(wordId.value);
const encountersQuery = useWordEncounters(wordId.value);
const updateWord = useUpdateWord();
const { data: sources } = useSources(false);

const word = computed(() => wordQuery.data.value);

const STATUS_OPTIONS: WordStatus[] = ['inbox', 'active', 'known', 'archived'];

/* ---- personal_phonetic ---- */
const phoneticDraft = ref('');
watchEffect(() => {
  phoneticDraft.value = word.value?.personal_phonetic ?? '';
});
const phoneticDirty = computed(() => (phoneticDraft.value.trim() || null) !== (word.value?.personal_phonetic ?? null));

async function savePhonetic(): Promise<void> {
  if (!word.value) return;
  try {
    await updateWord.mutateAsync({ id: word.value.id, patch: { personal_phonetic: phoneticDraft.value.trim() || null } });
    toastSuccess('音标已更新');
  } catch (err) {
    toastError(messageOf(err));
  }
}

async function setStatus(status: WordStatus): Promise<void> {
  if (!word.value || word.value.status === status) return;
  try {
    await updateWord.mutateAsync({ id: word.value.id, patch: { status } });
    toastSuccess(wordStatusMeta(status).label);
  } catch (err) {
    toastError(messageOf(err));
  }
}

async function setFamiliarity(v: number): Promise<void> {
  if (!word.value) return;
  try {
    await updateWord.mutateAsync({ id: word.value.id, patch: { familiarity: v as Familiarity } });
  } catch (err) {
    toastError(messageOf(err));
  }
}

async function clearFamiliarity(): Promise<void> {
  if (!word.value || word.value.familiarity === null) return;
  try {
    await updateWord.mutateAsync({ id: word.value.id, patch: { familiarity: null } });
  } catch (err) {
    toastError(messageOf(err));
  }
}

/* ---- note ---- */
const noteDraft = ref('');
const noteDirty = ref(false);
watchEffect(() => {
  noteDraft.value = word.value?.note ?? '';
  noteDirty.value = false;
});
async function saveNote(): Promise<void> {
  if (!word.value) return;
  try {
    await updateWord.mutateAsync({ id: word.value.id, patch: { note: noteDraft.value.trim() || null } });
    noteDirty.value = false;
    toastSuccess('备注已保存');
  } catch (err) {
    toastError(messageOf(err));
  }
}

/* ---- senses CRUD ---- */
const showAddSense = ref(false);
const newSense = ref<SenseDraft>(emptySenseDraft());
const createSense = useCreateSense();
const deleteSense = useDeleteSense();
const updateSense = useUpdateSense();

function toSenseBody(d: SenseDraft, { partial }: { partial: boolean }) {
  const zh = d.definition_zh.trim();
  const en = d.definition_en.trim();
  if (partial) {
    return {
      part_of_speech: d.part_of_speech.trim() || null,
      definition_zh: zh || undefined,
      definition_en: en || undefined,
    };
  }
  return {
    part_of_speech: d.part_of_speech.trim() || null,
    definition_zh: zh || undefined,
    definition_en: en || undefined,
  };
}

async function addSense(): Promise<void> {
  if (!word.value || !hasDefinition(newSense.value)) return;
  try {
    await createSense.mutateAsync({ wordId: word.value.id, body: toSenseBody(newSense.value, { partial: false }) });
    newSense.value = emptySenseDraft();
    showAddSense.value = false;
    toastSuccess('义项已添加');
  } catch (err) {
    toastError(messageOf(err));
  }
}

const editingSenseId = ref<string | null>(null);
const editSense = ref<SenseDraft>(emptySenseDraft());
const pendingDeleteId = ref<string | null>(null);

function startEditSense(s: Sense): void {
  editingSenseId.value = s.id;
  editSense.value = { part_of_speech: s.part_of_speech ?? '', definition_zh: s.definition_zh, definition_en: s.definition_en };
}

async function saveSense(s: Sense): Promise<void> {
  if (!hasDefinition(editSense.value)) return;
  try {
    await updateSense.mutateAsync({
      senseId: s.id,
      wordId: s.user_word_id,
      patch: toSenseBody(editSense.value, { partial: true }),
    });
    editingSenseId.value = null;
    toastSuccess('义项已更新');
  } catch (err) {
    toastError(messageOf(err));
  }
}

async function removeSense(s: Sense): Promise<void> {
  if (pendingDeleteId.value === s.id) {
    try {
      await deleteSense.mutateAsync({ senseId: s.id, wordId: s.user_word_id });
      pendingDeleteId.value = null;
      toastSuccess('义项已删除');
    } catch (err) {
      toastError(messageOf(err));
    }
    return;
  }
  pendingDeleteId.value = s.id;
  window.setTimeout(() => {
    if (pendingDeleteId.value === s.id) pendingDeleteId.value = null;
  }, 3000);
}

async function moveSense(s: Sense, dir: -1 | 1): Promise<void> {
  if (!word.value) return;
  const list = [...word.value.senses].sort((a, b) => a.sort_order - b.sort_order);
  const idx = list.findIndex((x) => x.id === s.id);
  const other = list[idx + dir];
  if (!other) return;
  try {
    await updateSense.mutateAsync({ senseId: s.id, wordId: s.user_word_id, patch: { sort_order: other.sort_order } });
    await updateSense.mutateAsync({ senseId: other.id, wordId: other.user_word_id, patch: { sort_order: s.sort_order } });
  } catch (err) {
    toastError(messageOf(err));
  }
}

const orderedSenses = computed(() => {
  const list = word.value?.senses ?? [];
  return [...list].sort((a, b) => a.sort_order - b.sort_order);
});

/* ---- encounters (append-only, requires client_event_id) ---- */
const encDraft = reactive({ surfaceText: '', context: '', type: '', sourceId: null as string | null });
const addingEncounter = ref(false);
const ENC_TYPES = ['阅读', '听力', '口语', '写作', '复习', '捕获'];

async function addEncounter(): Promise<void> {
  if (!word.value || addingEncounter.value) return;
  const hasContent = Boolean(encDraft.surfaceText.trim() || encDraft.context.trim());
  if (!hasContent) {
    toastError('请至少填「表面形式」或上下文');
    return;
  }
  addingEncounter.value = true;
  try {
    await api.encounters.create({
      user_word_id: word.value.id,
      surface_text: encDraft.surfaceText.trim() || null,
      source_id: encDraft.sourceId,
      type: encDraft.type.trim() || null,
      context: encDraft.context.trim() || null,
      client_event_id: newClientEventId(),
    });
    encDraft.surfaceText = '';
    encDraft.context = '';
    encDraft.type = '';
    toastSuccess('已记录遇词');
    void encountersQuery.refetch();
    void wordQuery.refetch();
  } catch (err) {
    toastError(messageOf(err));
  } finally {
    addingEncounter.value = false;
  }
}
</script>

<template>
  <div v-if="!word" class="space-y-3">
    <div v-if="wordQuery.isPending.value" class="panel"><StateBlock state="loading" title="正在加载词条…" /></div>
    <div v-else class="panel">
      <StateBlock state="error" title="词条加载失败" :hint="wordQuery.error.value?.message" @retry="void wordQuery.refetch()" />
      <div class="px-4 pb-4 text-center">
        <button type="button" class="btn-ghost btn-sm" @click="router.back()">返回</button>
      </div>
    </div>
  </div>

  <div v-else class="space-y-4">
    <!-- 头部 -->
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="flex items-center gap-1.5">
        <button type="button" class="btn-icon" title="返回词库" aria-label="返回" @click="router.back()">
          <Icon name="chevron-left" :size="16" />
        </button>
        <div>
          <div class="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <h2 class="text-2xl font-bold tracking-tight">{{ word.lemma }}</h2>
            <span v-if="word.personal_phonetic" class="font-mono text-sm text-stone-500 dark:text-stone-400">/{{ word.personal_phonetic }}/</span>
          </div>
          <p class="mt-0.5 text-xs text-stone-400 dark:text-stone-500">
            {{ word.normalized_lemma }}
            <template v-if="word.word_id"> · 词典词 #{{ word.word_id.slice(0, 8) }}</template>
            · 首次 {{ formatDateTime(word.first_seen_at) }} · 最近遇词 {{ relativeTime(word.last_seen_at) }}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <select class="field-sm w-auto" :value="word.status" aria-label="状态" @change="setStatus(($event.target as HTMLSelectElement).value as WordStatus)">
          <option v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ wordStatusMeta(s).label }}</option>
        </select>
        <RouterLink to="/review" class="btn-primary btn-sm">
          <Icon name="repeat" :size="13" />去复习
        </RouterLink>
      </div>
    </div>

    <!-- 无义项提示 -->
    <div
      v-if="word.senses.length === 0"
      class="flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2.5 text-[13px] text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
    >
      <Icon name="alert" :size="15" class="shrink-0" />
      <span class="flex-1">还没有义项 —— 复习与激活都依赖义项，先补上第一条（中英释义至少一项）。</span>
      <button type="button" class="btn-ghost btn-sm !border-amber-300 dark:!border-amber-800" @click="showAddSense = true">添加义项</button>
    </div>

    <div class="grid gap-4 xl:grid-cols-3">
      <!-- 左两列：义项 -->
      <section class="panel space-y-3 p-4 xl:col-span-2">
        <header class="flex items-center justify-between">
          <h3 class="microlabel">义项（{{ word.senses.length }}）</h3>
          <button type="button" class="btn-ghost btn-sm" @click="showAddSense = !showAddSense">
            <Icon name="plus" :size="13" />添加义项
          </button>
        </header>

        <form v-if="showAddSense" class="space-y-2 rounded-md border border-stone-200 p-3 dark:border-stone-700" @submit.prevent="addSense">
          <SenseFields :value="newSense" @update:value="newSense = $event" />
          <p class="text-xs text-stone-400">中文或英文释义至少填一项。</p>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn-ghost btn-sm" @click="showAddSense = false">取消</button>
            <button type="submit" class="btn-primary btn-sm" :disabled="!hasDefinition(newSense)">保存义项</button>
          </div>
        </form>

        <ol v-if="orderedSenses.length" class="space-y-2">
          <li
            v-for="(s, i) in orderedSenses"
            :key="s.id"
            class="group rounded-md border border-stone-200 px-3 py-2.5 dark:border-stone-700"
          >
            <template v-if="editingSenseId === s.id">
              <SenseFields :value="editSense" @update:value="editSense = $event" />
              <div class="mt-2 flex justify-end gap-2">
                <button type="button" class="btn-ghost btn-sm" @click="editingSenseId = null">取消</button>
                <button type="button" class="btn-primary btn-sm" :disabled="!hasDefinition(editSense)" @click="saveSense(s)">保存</button>
              </div>
            </template>
            <template v-else>
              <div class="flex items-start gap-2">
                <span class="mt-0.5 w-5 text-right font-mono text-xs text-stone-400 tabular-nums">{{ i + 1 }}.</span>
                <div class="min-w-0 flex-1">
                  <p class="text-[14px]">
                    <span v-if="s.part_of_speech" class="mr-1.5 font-mono text-[12px] font-medium text-violet-600 italic dark:text-violet-300">{{ s.part_of_speech }}</span>
                    <span v-if="s.definition_zh" class="font-medium">{{ s.definition_zh }}</span>
                    <span v-if="s.definition_zh && s.definition_en" class="mx-1 text-stone-300 dark:text-stone-600">·</span>
                    <span v-if="s.definition_en" class="text-stone-500 italic dark:text-stone-400">{{ s.definition_en }}</span>
                  </p>
                  <p v-if="!s.definition_zh && !s.definition_en" class="text-stone-400 italic">（释义为空）</p>
                </div>
                <div class="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                  <button type="button" class="btn-icon !h-6.5 !w-6.5" title="上移" :disabled="i === 0" aria-label="上移" @click="moveSense(s, -1)">
                    <Icon name="chevron-up" :size="13" />
                  </button>
                  <button type="button" class="btn-icon !h-6.5 !w-6.5" title="下移" :disabled="i === orderedSenses.length - 1" aria-label="下移" @click="moveSense(s, 1)">
                    <Icon name="chevron-down" :size="13" />
                  </button>
                  <button type="button" class="btn-icon !h-6.5 !w-6.5" title="编辑" aria-label="编辑" @click="startEditSense(s)">
                    <Icon name="pencil" :size="13" />
                  </button>
                  <button
                    type="button"
                    class="btn-icon !h-6.5 !w-6.5"
                    :class="pendingDeleteId === s.id ? '!bg-red-100 !text-red-600 dark:!bg-red-950 dark:!text-red-300' : ''"
                    :title="pendingDeleteId === s.id ? '再次点击确认删除' : '删除'"
                    aria-label="删除义项"
                    @click="removeSense(s)"
                  >
                    <Icon name="trash" :size="13" />
                  </button>
                </div>
              </div>
            </template>
          </li>
        </ol>
        <p v-else class="py-2 text-sm text-stone-400 dark:text-stone-500">暂无义项</p>
      </section>

      <!-- 右列：状态 / 卡片 -->
      <div class="space-y-4">
        <section class="panel space-y-3 p-4">
          <h3 class="microlabel">个人状态</h3>
          <div class="flex items-center justify-between">
            <span class="text-sm text-stone-500 dark:text-stone-400">状态</span>
            <Tag :label="wordStatusMeta(word.status).label" :tone="wordStatusMeta(word.status).tone" />
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-stone-500 dark:text-stone-400">熟悉度</span>
            <span class="flex items-center gap-1.5">
              <FamiliarityDots :value="word.familiarity" interactive @select="setFamiliarity" />
              <button
                v-if="word.familiarity !== null"
                type="button"
                class="link text-[11px]"
                title="清除熟悉度"
                @click="clearFamiliarity"
              >
                清除
              </button>
            </span>
          </div>
          <div>
            <div class="mb-1 flex items-center justify-between">
              <span class="text-sm text-stone-500 dark:text-stone-400">备注</span>
              <button v-if="noteDirty" type="button" class="link text-xs" @click="saveNote">保存</button>
            </div>
            <textarea v-model="noteDraft" class="field !min-h-20 text-[13px]" placeholder="记忆线索、搭配、易错点…" @input="noteDirty = true" />
          </div>
        </section>

        <section class="panel space-y-2.5 p-4">
          <h3 class="microlabel">卡片</h3>
          <template v-if="word.card">
            <div class="flex items-center justify-between">
              <span class="text-sm text-stone-500 dark:text-stone-400">阶段</span>
              <Tag :label="cardStage(word.card).label" :tone="cardStage(word.card).tone" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-sm text-stone-500 dark:text-stone-400">下次复习</span>
              <span class="text-sm font-medium tabular-nums" :class="word.card.due_at && dueLabel(word.card.due_at) === '今天' ? 'text-amber-600 dark:text-amber-400' : ''">
                {{ dueLabel(word.card.due_at) ?? '未排期' }}
                <span v-if="word.card.due_at" class="ml-1 text-xs text-stone-400">{{ formatDateTime(word.card.due_at) }}</span>
              </span>
            </div>
            <div class="flex items-center justify-between text-[13px] text-stone-500 dark:text-stone-400">
              <span>难度</span>
              <span class="tabular-nums">{{ word.card.difficulty.toFixed(2) }}</span>
            </div>
            <div class="flex items-center justify-between text-[13px] text-stone-500 dark:text-stone-400">
              <span>稳定天数</span>
              <span class="tabular-nums">{{ word.card.stability_days }} 天</span>
            </div>
            <div class="flex items-center justify-between text-[13px] text-stone-500 dark:text-stone-400">
              <span>复习 / 遗忘</span>
              <span class="tabular-nums">{{ word.card.review_count }} 次 / {{ word.card.lapse_count }} 次</span>
            </div>
            <div class="flex items-center justify-between text-[13px] text-stone-500 dark:text-stone-400">
              <span>上次复习</span>
              <span class="tabular-nums">{{ relativeTime(word.card.last_review_at) }}</span>
            </div>
            <div class="flex items-center justify-between text-[13px] text-stone-500 dark:text-stone-400">
              <span>版本</span>
              <span class="font-mono tabular-nums">{{ word.card.version }}</span>
            </div>
            <p v-if="word.card.suspended_at" class="rounded bg-stone-100 px-2 py-1 text-xs text-stone-500 dark:bg-stone-800 dark:text-stone-400">
              挂起于 {{ formatDateTime(word.card.suspended_at) }}，暂不排期。
            </p>
          </template>
          <p v-else class="text-sm text-stone-400 dark:text-stone-500">
            还没有卡片。激活词条后系统会为它排期。
          </p>
        </section>

        <section class="panel space-y-2 p-4">
          <div class="flex items-center justify-between">
            <h3 class="microlabel">遇词历史</h3>
            <RouterLink to="/inbox" class="link text-xs">去收件箱</RouterLink>
          </div>
          <div v-if="encountersQuery.isPending.value" class="py-3 text-center text-xs text-stone-400">加载中…</div>
          <div v-else-if="encountersQuery.isError.value" class="py-3 text-center text-xs text-red-500" role="alert">
            {{ encountersQuery.error.value?.message }}
          </div>
          <template v-else>
            <div v-if="(encountersQuery.data.value ?? []).length === 0" class="py-2 text-sm text-stone-400 dark:text-stone-500">
              还没有遇词记录 —— 在阅读或听力里见到它时记一笔。
            </div>
            <ol v-else class="max-h-56 space-y-1.5 overflow-y-auto pr-1">
              <li v-for="e in encountersQuery.data.value" :key="e.id" class="flex flex-col gap-0.5 rounded bg-stone-50 px-2 py-1.5 text-[13px] dark:bg-stone-800/60">
                <div class="flex items-center gap-2">
                  <Tag v-if="e.type" :label="e.type" tone="violet" dot />
                  <span class="flex-1 truncate text-xs text-stone-500 dark:text-stone-400">{{ e.source?.name ?? '无来源' }}</span>
                  <span class="text-xs text-stone-400 dark:text-stone-500">{{ relativeTime(e.encountered_at ?? e.created_at) }}</span>
                </div>
                <p v-if="e.surface_text" class="truncate font-medium">{{ e.surface_text }}</p>
                <p v-if="e.context" class="truncate text-stone-600 italic dark:text-stone-300">“{{ e.context }}”</p>
                <p v-if="e.note" class="truncate text-xs text-stone-400 dark:text-stone-500">备注：{{ e.note }}</p>
              </li>
            </ol>
            <form class="space-y-1.5 border-t border-stone-200 pt-2.5 dark:border-stone-800" @submit.prevent="addEncounter">
              <input v-model="encDraft.surfaceText" class="field !h-8 text-[13px]" placeholder="见到的表面形式（可选）" />
              <input v-model="encDraft.context" class="field !h-8 text-[13px]" placeholder="上下文句子（可选）" />
              <div class="flex gap-1.5">
                <input v-model="encDraft.type" class="field !h-8 w-24 text-[13px]" placeholder="类型" list="enc-types" />
                <div class="min-w-0 flex-1">
                  <SourceSelect v-model="encDraft.sourceId" :sources="sources ?? []" :allow-empty="false" />
                </div>
                <button type="submit" class="btn-ghost btn-sm shrink-0" :disabled="addingEncounter">
                  <Icon name="plus" :size="13" />记录
                </button>
              </div>
              <datalist id="enc-types">
                <option v-for="t in ENC_TYPES" :key="t" :value="t" />
              </datalist>
            </form>
          </template>
        </section>
      </div>
    </div>

    <!-- personal_phonetic 编辑 -->
    <section class="panel flex flex-wrap items-center gap-2 px-4 py-3">
      <span class="microlabel">个人音标</span>
      <div class="flex items-center gap-2">
        <input v-model="phoneticDraft" class="field !h-8 w-44 font-mono text-[13px]" placeholder="ɪˈfem(ə)rəl（不带斜杠）" spellcheck="false" />
        <button type="button" class="btn-ghost btn-sm" :disabled="!phoneticDirty" @click="savePhonetic">保存</button>
      </div>
    </section>
  </div>
</template>
