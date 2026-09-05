<script setup lang="ts">
import { computed } from 'vue';
import { TONE_STYLES, type Tone } from '@/lib/statusMeta';

const props = withDefaults(defineProps<{ label: string; tone?: Tone; dot?: boolean }>(), {
  tone: 'stone',
  dot: true,
});

const cls = computed(() => TONE_STYLES[props.tone]);
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2 py-px text-[11.5px] leading-5 font-medium ring-1 ring-inset"
    :class="cls.chip"
  >
    <span v-if="dot" class="h-1.5 w-1.5 rounded-full" :class="cls.dot" />
    {{ label }}
  </span>
</template>
