import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Provider } from 'react-redux'
import './index.css'
import App from './App.jsx'
import { store } from './store.js'

// HW5 Part 1.III: Redux Toolkit store now wraps the app, alongside the
// existing BrowserRouter from HW4. The records data layer (recall_record)
// reads/writes through this store from here on; auth stays local state in
// App.jsx.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Provider store={store}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Provider>
  </StrictMode>,
)
