import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('./views/QueryView.vue') },
  { path: '/events/new', component: () => import('./views/NewEventView.vue') },
  { path: '/events/:id', component: () => import('./views/EventDetailView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
