import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.js";

// Fusion avec vite.config.js : le plugin @vitejs/plugin-vue (compilation des SFC) est
// declare une seule fois, cote build. Vitest ignore vite.config.js des lors qu'un
// vitest.config.js existe — d'ou le merge explicite plutot qu'une redeclaration.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      // pool threads : le pool "forks" par defaut echoue par intermittence au
      // demarrage du worker sous Windows ("Timeout waiting for worker to respond").
      // Ces tests ne mutent aucun etat de processus, l'isolation par thread suffit.
      pool: "threads",
      // clearMocks : sans ca les appels enregistres par un vi.fn() partage (mock de
      // module) s'accumulent d'un test a l'autre et une assertion peut lire l'appel
      // du test precedent au lieu du sien.
      clearMocks: true,
      include: ["src/**/*.test.js"],
      restoreMocks: true,
      unstubGlobals: true,
      unstubEnvs: true,
    },
  })
);
