import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

declare module 'vue-router' {
  interface RouteMeta {
    /** Shown in the top bar & document title. */
    title: string;
    /** Route is reachable while logged out (login/register). */
    public?: boolean;
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { title: '注册', public: true },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '仪表盘' },
  },
  {
    path: '/inbox',
    name: 'inbox',
    component: () => import('@/views/InboxView.vue'),
    meta: { title: '收件箱' },
  },
  {
    path: '/words',
    name: 'words',
    component: () => import('@/views/WordsView.vue'),
    meta: { title: '词库' },
  },
  {
    path: '/words/:id',
    name: 'word-detail',
    component: () => import('@/views/WordDetailView.vue'),
    meta: { title: '词条详情' },
  },
  {
    path: '/review',
    name: 'review',
    component: () => import('@/views/ReviewView.vue'),
    meta: { title: '复习' },
  },
  {
    path: '/sources',
    name: 'sources',
    component: () => import('@/views/SourcesView.vue'),
    meta: { title: '来源' },
  },
  {
    path: '/daily-sheets',
    name: 'daily-sheets',
    component: () => import('@/views/DailySheetsView.vue'),
    meta: { title: '练习纸' },
  },
  {
    path: '/daily-sheets/:id',
    name: 'daily-sheet-detail',
    component: () => import('@/views/DailySheetDetailView.vue'),
    meta: { title: '练习纸详情' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '设置' },
  },
  { path: '/', redirect: { name: 'dashboard' } },
  { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!to.meta.public && !auth.loggedIn) {
    const user = await auth.ensureSession();
    if (!user) {
      return { name: 'login', query: { redirect: to.fullPath } };
    }
  }
  return true;
});

router.afterEach((to) => {
  document.title = to.meta.public ? `${to.meta.title} · Lexiora` : `${to.meta.title} · Lexiora`;
});
