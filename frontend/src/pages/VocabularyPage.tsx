import { BookOpenCheck, Check, Download, Pencil, Search, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_URL, api } from '../api'
import type { VocabularyEntry } from '../types'

export function VocabularyPage() {
  const [entries, setEntries] = useState<VocabularyEntry[]>([])
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setEntries(await api.vocabulary(search))
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '单词本加载失败')
    }
  }, [search])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 180)
    return () => window.clearTimeout(timer)
  }, [load])

  const saveEdit = async (entry: VocabularyEntry) => {
    if (!draft.trim()) return
    try {
      const updated = await api.updateVocabulary(entry.id, draft.trim())
      setEntries((current) => current.map((item) => item.id === entry.id ? { ...item, chinese_annotation: updated.chinese_annotation } : item))
      setEditing(null)
    } catch (caught) { setError(caught instanceof Error ? caught.message : '修改失败') }
  }

  const remove = async (entry: VocabularyEntry) => {
    if (!window.confirm(`删除“${entry.selected_text}”及其正文内联注释吗？`)) return
    try { await api.deleteVocabulary(entry.id); setEntries((current) => current.filter((item) => item.id !== entry.id)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : '删除失败') }
  }

  const exportUrl = useMemo(() => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    return `${API_URL}/vocabulary/export.csv?${params}`
  }, [search])

  return (
    <div className="page vocabulary-page">
      <header className="page-header">
        <div><span className="eyebrow">语境记忆</span><h1>单词本</h1><p>只保留单词、中文释义和当时读到的完整句子，不记录书名或页码。</p></div>
        <a className="button primary" href={exportUrl} download><Download size={17} />导出 CSV</a>
      </header>
      <section className="filter-bar">
        <label className="search-field"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索单词、中文释义或原句" aria-label="搜索单词本" />{search && <button onClick={() => setSearch('')} aria-label="清除"><X size={15} /></button>}</label>
        <span className="entry-count">{entries.length} 条记录</span>
      </section>
      {error && <div className="alert error-message" role="alert">{error}</div>}
      {entries.length === 0 ? <section className="empty-state vocabulary-empty"><span className="empty-icon"><BookOpenCheck size={28} /></span><h2>还没有收藏语境</h2><p>阅读时单击英文单词，或拖动选择词组，生成的释义会自动出现在这里。</p><Link className="button secondary" to="/shelf">去书架阅读</Link></section> : (
        <div className="vocabulary-list">
          {entries.map((entry) => <article className="vocabulary-card" key={entry.id} data-testid="vocabulary-entry">
            <div className="word-and-meaning">
              <strong>{entry.selected_text}</strong>
              {editing === entry.id ? <div className="edit-meaning"><input autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void saveEdit(entry); if (event.key === 'Escape') setEditing(null) }} /><button aria-label="保存修改" onClick={() => void saveEdit(entry)}><Check size={16} /></button><button aria-label="取消修改" onClick={() => setEditing(null)}><X size={16} /></button></div> : <span>（{entry.chinese_annotation}）</span>}
            </div>
            {entry.all_chinese_meanings.length > 1 && <div className="vocabulary-meanings">
              {entry.all_chinese_meanings.map((meaning, index) => <span className={index === 0 ? 'current' : ''} key={`${meaning}-${index}`}>{meaning}</span>)}
            </div>}
            <blockquote>{entry.sentence}</blockquote>
            <div className="vocabulary-meta"><time>{new Date(entry.created_at).toLocaleString('zh-CN')}</time></div>
            <div className="vocabulary-actions">
              <button onClick={() => { setEditing(entry.id); setDraft(entry.chinese_annotation) }}><Pencil size={15} />修改</button>
              <button className="danger-text" onClick={() => void remove(entry)}><Trash2 size={15} />删除</button>
            </div>
          </article>)}
        </div>
      )}
    </div>
  )
}
