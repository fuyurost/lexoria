<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';
import { useStats } from '@/api/stats';
import Icon, { type IconName } from './Icon.vue';

const route = useRoute();
const auth = useAuthStore();
const ui = useUiStore();

const statsQuery = useStats();
const stats = computed(() => statsQuery.data.value);

interface NavEntry {
  to: string;
  label: string;
  icon: IconName;
  badge?: () => number;
}

const nav: NavEntry[] = [
  { to: '/dashboard', label: '仪表盘', icon: 'dashboard' },
  { to: '/inbox', label: '收件箱', icon: 'inbox', badge: () => stats.value?.inbox_open ?? 0 },
  { to: '/words', label: '词库', icon: 'book' },
  { to: '/review', label: '复习', icon: 'repeat', badge: () => stats.value?.due_today ?? 0 },
  { to: '/sources', label: '来源', icon: 'folder' },
  { to: '/daily-sheets', label: '练习纸', icon: 'file' },
  { to: '/settings', label: '设置', icon: 'settings' },
];

const emit = defineEmits<{ navigate: [] }>();
const collapsed = computed(() => ui.sidebarCollapsed);

function badgeOf(entry: NavEntry): number {
  return entry.badge ? entry.badge() : 0;
}

function isActive(entry: NavEntry): boolean {
  if (route.path === entry.to) return true;
  if (entry.to === '/words') return route.path.startsWith('/words/');
  return route.path.startsWith(`${entry.to}/`);
}

async function onLogout(): Promise<void> {
  await auth.logout();
  emit('navigate');
}
</script>

<template>
  <nav
    class="flex h-full flex-col border-r border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900"
    :class="collapsed ? 'w-14' : 'w-56'"
    aria-label="主导航"
  >
    <div class="flex h-13 items-center gap-2 px-3 py-3" :class="collapsed ? 'justify-center' : ''">
      <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-orange-600 text-[15px] font-black text-white dark:bg-orange-500 dark:text-stone-950">
        L
      </span>
      <span v-if="!collapsed" class="truncate text-[15px] font-bold tracking-tight">Lexiora</span>
    </div>

    <button
      type="button"
      class="btn-icon mx-2 mb-1 !w-auto !justify-start !px-2 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300"
      :aria-label="collapsed ? '展开侧栏' : '收起侧栏'"
      @click="ui.sidebarCollapsed = !ui.sidebarCollapsed"
    >
      <Icon name="chevron-left" :size="15" :class="collapsed ? 'rotate-180' : ''" />
      <span v-if="!collapsed" class="text-[11px] tracking-wide">收起侧栏</span>
    </button>

    <ul class="mt-1 flex-1 space-y-0.5 overflow-y-auto px-2">
      <li v-for="entry in nav" :key="entry.to">
        <RouterLink
          :to="entry.to"
          class="group flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13.5px] font-medium text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-stone-800 dark:hover:text-white"
          :class="[
            isActive(entry) ? 'bg-orange-50 text-orange-800 dark:bg-orange-950/40 dark:text-orange-300' : '',
            collapsed ? 'justify-center px-0' : '',
          ]"
          :title="collapsed ? entry.label : undefined"
          :aria-label="entry.label"
          @click="emit('navigate')"
        >
          <span class="relative">
            <Icon :name="entry.icon" :size="16" class="shrink-0" />
            <span
              v-if="collapsed && badgeOf(entry) > 0"
              class="absolute -top-1 -right-1.5 h-1.5 w-1.5 rounded-full bg-orange-500"
            />
          </span>
          <span v-if="!collapsed" class="min-w-0 flex-1 truncate">{{ entry.label }}</span>
          <span
            v-if="!collapsed && badgeOf(entry) > 0"
            class="rounded-full bg-orange-600/10 px-1.5 text-[10.5px] leading-4 font-bold text-orange-700 tabular-nums dark:bg-orange-400/15 dark:text-orange-300"
          >
            {{ badgeOf(entry) > 99 ? '99+' : badgeOf(entry) }}
          </span>
        </RouterLink>
      </li>
    </ul>

    <div v-if="!collapsed" class="border-t border-stone-200 px-3 py-3 text-[11px] leading-5 text-stone-400 dark:border-stone-800 dark:text-stone-500">
      <p><span class="kbd mr-1">Ctrl</span><span class="kbd mr-1">Shift</span><span class="kbd">A</span> 快速添加</p>
      <p class="mt-1">g + 字母跳转 · / 搜索词库</p>
    </div>
    <div v-else class="border-t border-stone-200 py-2 text-center dark:border-stone-800">
      <span class="kbd">g</span>
    </div>

    <div class="border-t border-stone-200 p-2 dark:border-stone-800" :class="collapsed ? 'flex justify-center' : ''">
      <button
        type="button"
        class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
        :title="collapsed ? auth.user?.username : undefined"
        @click="onLogout"
      >
        <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-stone-200 text-[11px] font-bold text-stone-600 dark:bg-stone-700 dark:text-stone-200">
          {{ auth.user?.username?.slice(0, 1).toUpperCase() ?? '?' }}
        </span>
        <span v-if="!collapsed" class="min-w-0 flex-1 truncate">{{ auth.user?.username }}</span>
        <Icon v-if="!collapsed" name="logout" :size="13" class="text-stone-400" />
      </button>
    </div>
  </nav>
</template>
