<script setup lang="ts">
/** 来源：type ∈ school|ielts|cet4|exam|reading|manual|other；归档用 PATCH { archived }。 */
import { computed, reactive, ref } from 'vue';
import { messageOf, type Source, type SourceCreate, type SourceType } from '@lexoria/api-client';
import { useCreateSource, useSources, useUpdateSource } from '@/api/sources';
import { formatDate, relativeTime } from '@/lib/format';
import { sourceTypeLabel, sourceTypeTone, SOURCE_TYPE_OPTIONS } from '@/lib/statusMeta';
import { toastError, toastSuccess } from '@/lib/toast';
import Icon from '@/components/Icon.vue';
import StateBlock from '@/components/StateBlock.vue';
import Tag from '@/components/Tag.vue';

const sourcesQuery = useSources(true);
const createSource = useCreateSource();
const updateSource = useUpdateSource();

const showCreate = ref(false);
const form = reactive<{ name: string; type: SourceType | ''; description: string }>({ name: '', type: '', description: '' });
const formError = ref('');
const creating = ref(false);

const all = computed(() => sourcesQuery.data.value ?? []);
const active = computed(() => all.value.filter((s) => !s.archived_at));
const archived = computed(() => all.value.filter((s) => Boolean(s.archived_at)));

const editingId = ref<string | null>(null);
const editDraft = reactive<{ name: string; type: SourceType | ''; description: string }>({ name: '', type: '', description: '' });

function startEdit(s: Source): void {
  editingId.value = s.id;
  editDraft.name = s.name;
  editDraft.type = s.type ?? '';
  editDraft.description = s.description ?? '';
}

async function saveEdit(s: Source): Promise<void> {
  if (!editDraft.name.trim()) return;
  try {
    await updateSource.mutateAsync({
      id: s.id,
      patch: {
        name: editDraft.name.trim(),
        type: editDraft.type === '' ? undefined : (editDraft.type as SourceType),
        description: editDraft.description.trim() || null,
      },
    });
    toastSuccess('来源已更新');
    editingId.value = null;
  } catch (err) {
    toastError(messageOf(err));
  }
}

async function toggleArchive(s: Source): Promise<void> {
  try {
    await updateSource.mutateAsync({ id: s.id, patch: { archived: !s.archived_at } });
    toastSuccess(s.archived_at ? '已恢复来源' : '已归档来源');
  } catch (err) {
    toastError(messageOf(err));
  }
}

async function create(): Promise<void> {
  formError.value = '';
  if (!form.name.trim()) {
    formError.value = '名称不能为空';
    return;
  }
  creating.value = true;
  try {
    await createSource.mutateAsync({
      name: form.name.trim(),
      type: form.type === '' ? undefined : (form.type as SourceType),
      description: form.description.trim() || null,
    });
    toastSuccess(`来源「${form.name.trim()}」已创建`);
    form.name = '';
    form.type = '';
    form.description = '';
    showCreate.value = false;
  } catch (err) {
    formError.value = messageOf(err);
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <p class="text-[13px] text-stone-500 dark:text-stone-400">共 {{ all.length }} 个来源（{{ active.length }} 个使用中）</p>
      <button v-if="!showCreate" type="button" class="btn-primary" @click="showCreate = true">
        <Icon name="plus" :size="14" />新增来源
      </button>
    </div>

    <form v-if="showCreate" class="panel space-y-3 p-4" @submit.prevent="create">
      <div class="grid gap-3 sm:grid-cols-[1fr_180px]">
        <div>
          <label class="microlabel mb-1 block" for="src-name">名称</label>
          <input id="src-name" v-model="form.name" class="field" placeholder="如：《人类简史》 / The Economist" />
        </div>
        <div>
          <label class="microlabel mb-1 block" for="src-type">类型</label>
          <select id="src-type" v-model="form.type" class="field">
            <option v-for="o in SOURCE_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>
      </div>
      <div>
        <label class="microlabel mb-1 block" for="src-desc">描述（可选）</label>
        <textarea id="src-desc" v-model="form.description" class="field !min-h-16" placeholder="这本书 / 这份材料大致是什么？" />
      </div>
      <p v-if="formError" class="text-[13px] text-red-600 dark:text-red-400">{{ formError }}</p>
      <div class="flex justify-end gap-2">
        <button type="button" class="btn-ghost" :disabled="creating" @click="showCreate = false">取消</button>
        <button type="submit" class="btn-primary" :disabled="creating">{{ creating ? '创建中…' : '创建' }}</button>
      </div>
    </form>

    <StateBlock v-if="sourcesQuery.isPending.value" state="loading" title="正在加载来源…" />
    <StateBlock v-else-if="sourcesQuery.isError.value" state="error" title="来源加载失败" :hint="sourcesQuery.error.value?.message" @retry="void sourcesQuery.refetch()" />
    <template v-else>
      <section v-if="active.length" class="panel divide-y divide-stone-100 dark:divide-stone-800">
        <div v-for="s in active" :key="s.id" class="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
          <template v-if="editingId === s.id">
            <div class="grid flex-1 gap-2 sm:grid-cols-[1fr_160px]">
              <input v-model="editDraft.name" class="field" aria-label="名称" />
              <select v-model="editDraft.type" class="field" aria-label="类型">
                <option v-for="o in SOURCE_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <input v-model="editDraft.description" class="field flex-1" placeholder="描述" aria-label="描述" />
            <div class="flex gap-1.5">
              <button type="button" class="btn-primary btn-sm" :disabled="!editDraft.name.trim()" @click="saveEdit(s)">
                <Icon name="check" :size="13" />保存
              </button>
              <button type="button" class="btn-ghost btn-sm" @click="editingId = null">取消</button>
            </div>
          </template>
          <template v-else>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-sm font-semibold">{{ s.name }}</span>
                <Tag :label="sourceTypeLabel(s.type)" :tone="sourceTypeTone(s.type)" />
              </div>
              <p class="mt-0.5 truncate text-xs text-stone-500 dark:text-stone-400">
                {{ s.description || '（无描述）' }} · 创建于 {{ relativeTime(s.created_at) }}
              </p>
            </div>
            <div class="flex shrink-0 items-center gap-1">
              <button type="button" class="btn-icon" :title="`编辑 ${s.name}`" aria-label="编辑" @click="startEdit(s)">
                <Icon name="pencil" :size="14" />
              </button>
              <button type="button" class="btn-icon" :title="`归档 ${s.name}`" aria-label="归档" @click="toggleArchive(s)">
                <Icon name="folder" :size="14" />
              </button>
            </div>
          </template>
        </div>
      </section>

      <div v-else class="panel">
        <StateBlock state="empty" title="还没有来源" hint="把正在读的书、备考材料或追的剧记下来，捕获单词时挂上来源。">
          <button type="button" class="btn-primary" @click="showCreate = true">
            <Icon name="plus" :size="14" />创建第一个来源
          </button>
        </StateBlock>
      </div>

      <section v-if="archived.length" class="panel">
        <h3 class="microlabel border-b border-stone-200 px-4 py-2.5 dark:border-stone-800">已归档</h3>
        <ul class="divide-y divide-stone-100 dark:divide-stone-800">
          <li v-for="s in archived" :key="s.id" class="flex items-center gap-2 px-4 py-2.5 text-sm">
            <span class="min-w-0 flex-1 truncate text-stone-500 dark:text-stone-400">
              {{ s.name }}
              <span class="ml-2 text-xs text-stone-400 dark:text-stone-600">归档于 {{ formatDate(s.archived_at) }}</span>
            </span>
            <button type="button" class="link text-xs" @click="toggleArchive(s)">恢复</button>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
