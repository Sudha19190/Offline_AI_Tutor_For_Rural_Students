import { useEffect, useState } from 'react'
import { MessageCircle, ClipboardCheck, BarChart3, WifiOff, LogOut, BookOpen } from 'lucide-react'
import { getCatalog } from './api'
import NameGate from './components/NameGate'
import ChatPage from './pages/ChatPage'
import QuizPage from './pages/QuizPage'
import ProgressPage from './pages/ProgressPage'

const TABS = [
  { id: 'chat', label: 'Ask', icon: MessageCircle },
  { id: 'quiz', label: 'Quiz', icon: ClipboardCheck },
  { id: 'progress', label: 'Progress', icon: BarChart3 },
]

function loadStudent() {
  try { return JSON.parse(localStorage.getItem('jv_student')) } catch { return null }
}
function saveStudent(s) {
  try {
    if (s) localStorage.setItem('jv_student', JSON.stringify(s))
    else localStorage.removeItem('jv_student')
  } catch { /* storage unavailable: ignore */ }
}

export default function App() {
  const [student, setStudent] = useState(loadStudent)
  const [tab, setTab] = useState('chat')
  const [subjects, setSubjects] = useState([])
  const [status, setStatus] = useState('loading') // loading | ok | error
  const [subject, setSubject] = useState('')
  const [chapter, setChapter] = useState('')

  useEffect(() => {
    getCatalog()
      .then((c) => {
        const list = c.subjects || []
        setSubjects(list)
        setSubject(list[0]?.name || '')
        setStatus('ok')
      })
      .catch(() => setStatus('error'))
  }, [])

  if (!student) {
    return <NameGate onDone={(s) => { saveStudent(s); setStudent(s) }} />
  }

  const sel = {
    subjects, subject, chapter,
    setSubject: (name) => { setSubject(name); setChapter('') },
    setChapter,
  }

  const logout = () => { saveStudent(null); setStudent(null) }

  let body
  if (status === 'loading') {
    body = <p className="p-6 text-stone-500">Loading...</p>
  } else if (status === 'error') {
    body = <p className="m-4 rounded-xl bg-red-50 p-4 text-red-700">Cannot reach the tutor. Please check that the server is running.</p>
  } else if (subjects.length === 0) {
    body = <p className="m-4 rounded-xl bg-amber-50 p-4 text-amber-800">No textbooks are installed yet. Ask your teacher to add one.</p>
  } else {
    body = (
      <>
        <div className={tab === 'chat' ? 'h-full min-h-0' : 'hidden'}><ChatPage {...sel} /></div>
        <div className={tab === 'quiz' ? 'h-full min-h-0' : 'hidden'}><QuizPage {...sel} student={student} /></div>
        {tab === 'progress' && <ProgressPage student={student} />}
      </>
    )
  }

  return (
    <div className="flex h-dvh flex-col md:flex-row">
      {/* Sidebar (tablets and laptops) */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-stone-200 bg-white p-4 md:flex">
        <div className="flex items-center gap-2 px-2 py-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-600 text-white"><BookOpen size={20} /></div>
          <div className="leading-tight"><p className="font-bold">Jnana Vistara</p><p className="text-xs text-stone-500">Offline study tutor</p></div>
        </div>
        <nav className="mt-4 space-y-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left font-medium ${tab === id ? 'bg-emerald-50 text-emerald-800' : 'text-stone-600 hover:bg-stone-100'}`}>
              <Icon size={20} /> {label}
            </button>
          ))}
        </nav>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-stone-200 bg-white px-4 py-3">
          <p className="font-bold md:hidden">Jnana Vistara</p>
          <span className="hidden text-sm text-stone-500 md:block">Hello, {student.name}</span>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-800">
              <WifiOff size={12} /> Offline mode
            </span>
            <button onClick={logout} aria-label="Switch student" title={`Signed in as ${student.name}. Tap to switch.`}
              className="rounded-full p-2 text-stone-500 hover:bg-stone-100"><LogOut size={18} /></button>
          </div>
        </header>

        <main className="min-h-0 flex-1">{body}</main>

        {/* Bottom tabs (phones) */}
        <nav className="flex border-t border-stone-200 bg-white md:hidden">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium ${tab === id ? 'text-emerald-700' : 'text-stone-500'}`}>
              <Icon size={22} /> {label}
            </button>
          ))}
        </nav>
      </div>
    </div>
  )
}