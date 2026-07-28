import babel from "@rolldown/plugin-babel";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import { resolve } from "path";
import { defineConfig, loadEnv } from "vite";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const devProxyServer = process.env.DEV_PROXY_SERVER || env.DEV_PROXY_SERVER || "http://localhost:8081";

  return {
    plugins: [react(), babel({ presets: [reactCompilerPreset()] }), tailwindcss()],
    server: {
      host: "0.0.0.0",
      port: 3001,
      proxy: {
        "^/api/v1/sse": {
          target: devProxyServer,
          xfwd: true,
          // SSE requires no response buffering and longer timeout.
          timeout: 0,
        },
        "^/api": {
          target: devProxyServer,
          xfwd: true,
        },
        "^/memos.api.v1": {
          target: devProxyServer,
          xfwd: true,
        },
        "^/file": {
          target: devProxyServer,
          xfwd: true,
        },
      },
    },
    resolve: {
      alias: {
        "@/": `${resolve(__dirname, "src")}/`,
      },
    },
    build: {
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              {
                name: "utils-vendor",
                test: /node_modules[\\/](dayjs|lodash-es)([\\/]|$)/,
              },
              {
                name: "leaflet-vendor",
                test: /node_modules[\\/]leaflet([\\/]|$)/,
              },
            ],
          },
        },
      },
    },
  };
});
