import { LoaderCircle, X } from 'lucide-react'

interface Props {
  selectedText: string
  sentence: string
  contextualTranslation: string
  meanings: string[]
  previewing: boolean
  saving: boolean
  error: string
  onRetry: () => void
  onSave: () => void
  onClose: () => void
}

export function WordModal({
  selectedText,
  sentence,
  contextualTranslation,
  meanings,
  previewing,
  saving,
  error,
  onRetry,
  onSave,
  onClose,
}: Props) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="word-modal" role="dialog" aria-modal="true" aria-labelledby="word-title">
        <button className="icon-button modal-close" onClick={onClose} aria-label="关闭"><X size={18} /></button>
        <span className="eyebrow">语境释义</span>
        <h2 id="word-title">{selectedText}</h2>
        <div className="meaning-preview">
          <span>当前句子中的意思</span>
          {previewing ? <strong className="meaning-loading"><LoaderCircle className="spin" size={16} />正在由本地模型生成中文释义…</strong> : (
            <strong data-testid="contextual-meaning">{contextualTranslation || '暂未生成'}</strong>
          )}
        </div>
        {!previewing && meanings.length > 0 && <div className="all-meanings">
          <span>全部中文释义</span>
          <ol>
            {meanings.map((meaning, index) => <li className={index === 0 ? 'current' : ''} key={`${meaning}-${index}`}>
              <span>{meaning}</span>{index === 0 && <em>当前语境</em>}
            </li>)}
          </ol>
        </div>}
        <div className="sentence-box">
          <span>完整原句</span>
          <p>{sentence}</p>
        </div>
        {error && <div className="error-message modal-error" role="alert"><span>{error}</span><button onClick={onRetry}>重新生成</button></div>}
        <div className="modal-actions">
          <button className="button ghost" onClick={onClose} disabled={saving}>取消</button>
          <button className="button primary" onClick={onSave} disabled={previewing || saving || !contextualTranslation} data-testid="save-translation">
            {saving && <LoaderCircle className="spin" size={17} />}
            保存
          </button>
        </div>
      </section>
    </div>
  )
}
