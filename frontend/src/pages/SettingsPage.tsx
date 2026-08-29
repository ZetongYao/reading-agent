import { CheckCircle2, CircleAlert, LoaderCircle, Moon, RefreshCw, Save, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { AppSettings } from '../types'

type OllamaStatus = { running: boolean; model_installed: boolean; model: string; message: string }

export function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [ollama, setOllama] = useState<OllamaStatus | null>(null)
  const [checking, setChecking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.settings().then((value) => { setSettings(value); document.documentElement.dataset.theme = value.theme }).catch((caught) => setError(caught instanceof Error ? caught.message : '设置加载失败'))
  }, [])

  const check = async () => {
    setChecking(true)
    setError('')
    try { setOllama(await api.checkOllama()) } catch (caught) { setError(caught instanceof Error ? caught.message : '检测失败') }
    finally { setChecking(false) }
  }

  const save = async () => {
    if (!settings) return
    setSaving(true)
    setError('')
    try {
      const updated = await api.updateSettings(settings)
      setSettings(updated)
      document.documentElement.dataset.theme = updated.theme
      setNotice('设置已保存')
      window.setTimeout(() => setNotice(''), 2000)
    } catch (caught) { setError(caught instanceof Error ? caught.message : '保存失败') }
    finally { setSaving(false) }
  }

  if (!settings) return <div className="page"><div className="reader-loading"><LoaderCircle className="spin" />正在读取设置…</div>{error && <p className="error-message">{error}</p>}</div>

  return (
    <div className="page settings-page">
      <header className="page-header"><div><span className="eyebrow">本地偏好</span><h1>设置</h1><p>翻译地址、模型和阅读外观仅作用于本机。</p></div><button className="button primary" onClick={() => void save()} disabled={saving}>{saving ? <LoaderCircle className="spin" size={17} /> : <Save size={17} />}保存设置</button></header>
      {error && <div className="alert error-message" role="alert">{error}</div>}
      {notice && <div className="alert success-message"><CheckCircle2 size={17} />{notice}</div>}
      <div className="settings-grid">
        <section className="settings-card ollama-card">
          <div className="settings-card-heading"><div><span className="settings-icon">AI</span><div><h2>本地 Ollama</h2><p>只发送选中的词或词组及其完整句子</p></div></div><button className="button secondary compact" onClick={() => void check()} disabled={checking}>{checking ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}重新检测</button></div>
          {ollama && <div className={`ollama-status ${ollama.running && ollama.model_installed ? 'ready' : 'not-ready'}`}>{ollama.running && ollama.model_installed ? <CheckCircle2 size={19} /> : <CircleAlert size={19} />}<div><strong>{ollama.running && ollama.model_installed ? '翻译服务已就绪' : '需要完成本地设置'}</strong><span>{ollama.message}</span></div></div>}
          <div className="form-grid">
            <label><span>Ollama 地址</span><input value={settings.ollama_url} onChange={(event) => setSettings({ ...settings, ollama_url: event.target.value })} placeholder="http://localhost:11434" /></label>
            <label><span>模型名称</span><input value={settings.ollama_model} onChange={(event) => setSettings({ ...settings, ollama_model: event.target.value })} placeholder="qwen3:4b" /></label>
          </div>
          <div className="install-note"><strong>还没有安装 Ollama？</strong><p>安装并启动 Ollama 后，在 PowerShell 运行：</p><code>ollama pull {settings.ollama_model || 'qwen3:4b'}</code><p>即使未安装，本地书籍仍可正常导入和阅读。</p></div>
        </section>

        <section className="settings-card reading-settings">
          <div className="settings-card-heading"><div><span className="settings-icon">Aa</span><div><h2>阅读外观</h2><p>调整正文的舒适度</p></div></div></div>
          <div className="theme-toggle" role="group" aria-label="主题">
            <button className={settings.theme === 'light' ? 'active' : ''} onClick={() => { setSettings({ ...settings, theme: 'light' }); document.documentElement.dataset.theme = 'light' }}><Sun size={18} />亮色</button>
            <button className={settings.theme === 'dark' ? 'active' : ''} onClick={() => { setSettings({ ...settings, theme: 'dark' }); document.documentElement.dataset.theme = 'dark' }}><Moon size={18} />深色</button>
          </div>
          <label className="range-setting"><div><span>正文字号</span><strong>{settings.font_size}px</strong></div><input type="range" min="14" max="36" step="1" value={settings.font_size} onChange={(event) => setSettings({ ...settings, font_size: Number(event.target.value) })} /></label>
          <label className="range-setting"><div><span>正文行距</span><strong>{settings.line_height.toFixed(1)}</strong></div><input type="range" min="1.2" max="3" step="0.1" value={settings.line_height} onChange={(event) => setSettings({ ...settings, line_height: Number(event.target.value) })} /></label>
          <div className="reading-preview" style={{ fontSize: `${settings.font_size}px`, lineHeight: settings.line_height }}><span>阅读预览</span><p>The limits of my language mean the limits（界限）of my world.</p></div>
        </section>
      </div>
    </div>
  )
}

