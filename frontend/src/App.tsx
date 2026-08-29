import { BookOpenText, LibraryBig, Settings as SettingsIcon } from 'lucide-react'
import { useEffect } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { ReaderPage } from './pages/ReaderPage'
import { SettingsPage } from './pages/SettingsPage'
import { ShelfPage } from './pages/ShelfPage'
import { VocabularyPage } from './pages/VocabularyPage'

export default function App() {
  useEffect(() => {
    api.settings().then((settings) => {
      document.documentElement.dataset.theme = settings.theme
    }).catch(() => {
      // Individual pages show connection errors if the backend is unavailable.
    })
  }, [])

  return (
    <div className="app-shell">
      <aside className="app-nav">
        <div className="brand" aria-label="原阅">
          <span className="brand-mark">原</span>
          <span className="brand-copy"><strong>原阅</strong><small>读原著，记语境</small></span>
        </div>
        <nav>
          <NavLink to="/shelf"><LibraryBig size={19} /><span>书架</span></NavLink>
          <NavLink to="/vocabulary"><BookOpenText size={19} /><span>单词本</span></NavLink>
          <NavLink to="/settings"><SettingsIcon size={19} /><span>设置</span></NavLink>
        </nav>
        <p className="local-note">所有书籍与数据仅保存在本机</p>
      </aside>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/shelf" replace />} />
          <Route path="/shelf" element={<ShelfPage />} />
          <Route path="/reader/:bookId" element={<ReaderPage />} />
          <Route path="/vocabulary" element={<VocabularyPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}
