<script setup lang="ts">
import { useToasts, dismiss } from '@/lib/toast';
import Icon, { type IconName } from './Icon.vue';

const toasts = useToasts();

type ToneStyle = { bar: string; icon: string; glyph: IconName };
const TONES: Record<string, ToneStyle> = {
  success: { bar: 'bg-emerald-500', icon: 'text-emerald-600 dark:text-emerald-400', glyph: 'check' },
  error: { bar: 'bg-red-500', icon: 'text-red-600 dark:text-red-400', glyph: 'alert' },
  info: { bar: 'bg-stone-400 dark:bg-stone-500', icon: 'text-stone-500 dark:text-stone-400', glyph: 'info' },
};

function toneOf(kind: string): ToneStyle {
  const found = TONES[kind];
  if (found) return found;
  return TONES.info as ToneStyle;
}

</script>

<template>
  <Teleport to="body">
    <div class="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-80 flex-col gap-2">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts.list"
          :key="t.id"
          class="pointer-events-auto relative flex items-start gap-2.5 overflow-hidden rounded-md border border-stone-200 bg-white py-2.5 pr-2 pl-3 text-sm shadow-lg dark:border-stone-700 dark:bg-stone-900"
          role="status"
        >
          <span class="absolute inset-y-0 left-0 w-0.5" :class="toneOf(t.kind).bar" />
          <Icon :name="toneOf(t.kind).glyph" :size="15" class="mt-0.5 shrink-0" :class="toneOf(t.kind).icon" />
          <span class="min-w-0 flex-1 break-words text-stone-700 dark:text-stone-200">{{ t.text }}</span>
          <button type="button" class="btn-icon !h-6 !w-6 !p-0" aria-label="关闭通知" @click="dismiss(t.id)">
            <Icon name="x" :size="13" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.18s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
