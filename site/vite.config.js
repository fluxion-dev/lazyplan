import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: '/lazyplan/',
  plugins: [tailwindcss()],
  build: {
    outDir: 'dist'
  }
})
