<script setup lang="ts">
import { computed } from 'vue';
import { RouterView, useRoute } from 'vue-router';
import { useUiStore } from '@/stores/ui';
import { useSources } from '@/api/sources';
import Icon from './Icon.vue';
import QuickAddDialog from './QuickAddDialog.vue';
import SideNav from './SideNav.vue';
import TopBar from './TopBar.vue';

const ui = useUiStore();
const route = useRoute();
const { data: sources } = useSources(false);
const routeKey = computed(() => route.fullPath);
</script>

<template>
  <div class="flex min-h-dvh">
    <!-- Desktop sidebar -->
    <aside class="sticky top-0 hidden h-dvh shrink-0 lg:block">
      <SideNav />
    </aside>

    <!-- Mobile drawer -->
    <Teleport to="body">
      <Transition name="drawer">
        <div v-if="ui.sidebarOpen" class="fixed inset-0 z-40 lg:hidden">
          <div class="absolute inset-0 bg-stone-950/45 dark:bg-black/60" @click="ui.sidebarOpen = false" />
          <aside class="absolute inset-y-0 left-0 shadow-xl">
            <SideNav @navigate="ui.sidebarOpen = false" />
          </aside>
        </div>
      </Transition>
    </Teleport>

    <div class="flex min-w-0 flex-1 flex-col">
      <TopBar @menu="ui.sidebarOpen = true" />
      <main class="mx-auto w-full max-w-6xl flex-1 px-3 py-5 sm:px-6">
        <RouterView :key="routeKey" />
      </main>
      <footer class="flex items-center gap-1.5 border-t border-stone-200 px-6 py-2 text-[11px] text-stone-400 dark:border-stone-800 dark:text-stone-600 lg:hidden">
        <Icon name="keyboard" :size="12" />
        <span>Ctrl+Shift+A 快速添加</span>
      </footer>
    </div>

    <QuickAddDialog :open="ui.quickAddOpen" :sources="sources ?? []" @close="ui.quickAddOpen = false" />
  </div>
</template>

<style scoped>
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.16s ease;
}
.drawer-enter-active aside,
.drawer-leave-active aside {
  transition: transform 0.16s ease;
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from aside,
.drawer-leave-to aside {
  transform: translateX(-100%);
}
</style>
