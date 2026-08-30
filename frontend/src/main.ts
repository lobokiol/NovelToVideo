import { createApp } from 'vue'
import { createPinia } from "pinia"
import ElementPlus from "element-plus"
import { config } from 'md-editor-v3'
import 'element-plus/dist/index.css'
import 'md-editor-v3/lib/style.css'
import './style.css'
import App from './App.vue'
import router from "./routes";

config({
  markdownItConfig(md) {
    const defaultRender = md.renderer.rules.link_open
      ?? ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

    md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
      const token = tokens[idx]
      const href = token.attrGet('href')
      if (href) {
        token.attrSet('target', '_blank')
        token.attrSet('rel', 'noopener noreferrer')
      }
      return defaultRender(tokens, idx, options, env, self)
    }
  },
})

createApp(App).use(createPinia()).use(router).use(ElementPlus).mount("#app");
