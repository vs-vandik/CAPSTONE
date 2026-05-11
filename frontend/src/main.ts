import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './style.css'

// Pinia must be installed before the router so route guards can call
// `useDiscourseStore()` synchronously.
const app = createApp(App)
app.use(createPinia())

// Lazy-import the router so its guards (which reference the store) run
// after Pinia is wired in.
import('./router').then(({ default: router }) => {
  app.use(router)
  app.mount('#app')

  // Warm the persona catalog at app boot. The user is almost certainly
  // going to need it (either Landing -> /experts, or they deep-linked
  // straight in), and firing the fetch here gives the backend a head
  // start over the user's click. Done after mount so we don't block
  // first paint; runs in the background.
  // Imported lazily to keep the entry chunk small and to ensure Pinia
  // is fully initialized.
  import('./stores/discourse').then(({ useDiscourseStore }) => {
    useDiscourseStore().loadPersonas()
  })
})
