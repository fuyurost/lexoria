<script setup lang="ts">
import { watch } from 'vue';
import Icon from './Icon.vue';

const props = withDefaults(defineProps<{ open: boolean; title?: string; width?: string }>(), {
  open: false,
  width: 'max-w-lg',
});

const emit = defineEmits<{ close: [] }>();

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    e.stopPropagation();
    emit('close');
  }
}

function lockBody(lock: boolean): void {
  document.body.style.overflow = lock ? 'hidden' : '';
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      lockBody(true);
      window.addEventListener('keydown', onKeydown, true);
    } else {
      lockBody(false);
      window.removeEventListener('keydown', onKeydown, true);
    }
  },
  { immediate: true },
);
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="open"
        class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-stone-950/45 p-4 pt-[10vh] dark:bg-black/60"
        role="presentation"
        @mousedown.self="emit('close')"
      >
        <div
          class="panel w-full shadow-xl"
          :class="width"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
        >
          <header v-if="title" class="flex items-center justify-between border-b border-stone-200 px-4 py-2.5 dark:border-stone-800">
            <h2 class="text-sm font-semibold">{{ title }}</h2>
            <button type="button" class="btn-icon" aria-label="关闭" @click="emit('close')">
              <Icon name="x" :size="16" />
            </button>
          </header>
          <div class="px-4 py-4">
            <slot />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.16s ease;
}
.modal-fade-enter-active > div,
.modal-fade-leave-active > div {
  transition: transform 0.16s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
.modal-fade-enter-from > div,
.modal-fade-leave-to > div {
  transform: translateY(-6px) scale(0.99);
}
</style>
