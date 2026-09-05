<script setup lang="ts">
import { computed } from 'vue';
import Icon from './Icon.vue';

const props = defineProps<{ page: number; pageSize: number; total: number; showSize?: boolean }>();

const emit = defineEmits<{ page: [value: number]; pageSize: [value: number] }>();

const pages = computed(() => (props.total === 0 ? 1 : Math.max(1, Math.ceil(props.total / props.pageSize))));
const canPrev = computed(() => props.page > 1);
const canNext = computed(() => props.page < pages.value);
</script>

<template>
  <div class="flex items-center justify-between gap-3 text-[13px] text-stone-500 dark:text-stone-400">
    <div class="flex items-center gap-3">
      <label v-if="showSize" class="flex items-center gap-1.5">
        每页
        <select class="field-sm !h-7 w-auto" :value="pageSize" @change="emit('pageSize', Number(($event.target as HTMLSelectElement).value))">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
      </label>
      <span>共 {{ total }} 条</span>
    </div>
    <div class="flex items-center gap-1">
      <button type="button" class="btn-ghost btn-sm" :disabled="!canPrev" aria-label="上一页" @click="emit('page', page - 1)">
        <Icon name="chevron-left" :size="14" />
      </button>
      <span class="px-1.5 tabular-nums">第 {{ page }} / {{ pages }} 页</span>
      <button type="button" class="btn-ghost btn-sm" :disabled="!canNext" aria-label="下一页" @click="emit('page', page + 1)">
        <Icon name="chevron-right" :size="14" />
      </button>
    </div>
  </div>
</template>
