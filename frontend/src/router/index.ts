import { createRouter, createWebHistory } from 'vue-router'
import { useDiscourseStore } from '@/stores/discourse'

// Route components are imported eagerly rather than via `() => import(...)`
// dynamic imports. Reasons:
//
// 1. There are only five views and none of them pulls in a heavy lib
//    (no chart libs, no markdown engines, no editors). Per-route code
//    splitting saves a handful of KB at best, but introduces an async
//    boundary at the router/<router-view> level.
// 2. App.vue uses `<router-view v-slot="{ Component }">` wrapped in a
//    `<transition mode="out-in">`. With *async* components, the first
//    navigation can race: the outgoing component leaves, the incoming
//    chunk hasn't arrived yet, and `<component :is="undefined" />`
//    renders nothing. The page looks blank until a refresh forces the
//    chunk to be cache-hit and resolves synchronously. That is the
//    "experts page is empty on first visit, works after reload"
//    symptom we kept seeing.
// 3. Eager imports eliminate the race entirely without needing to
//    rework App.vue around `<Suspense>`.
import LandingView from '@/views/LandingView.vue'
import AboutView from '@/views/AboutView.vue'
import PersonasView from '@/views/PersonasView.vue'
import TopicView from '@/views/TopicView.vue'
import DiscourseView from '@/views/DiscourseView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: LandingView },
    { path: '/about', name: 'about', component: AboutView },
    { path: '/experts', name: 'experts', component: PersonasView },
    { path: '/topic', name: 'topic', component: TopicView },
    { path: '/discourse', name: 'discourse', component: DiscourseView },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

// Guard the deeper flow steps so users can't deep-link past selections.
// Pinia is initialized before the router is used (see main.ts).
router.beforeEach((to) => {
  const store = useDiscourseStore()
  if (to.name === 'topic' && store.selectedPersonaIds.length !== 2) {
    return { name: 'experts' }
  }
  if (to.name === 'discourse' && !store.sessionId) {
    // No active session -> bounce back to setup
    if (store.selectedPersonaIds.length !== 2) {
      return { name: 'experts' }
    }
    return { name: 'topic' }
  }
})

export default router
