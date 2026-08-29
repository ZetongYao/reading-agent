import { BookMarked, FileUp, LoaderCircle, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Book } from '../types'

const statusLabel: Record<Book['status'], string> = {
  pending: '等待处理',
  processing: '正在导入',
  complete: '可以阅读',
  failed: '导入失败',
}

export function ShelfPage() {
  const [books, setBooks] = useState<Book[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const loadBooks = useCallback(async () => {
    try {
      setBooks(await api.books())
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法读取书架')
    }
  }, [])

  useEffect(() => { void loadBooks() }, [loadBooks])
  useEffect(() => {
    if (!books.some((book) => book.status === 'pending' || book.status === 'processing')) return
    const timer = window.setInterval(() => void loadBooks(), 900)
    return () => window.clearInterval(timer)
  }, [books, loadBooks])

  const uploadFiles = async (files: FileList | File[]) => {
    if (!files.length) return
    setUploading(true)
    setError('')
    try {
      for (const file of Array.from(files)) await api.upload(file)
      await loadBooks()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '上传失败')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const deleteBook = async (book: Book) => {
    if (!window.confirm(`确定删除《${book.title}》吗？正文、注释、阅读进度和相关单词记录都会一并删除。`)) return
    try {
      await api.deleteBook(book.id)
      await loadBooks()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '删除失败')
    }
  }

  return (
    <div className="page shelf-page">
      <header className="page-header">
        <div><span className="eyebrow">本地书库</span><h1>你的英文原版书</h1><p>上传后会按章节或页码整理，原文与学习记录都留在这台电脑上。</p></div>
        <button className="button primary" onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? <LoaderCircle className="spin" size={18} /> : <Plus size={18} />}
          上传书籍
        </button>
        <input
          ref={inputRef}
          type="file"
          hidden
          multiple
          accept=".pdf,.epub,.txt,.md,.markdown,.html,.htm,.docx,.jpg,.jpeg,.png,.mobi,.azw3"
          onChange={(event) => event.target.files && void uploadFiles(event.target.files)}
          data-testid="book-upload"
        />
      </header>

      {error && <div className="alert error-message" role="alert">{error}</div>}

      <section
        className="upload-zone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => { event.preventDefault(); void uploadFiles(event.dataTransfer.files) }}
        onClick={() => inputRef.current?.click()}
      >
        <FileUp size={26} />
        <div><strong>拖入书籍，或点击选择文件</strong><span>PDF · EPUB · TXT · Markdown · HTML · DOCX · 图片 · MOBI/AZW3（需 Calibre）</span></div>
      </section>

      <div className="section-heading"><h2>全部书籍</h2><span>{books.length} 本</span></div>
      {books.length === 0 ? (
        <section className="empty-state">
          <span className="empty-icon"><BookMarked size={28} /></span>
          <h2>从第一本书开始</h2>
          <p>推荐先上传 TXT 或文字版 PDF。扫描 PDF 会自动调用本机 PaddleOCR。</p>
          <button className="button secondary" onClick={() => inputRef.current?.click()}>选择一本书</button>
        </section>
      ) : (
        <div className="book-grid">
          {books.map((book, index) => (
            <article className="book-card" key={book.id} data-testid="book-card">
              <div className={`book-cover cover-${index % 5}`}><span>{book.title.slice(0, 1).toUpperCase()}</span><small>{book.file_type.toUpperCase()}</small></div>
              <div className="book-info">
                <div className="book-title-row"><h3>{book.title}</h3><span className={`status status-${book.status}`}>{statusLabel[book.status]}</span></div>
                <p>{book.author || book.original_filename}</p>
                {book.status === 'processing' || book.status === 'pending' ? (
                  <div className="import-progress">
                    <div><span style={{ width: `${book.total_pages ? Math.min(100, book.processed_pages / book.total_pages * 100) : 8}%` }} /></div>
                    <small>{book.error_message || '正在读取文件…'}</small>
                  </div>
                ) : book.status === 'failed' ? (
                  <p className="card-error">{book.error_message}</p>
                ) : (
                  <div className="book-stats">
                    <span>共 {book.total_pages || book.section_count} 页/章</span>
                    <span>成功 {Math.max(0, book.processed_pages - book.failed_pages.length)} 页/章</span>
                    <span>{book.char_count.toLocaleString()} 字符</span>
                    {book.ocr_pages > 0 && <span>OCR {book.ocr_pages} 页</span>}
                    {book.failed_pages.length > 0 && <span className="danger">失败 {book.failed_pages.length} 页</span>}
                  </div>
                )}
                <div className="book-actions">
                  <button
                    className="button secondary compact"
                    disabled={book.status !== 'complete'}
                    onClick={() => navigate(`/reader/${book.id}`)}
                  >打开阅读</button>
                  <button className="icon-button danger-button" aria-label={`删除 ${book.title}`} onClick={() => void deleteBook(book)}><Trash2 size={17} /></button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
