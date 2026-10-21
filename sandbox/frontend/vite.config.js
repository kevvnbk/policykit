import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/sandbox': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
      '/credentials': 'http://localhost:8001',
    },
  },
})
