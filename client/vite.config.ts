import { fileURLToPath, URL } from 'node:url'

import { defineConfig, type HtmlTagDescriptor, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
function deconstaMetadata(): Plugin {
  let site: URL | undefined
  return {
    name: 'deconsta-metadata',
    configResolved(config) {
      site = config.env.VITE_SITE_URL ? new URL(config.env.VITE_SITE_URL) : undefined

      if (
        site &&
        (!['http:', 'https:'].includes(site.protocol) ||
          site.username ||
          site.password ||
          site.pathname !== '/' ||
          site.search ||
          site.hash)
      ) {
        throw new Error(
          'VITE_SITE_URL debe ser la URL raíz HTTP(S), sin credenciales, consulta ni fragmento.',
        )
      }
    },
    transformIndexHtml() {
      const tags: HtmlTagDescriptor[] = [
        {
          tag: 'meta',
          attrs: { name: 'twitter:card', content: site ? 'summary_large_image' : 'summary' },
        },
      ]
      if (site) {
        const image = new URL('/brand/deconsta/social/og-image.png', site).href
        tags.push(
          { tag: 'link', attrs: { rel: 'canonical', href: site.href } },
          { tag: 'meta', attrs: { property: 'og:url', content: site.href } },
          { tag: 'meta', attrs: { property: 'og:image', content: image } },
          { tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
          { tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
          {
            tag: 'meta',
            attrs: {
              property: 'og:image:alt',
              content: 'Deconsta. Gestión de pagos delegados.',
            },
          },
          { tag: 'meta', attrs: { name: 'twitter:image', content: image } },
          {
            tag: 'meta',
            attrs: {
              name: 'twitter:image:alt',
              content: 'Deconsta. Gestión de pagos delegados.',
            },
          },
        )
      }
      return tags
    },
  }
}

export default defineConfig({
  plugins: [vue(), vueDevTools(), deconstaMetadata()],
  server: {
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true } },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
