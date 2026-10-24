import { useState } from 'react'
import { ThemeProvider } from '@figma/astraui'
import { Landing } from './components/Landing'
import { Dashboard } from './components/Dashboard'

type Page = 'landing' | 'app'

function AppContent() {
  const [page, setPage] = useState<Page>('landing')
  return page === 'landing' ? <Landing openApp={() => setPage('app')} /> : <Dashboard exit={() => setPage('landing')} />
}

export default function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  )
}
