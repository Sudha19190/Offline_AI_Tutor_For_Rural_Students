import { useState } from 'react'
import { BookOpen, WifiOff } from 'lucide-react'
import { createStudent } from '../api'

export default function NameGate({ onDone }) {
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError('')
    try {
      const s = await createStudent(name.trim())
      onDone({ id: s.student_id, name: s.name })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-gradient-to-b from-emerald-50 to-stone-50 p-6">
      <form onSubmit={submit} className="w-full max-w-sm rounded-3xl border border-stone-200 bg-white p-7 shadow-sm">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-600 text-white">
          <BookOpen size={28} />
        </div>
        <h1 className="mt-4 text-center text-2xl font-bold">Jnana Vistara</h1>
        <p className="mt-1 text-center text-sm text-stone-500">Your offline study tutor</p>

        <label className="mt-6 block text-sm font-medium text-stone-700" htmlFor="name">What is your name?</label>
        <input
          id="name" value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={60}
          placeholder="Type your name"
          className="mt-1 w-full rounded-xl border border-stone-300 px-4 py-3 text-lg outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
        />
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <button
          disabled={busy || !name.trim()}
          className="mt-4 w-full rounded-xl bg-emerald-600 py-3 text-lg font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
        >
          {busy ? 'Please wait...' : 'Start learning'}
        </button>
        <p className="mt-4 flex items-center justify-center gap-1 text-xs text-stone-500">
          <WifiOff size={12} /> Works without internet
        </p>
      </form>
    </div>
  )
}