<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{ value: number | null; max?: number; interactive?: boolean }>(),
  { max: 5, interactive: false },
);

const emit = defineEmits<{ select: [value: number] }>();

const filled = computed(() => {
  const v = props.value;
  if (v === null || Number.isNaN(v)) return 0;
  return Math.min(props.max, Math.max(0, Math.trunc(v)));
});
</script>

<template>
  <span
    class="inline-flex items-center gap-[3px]"
    role="img"
    :aria-label="value === null ? '未评估熟悉度' : `熟悉度 ${value}/${max}`"
    :title="value === null ? '未评估' : `熟悉度 ${value}/5`"
  >
    <button
      v-for="n in max"
      :key="n"
      type="button"
      :disabled="!interactive"
      class="h-3 w-3 rounded-full transition-colors"
      :class="[
        n <= filled ? 'bg-amber-500' : 'bg-stone-300 dark:bg-stone-600',
        interactive ? 'cursor-pointer hover:scale-110' : 'cursor-default',
      ]"
      :aria-label="`设为 ${n}`"
      @click="interactive && emit('select', n)"
    />
  </span>
</template>
