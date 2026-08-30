import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from "node:path"



// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  // 使用@代表 "frontend/src"
  resolve: { alias: {"@": path.resolve(__dirname, "src") } },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8088",
        changeOrigin: true,
      },
      "/oss": {
        target: "http://127.0.0.1:8088",
        changeOrigin: true,
      },
    },
  },
})
