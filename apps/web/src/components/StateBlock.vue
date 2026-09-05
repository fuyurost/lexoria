<script setup lang="ts">
import Icon from './Icon.vue';

withDefaults(defineProps<{ state: 'loading' | 'error' | 'empty'; title?: string; hint?: string }>(), {
  title: '',
  hint: '',
});

const emit = defineEmits<{ retry: [] }>();
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
    <div
      v-if="state === 'loading'"
      class="h-6 w-6 animate-spin rounded-full border-2 border-stone-300 border-t-orange-600 dark:border-stone-700 dark:border-t-orange-500"
      role="status"
      aria-label="加载中"
    />
    <template v-else>
      <span
        class="flex h-10 w-10 items-center justify-center rounded-full"
        :class="state === 'error' ? 'bg-red-100 text-red-600 dark:bg-red-950/60 dark:text-red-400' : 'bg-stone-200/70 text-stone-500 dark:bg-stone-800 dark:text-stone-400'"
      >
        <Icon v-if="state === 'error'" name="alert" :size="18" />
        <Icon v-else name="list" :size="18" />
      </span>
    </template>
    <div class="space-y-1">
      <p v-if="title" class="text-sm font-medium">{{ title }}</p>
      <p v-if="hint" class="max-w-sm text-[13px] text-stone-500 dark:text-stone-400">{{ hint }}</p>
      <slot />
    </div>
    <button v-if="state === 'error'" type="button" class="btn-ghost" @click="emit('retry')">
      <Icon name="refresh" :size="14" />重试
    </button>
  </div>
</template>
