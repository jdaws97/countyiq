import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import type { IncomingMessage, ServerResponse } from 'node:http'

// Match production host routing in dev and built previews; no auth bypasses.
function siteRouting(): Plugin {
  const route = (request: IncomingMessage, response: ServerResponse, next: () => void) => {
    const url = new URL(request.url || '/', 'http://' + (request.headers.host || 'localhost'))
    const appHost = url.hostname.startsWith('app.')
    const apiPath = url.pathname === '/api' || url.pathname.startsWith('/api/')
    if (!appHost && apiPath) {
      response.writeHead(404).end()
      return
    }
    if (apiPath) {
      next()
      return
    }
    const internal = ['/@', '/src/', '/node_modules/', '/assets/'].some(prefix => url.pathname.startsWith(prefix))
    const staticFile = ['/favicon-ciq.svg', '/robots.txt'].includes(url.pathname)
    if (!internal && !staticFile) {
      if (appHost && url.pathname !== '/app.html') {
        request.url = '/app.html' + url.search
      } else if (!appHost && !['/', '/index.html'].includes(url.pathname)) {
        const local = url.hostname === 'localhost' || url.hostname === '127.0.0.1'
        url.hostname = local ? 'app.localhost' : 'app.' + url.hostname
        if (['/app', '/app.html'].includes(url.pathname)) url.pathname = '/'
        response.writeHead(302, { Location: url.href }).end()
        return
      }
    }
    next()
  }
  return {
    name: 'countyiq-site-routing',
    configureServer(server) { server.middlewares.use(route) },
    configurePreviewServer(server) { server.middlewares.use(route) },
  }
}

export default defineConfig({
  plugins: [siteRouting(), react()],
  build: {
    rolldownOptions: {
      input: {
        marketing: fileURLToPath(new URL('./index.html', import.meta.url)),
        app: fileURLToPath(new URL('./app.html', import.meta.url)),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.COUNTYIQ_DEV_API_PROXY || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
