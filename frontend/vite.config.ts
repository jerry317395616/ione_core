import fs from 'node:fs'
import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const frontendRoot = path.resolve(__dirname)
const appRoot = path.resolve(frontendRoot, '..')
const publicOutput = path.resolve(appRoot, 'ione_core/public/mobile')
const routeTemplate = path.resolve(appRoot, 'ione_core/www/ione-mobile.html')

function publishFrappeRoute() {
  return {
    name: 'publish-frappe-route',
    closeBundle() {
      const generatedIndex = path.join(publicOutput, 'index.html')
      if (!fs.existsSync(generatedIndex)) {
        throw new Error(`Mobile build did not create ${generatedIndex}`)
      }
      fs.mkdirSync(path.dirname(routeTemplate), { recursive: true })
      fs.copyFileSync(generatedIndex, routeTemplate)
    },
  }
}

export default defineConfig({
  root: frontendRoot,
  base: '/assets/ione_core/mobile/',
  plugins: [react(), publishFrappeRoute()],
  resolve: {
    alias: {
      '@': path.resolve(frontendRoot, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.FRAPPE_DEV_URL || 'https://manager.myyr.top',
        changeOrigin: true,
        secure: true,
      },
    },
  },
  build: {
    target: 'es2020',
    minify: 'esbuild',
    outDir: publicOutput,
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: path.resolve(frontendRoot, 'index.html'),
    },
  },
  publicDir: path.resolve(frontendRoot, 'public'),
})
