import { createRouter, createWebHistory } from 'vue-router'


const routes = [
  {
    path: '/',
    component: () => import('@/pages/Login.vue')
  },
  {
    path: '/login',
    component: () => import('@/pages/Login.vue')
  },
  {
    path: '/project',
    component: () => import('@/pages/Project.vue')
  },
  {
    path: '/novel',
    component: () => import('@/pages/Novel.vue')
  },
  {
    path: '/script',
    component: () => import('@/pages/Script.vue')
  },
  {
    path: '/original',
    component: () => import('@/pages/Original.vue')
  },
  {
    path: '/screenwriting',
    component: () => import('@/pages/Screenwriting.vue')
  },
  {
    path: '/tasks',
    component: () => import('@/pages/Tasks.vue')
  },
  {
    path: '/production',
    component: () => import('@/pages/Production.vue')
  },
  {
    path: '/editor',
    component: () => import('@/pages/Editor.vue')
  },
]


const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')

  if (to.path !== '/login' && !token) {
    return '/login'
  }

  if (to.path === '/login' && token) {
    return '/project'
  }

  if (to.path === '/' && token) {
    return '/project'
  }

})

export default router;