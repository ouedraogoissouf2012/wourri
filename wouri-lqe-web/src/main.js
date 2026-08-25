import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import LoginView from "./views/LoginView.vue";
import StudioView from "./views/StudioView.vue";
import AdminView from "./views/AdminView.vue";
import CoverageView from "./views/CoverageView.vue";
import AssignView from "./views/AssignView.vue";
import RequestsView from "./views/RequestsView.vue";
import DashboardView from "./views/DashboardView.vue";
import DictationView from "./views/DictationView.vue";
import "./style.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginView },
    { path: "/", component: StudioView },
    { path: "/admin", component: AdminView },
    { path: "/coverage", component: CoverageView },
    { path: "/assign", component: AssignView },
    { path: "/demandes", component: RequestsView },
    { path: "/dashboard", component: DashboardView },
    { path: "/dictee", component: DictationView },
  ],
});

createApp(App).use(router).mount("#app");
