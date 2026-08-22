import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import LoginView from "./views/LoginView.vue";
import StudioView from "./views/StudioView.vue";
import AdminView from "./views/AdminView.vue";
import "./style.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginView },
    { path: "/", component: StudioView },
  ],
});

createApp(App).use(router).mount("#app");

