import { useEffect, useRef, useState } from 'react'
import { Send, Square, BookOpen, AlertCircle, SearchX } from 'lucide-react'
import Picker from '../components/Picker'
import { askStream } from '../api'

function Bubble({ m }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-emerald-600 px-4 py-3 text-base text-white">{m.text}</div>
      </div>
    )
  }
  if (m.status === 'not_found') {
    return (
      <div className="flex max-w-[90%] gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-900">
        <SearchX className="mt-0.5 shrink-0" size={20} />
        <p>{m.text}</p>
      </div>
    )
  }
  if (m.status === 'error') {
    return (
      <div className="flex max-w-[90%] gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-red-800">
        <AlertCircle className="mt-0.5 shrink-0" size={20} />
        <p>{m.text}</p>
      </div>
    )
  }
  return (
    <div className="max-w-[90%] rounded-2xl rounded-bl-md border border-stone-200 bg-white px-4 py-3 shadow-sm">
      <p className="whitespace-pre-wrap text-base leading-relaxed">
        {m.text || (m.status === 'streaming' ? 'Looking through your textbook...' : '')}
        {m.status === 'streaming' && m.text && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-emerald-600 align-middle" />}
      </p>
      {m.sources?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-stone-100 pt-3">
          {m.sources.map((s) => (
            <span key={`${s.chapter}-${s.page}`} className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800">
              <BookOpen size={12} /> {s.chapter}, p.{s.page}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ChatPage({ subjects, subject, chapter, setSubject, setChapter }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [language, setLanguage] = useState('English')
  const abortRef = useRef(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Update the assistant message that is currently being written (always the last one).
  const patchLast = (fn) => setMessages((ms) => ms.map((m, i) => (i === ms.length - 1 ? fn(m) : m)))

  async function send(e) {
    e.preventDefault()
    const question = input.trim()
    if (question.length < 2 || busy) return
    setInput('')
    setBusy(true)
    setMessages((ms) => [...ms, { role: 'user', text: question }, { role: 'assistant', text: '', sources: [], status: 'streaming' }])

    const controller = new AbortController()
    abortRef.current = controller
    try {
      await askStream({ question, subject, chapter, language }, (ev) => {
        if (ev.type === 'token') patchLast((m) => ({ ...m, text: m.text + ev.text }))
        else if (ev.type === 'sources') patchLast((m) => ({ ...m, sources: ev.sources }))
        else if (ev.type === 'not_found') patchLast((m) => ({ ...m, text: ev.text, status: 'not_found' }))
        else if (ev.type === 'error') patchLast((m) => ({ ...m, text: ev.text, status: 'error' }))
      }, controller.signal)
      patchLast((m) => (m.status === 'streaming' ? { ...m, status: 'done' } : m))
    } catch (err) {
      if (err.name === 'AbortError') {
        patchLast((m) => ({ ...m, status: 'done', text: m.text || 'Stopped.' }))
      } else {
        patchLast((m) => ({ ...m, status: 'error', text: 'Could not reach the tutor. Is the server running?' }))
      }
    } finally {
      setBusy(false)
      abortRef.current = null
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-stone-200 bg-white px-4 py-3">
        <Picker
          subjects={subjects} subject={subject} chapter={chapter}
          onSubject={setSubject} onChapter={setChapter}
          language={language} onLanguage={setLanguage}
        />
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5">
        {messages.length === 0 && (
          <div className="mx-auto mt-10 max-w-sm text-center text-stone-500">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700">
              <BookOpen size={28} />
            </div>
            <p className="mt-4 text-lg font-semibold text-stone-700">Ask anything from your textbook</p>
            <p className="mt-1 text-sm">
              {chapter ? `I will answer from "${chapter}".` : `I will search all ${subject} chapters.`} Answers always show the page they came from.
            </p>
          </div>
        )}
        {messages.map((m, i) => <Bubble key={i} m={m} />)}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={send} className="flex gap-2 border-t border-stone-200 bg-white p-3">
        <input
          value={input} onChange={(e) => setInput(e.target.value)} maxLength={500}
          placeholder="Type your question..."
          className="min-w-0 flex-1 rounded-full border border-stone-300 px-5 py-3 text-base outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
        />
        {busy ? (
          <button type="button" onClick={() => abortRef.current?.abort()} aria-label="Stop"
            className="flex h-12 w-12 items-center justify-center rounded-full bg-stone-700 text-white">
            <Square size={18} />
          </button>
        ) : (
          <button disabled={input.trim().length < 2} aria-label="Send"
            className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-600 text-white transition hover:bg-emerald-700 disabled:opacity-40">
            <Send size={20} />
          </button>
        )}
      </form>
    </div>
  )
}