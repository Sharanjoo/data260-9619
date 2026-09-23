import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Pinned to 5174 (NOT Vite's default 5173 -- that port is already used by
// another project, DeviationTrace, on this machine). The FastAPI backend's
// CORS config (code/main.py) explicitly allow_origins=["http://localhost:5174"]
// to match -- if Vite silently fell back to a different port, every API call
// would start failing CORS/cookie checks with no obvious cause, so strictPort
// makes it fail loudly instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
  },
})
