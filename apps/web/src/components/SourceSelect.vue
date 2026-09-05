<script setup lang="ts">
import { computed } from 'vue';
import type { Source } from '@lexoria/api-client';

const props = withDefaults(
  defineProps<{
    modelValue: string | null;
    sources: Source[];
    placeholder?: string;
    disabled?: boolean;
    allowEmpty?: boolean;
  }>(),
  { placeholder: '选择来源…', disabled: false, allowEmpty: true },
);

const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>();

const selected = computed(() => props.modelValue ?? '');

function onChange(e: Event): void {
  const v = (e.target as HTMLSelectElement).value;
  emit('update:modelValue', v === '' ? null : v);
}
</script>

<template>
  <select class="field" :value="selected" :disabled="disabled || sources.length === 0" @change="onChange">
    <option v-if="allowEmpty" value="">暂无来源</option>
    <option v-for="s in sources" :key="s.id" :value="s.id">{{ s.name }}</option>
  </select>
  <p v-if="!disabled && sources.length === 0" class="mt-1 text-xs text-stone-400">先在「来源」里创建来源，即可在此选择。</p>
</template>
