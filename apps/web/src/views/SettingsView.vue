<script setup lang="ts">
import { reactive, ref, watchEffect } from 'vue';
import { DEFAULT_USER_SETTINGS, type PaperSize, type SheetColumns, type SheetTemplate } from '@lexoria/api-client';
import { useSettings, useUpdateSettings } from '@/api/settings';
import { columnOptions, paperSizes, sheetTemplates } from '@/api/sheets';
import { useUiStore } from '@/stores/ui';
import { useAuthStore } from '@/stores/auth';
import { timezoneOptions } from '@/lib/format';
import { messageOf } from '@lexoria/api-client';
import StateBlock from '@/components/StateBlock.vue';
import Icon from '@/components/Icon.vue';

const settingsQuery = useSettings();
const updateSettings = useUpdateSettings();
const ui = useUiStore();
const auth = useAuthStore();

const draft = reactive({
  timezone: DEFAULT_USER_SETTINGS.timezone,
  daily_template: DEFAULT_USER_SETTINGS.daily_template as SheetTemplate,
  paper_size: DEFAULT_USER_SETTINGS.paper_size as PaperSize,
  columns: DEFAULT_USER_SETTINGS.columns as SheetColumns,
  review_count: DEFAULT_USER_SETTINGS.review_count,
  new_count: DEFAULT_USER_SETTINGS.new_count,
});

const tzOptions = timezoneOptions();
const dirty = ref(false);
const saved = ref('');
const error = ref('');

watchEffect(() => {
  const s = settingsQuery.data.value;
  if (!s) return;
  draft.timezone = s.timezone;
  draft.daily_template = s.daily_template;
  draft.paper_size = s.paper_size;
  draft.columns = s.columns;
  draft.review_count = s.review_count;
  draft.new_count = s.new_count;
  dirty.value = false;
});

function markDirty(): void {
  dirty.value = true;
  saved.value = '';
}

function toInt(v: string, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? Math.trunc(n) : fallback;
}

async function save(): Promise<void> {
  error.value = '';
  saved.value = '';
  try {
    await updateSettings.mutateAsync({
      timezone: draft.timezone,
      daily_template: draft.daily_template,
      paper_size: draft.paper_size,
      columns: draft.columns,
      review_count: draft.review_count,
      new_count: draft.new_count,
    });
    dirty.value = false;
    saved.value = '设置已保存';
  } catch (err) {
    error.value = messageOf(err);
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-5">
    <StateBlock
      v-if="settingsQuery.isPending.value"
      state="loading"
      title="正在读取设置…"
    />
    <StateBlock
      v-else-if="settingsQuery.isError.value"
      state="error"
      :hint="settingsQuery.error.value?.message"
      @retry="void settingsQuery.refetch()"
    />
    <template v-else>
      <section class="panel divide-y divide-stone-200 dark:divide-stone-800">
        <div class="flex items-center justify-between px-4 py-3">
          <div>
            <h2 class="text-sm font-semibold">账户</h2>
            <p class="text-xs text-stone-500 dark:text-stone-400">账号信息由服务端管理，可在对应入口修改</p>
          </div>
          <button type="button" class="btn-ghost-danger btn-sm" @click="void auth.logout()">
            <Icon name="logout" :size="13" />退出登录
          </button>
        </div>
        <dl class="grid gap-3 px-4 py-3 sm:grid-cols-2">
          <div>
            <dt class="microlabel">用户名</dt>
            <dd class="mt-0.5 text-sm font-medium">{{ auth.user?.username }}</dd>
          </div>
          <div>
            <dt class="microlabel">邮箱</dt>
            <dd class="mt-0.5 text-sm font-medium">{{ auth.user?.email }}</dd>
          </div>
        </dl>
      </section>

      <section class="panel divide-y divide-stone-200 dark:divide-stone-800">
        <div class="px-4 py-3">
          <h2 class="text-sm font-semibold">练习纸默认设置</h2>
          <p class="text-xs text-stone-500 dark:text-stone-400">「生成练习纸」页面打开时会预填这些值</p>
        </div>

        <div class="grid gap-3 px-4 py-3 sm:grid-cols-2">
          <div>
            <label class="microlabel mb-1 block" for="set-tz">时区</label>
            <select id="set-tz" class="field" :value="draft.timezone" @change="markDirty(); draft.timezone = ($event.target as HTMLSelectElement).value">
              <option v-for="tz in tzOptions" :key="tz" :value="tz">{{ tz }}</option>
            </select>
          </div>
          <div>
            <span class="microlabel mb-1 block">默认模板</span>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="t in sheetTemplates"
                :key="t.value"
                type="button"
                class="rounded-md border px-2 py-1.5 text-[13px] font-medium transition-colors"
                :class="draft.daily_template === t.value ? 'border-orange-500 bg-orange-50 text-orange-800 dark:bg-orange-950/50 dark:text-orange-300' : 'border-stone-300 text-stone-600 hover:border-stone-400 dark:border-stone-600 dark:text-stone-300'"
                @click="markDirty(); draft.daily_template = t.value"
              >
                {{ t.label }}
              </button>
            </div>
          </div>
          <div>
            <label class="microlabel mb-1 block" for="set-paper">默认纸张</label>
            <select id="set-paper" class="field" :value="draft.paper_size" @change="markDirty(); draft.paper_size = ($event.target as HTMLSelectElement).value as PaperSize">
              <option v-for="p in paperSizes" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
          </div>
          <div>
            <span class="microlabel mb-1 block">默认栏数</span>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="c in columnOptions"
                :key="c.value"
                type="button"
                class="rounded-md border px-2 py-1.5 text-[13px] font-medium transition-colors"
                :class="draft.columns === c.value ? 'border-orange-500 bg-orange-50 text-orange-800 dark:bg-orange-950/50 dark:text-orange-300' : 'border-stone-300 text-stone-600 hover:border-stone-400 dark:border-stone-600 dark:text-stone-300'"
                @click="markDirty(); draft.columns = c.value"
              >
                {{ c.label }}
              </button>
            </div>
          </div>
          <div>
            <label class="microlabel mb-1 block" for="set-review">默认复习词数</label>
            <input id="set-review" type="number" min="0" max="100" class="field" :value="draft.review_count" @input="markDirty(); draft.review_count = toInt(($event.target as HTMLInputElement).value, 0)" />
          </div>
          <div>
            <label class="microlabel mb-1 block" for="set-new">默认新词数</label>
            <input id="set-new" type="number" min="0" max="100" class="field" :value="draft.new_count" @input="markDirty(); draft.new_count = toInt(($event.target as HTMLInputElement).value, 0)" />
          </div>
        </div>

        <div class="flex items-center justify-between px-4 py-3">
          <p v-if="error" class="text-[13px] text-red-600 dark:text-red-400">{{ error }}</p>
          <p v-else-if="saved" class="text-[13px] text-emerald-600 dark:text-emerald-400">{{ saved }}</p>
          <span v-else />
          <button type="button" class="btn-primary" :disabled="!dirty || updateSettings.isPending.value" @click="save">
            <Icon name="check" :size="14" />保存设置
          </button>
        </div>
      </section>

      <section class="panel px-4 py-3">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-sm font-semibold">外观</h2>
            <p class="text-xs text-stone-500 dark:text-stone-400">主题偏好保存在本机</p>
          </div>
          <button type="button" class="btn-ghost" @click="ui.toggleTheme()">
            <Icon :name="ui.isDark ? 'sun' : 'moon'" :size="14" />
            {{ ui.isDark ? '深色模式' : '浅色模式' }}
          </button>
        </div>
      </section>
    </template>
  </div>
</template>
