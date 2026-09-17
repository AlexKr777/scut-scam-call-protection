import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { I18nProvider } from './i18n'
import { FloatingBar } from './components/FloatingBar'
import './styles/fonts.css'
import './styles/tokens.css'
import './styles/app.css'

const isFloatingSurface = new URLSearchParams(window.location.search).get('surface') === 'floating-bar'

createRoot(document.getElementById('root')!).render(
  <StrictMode><I18nProvider>
    {isFloatingSurface ? <FloatingBar /> : <App />}
  </I18nProvider></StrictMode>,
)
