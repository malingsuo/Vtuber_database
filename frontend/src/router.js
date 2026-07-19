import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('./views/LoginView.vue') },
  { path: '/', component: () => import('./views/QueryView.vue') },
  { path: '/events/new', component: () => import('./views/NewEventView.vue') },
  { path: '/events/:id', component: () => import('./views/EventDetailView.vue') },
  { path: '/reports', component: () => import('./views/ReportView.vue') },
  { path: '/forecast', component: () => import('./views/ForecastView.vue') },
  { path: '/settings', component: () => import('./views/SettingsView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 沒登入一律導向登入頁；已登入就別再看登入頁
router.beforeEach((to) => {
  const hasToken = !!localStorage.getItem('token')
  if (to.path !== '/login' && !hasToken) return '/login'
  if (to.path === '/login' && hasToken) return '/'
})

export default router
