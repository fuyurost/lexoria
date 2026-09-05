<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';
import Icon from './Icon.vue';

const route = useRoute();
const auth = useAuthStore();
const ui = useUiStore();

const emit = defineEmits<{ menu: [] }>();

const title = computed(() => route.meta.title ?? '');
const initials = computed(() => (auth.user?.username ?? '?').slice(0, 2).toUpperCase());
</script>

<template>
  <header
    class="sticky top-0 z-30 flex h-12 items-center gap-2 border-b border-stone-200 bg-stone-100/90 px-3 backdrop-blur-sm sm:px-5 dark:border-stone-800 dark:bg-stone-950/85"
  >
    <button type="button" class="btn-icon lg:hidden" aria-label="打开菜单" @click="emit('menu')">
      <Icon name="menu" :size="17" />
    </button>
    <h1 class="min-w-0 flex-1 truncate text-[15px] font-semibold tracking-tight">{{ title }}</h1>

    <button
      type="button"
      class="btn-primary btn-sm mr-1 hidden sm:inline-flex"
      aria-label="快速添加"
      @click="ui.quickAddOpen = true"
    >
      <Icon name="plus" :size="14" />快速添加
      <span class="kbd !border-white/30 !bg-white/15 !text-white/80">Ctrl⇧A</span>
    </button>

    <button type="button" class="btn-icon" :aria-label="ui.isDark ? '切换到浅色' : '切换到深色'" @click="ui.toggleTheme()">
      <Icon :name="ui.isDark ? 'sun' : 'moon'" :size="16" />
    </button>

    <div class="ml-1 flex items-center gap-2 border-l border-stone-200 pl-3 dark:border-stone-800">
      <span
        class="flex h-6.5 w-6.5 items-center justify-center rounded-full bg-orange-100 text-[10px] font-bold text-orange-800 dark:bg-orange-950 dark:text-orange-300"
        :title="auth.user?.email"
      >
        {{ initials }}
      </span>
      <span class="hidden text-[13px] font-medium sm:block">{{ auth.user?.username }}</span>
    </div>
  </header>
</template>
