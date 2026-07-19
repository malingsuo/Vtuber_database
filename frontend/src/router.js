import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('./views/QueryView.vue') },
  { path: '/events/new', component: () => import('./views/NewEventView.vue') },
  { path: '/events/:id', component: () => import('./views/EventDetailView.vue') },
  { path: '/reports', component: () => import('./views/ReportView.vue') },
  { path: '/forecast', component: () => import('./views/ForecastView.vue') },
  { path: '/settings', component: () => import('./views/SettingsView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
