import { useState } from 'react'
import { CheckCircle2, XCircle, Loader2, ClipboardCheck } from 'lucide-react'
import Picker from '../components/Picker'
import { generateQuiz, submitQuiz } from '../api'

export default function QuizPage({ subjects, subject, chapter, setSubject, setChapter, student }) {
  const current = subjects.find((s) => s.name === subject)
  const chosenChapter = chapter || current?.chapters[0]?.name || ''

  const [n, setN] = useState(3)
  const [phase, setPhase] = useState('idle') // idle | loading | taking | grading | done
  const [quiz, setQuiz] = useState(null)
  const [idx, setIdx] = useState(0)
  const [picked, setPicked] = useState(null)
  const [answers, setAnswers] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  async function start() {
    setError('')
    setPhase('loading')
    try {
      const q = await generateQuiz(subject, chosenChapter, n)
      setQuiz(q)
      setIdx(0)
      setPicked(null)
      setAnswers([])
      setPhase('taking')
    } catch (err) {
      setError(err.message)
      setPhase('idle')
    }
  }

  async function next() {
    const all = [...answers, picked]
    if (idx + 1 < quiz.questions.length) {
      setAnswers(all)
      setIdx(idx + 1)
      setPicked(null)
      return
    }
    setPhase('grading')
    try {
      setResult(await submitQuiz(quiz.quiz_id, all, student.id))
      setPhase('done')
    } catch (err) {
      setError(err.message)
      setPhase('idle')
    }
  }

  const wrap = 'mx-auto h-full max-w-2xl overflow-y-auto px-4 py-5'

  if (phase === 'loading' || phase === 'grading') {
    return (
      <div className={`${wrap} flex flex-col items-center justify-center text-center`}>
        <Loader2 className="animate-spin text-emerald-600" size={40} />
        <p className="mt-4 text-lg font-semibold">{phase === 'loading' ? 'Writing your questions...' : 'Checking your answers...'}</p>
        {phase === 'loading' && <p className="mt-1 text-sm text-stone-500">This can take up to a minute on a school laptop.</p>}
      </div>
    )
  }

  if (phase === 'taking' && quiz) {
    const q = quiz.questions[idx]
    const last = idx + 1 === quiz.questions.length
    return (
      <div className={wrap}>
        <div className="flex items-center justify-between text-sm text-stone-500">
          <span>Question {idx + 1} of {quiz.questions.length}</span>
          <span>{quiz.chapter}</span>
        </div>
        <div className="mt-2 h-2 rounded-full bg-stone-200">
          <div className="h-2 rounded-full bg-emerald-600 transition-all" style={{ width: `${((idx + (picked !== null ? 1 : 0)) / quiz.questions.length) * 100}%` }} />
        </div>

        <h2 className="mt-6 text-xl font-semibold leading-snug">{q.question}</h2>
        <div className="mt-4 space-y-3">
          {q.options.map((opt, i) => {
            let style = 'border-stone-300 bg-white hover:border-emerald-400'
            if (picked !== null) {
              if (i === q.correct_index) style = 'border-emerald-500 bg-emerald-50'
              else if (i === picked) style = 'border-red-400 bg-red-50'
              else style = 'border-stone-200 bg-stone-50 text-stone-400'
            }
            return (
              <button key={i} disabled={picked !== null} onClick={() => setPicked(i)}
                className={`flex w-full items-center gap-3 rounded-2xl border-2 px-4 py-3 text-left text-base transition ${style}`}>
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-stone-100 text-sm font-semibold text-stone-600">
                  {String.fromCharCode(65 + i)}
                </span>
                <span className="flex-1">{opt}</span>
                {picked !== null && i === q.correct_index && <CheckCircle2 className="shrink-0 text-emerald-600" size={20} />}
                {picked !== null && i === picked && i !== q.correct_index && <XCircle className="shrink-0 text-red-500" size={20} />}
              </button>
            )
          })}
        </div>

        {picked !== null && (
          <div className="mt-4">
            {q.explanation && <p className="rounded-2xl bg-stone-100 px-4 py-3 text-sm text-stone-700">{q.explanation}{q.page ? ` (page ${q.page})` : ''}</p>}
            <button onClick={next} className="mt-4 w-full rounded-xl bg-emerald-600 py-3 text-lg font-semibold text-white hover:bg-emerald-700">
              {last ? 'See my score' : 'Next question'}
            </button>
          </div>
        )}
      </div>
    )
  }

  if (phase === 'done' && result) {
    const msg = result.percent >= 80 ? 'Great work!' : result.percent >= 50 ? 'Good effort. Review the ones you missed.' : 'Keep practising. Read the chapter and try again.'
    return (
      <div className={wrap}>
        <div className="rounded-3xl border border-stone-200 bg-white p-6 text-center shadow-sm">
          <p className="text-5xl font-bold text-emerald-700">{result.score}/{result.total}</p>
          <p className="mt-1 text-stone-500">{result.percent}%</p>
          <p className="mt-3 text-lg font-medium">{msg}</p>
        </div>
        <div className="mt-5 space-y-3">
          {result.results.map((r, i) => (
            <div key={i} className="flex gap-3 rounded-2xl border border-stone-200 bg-white p-4">
              {r.correct ? <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-600" size={20} /> : <XCircle className="mt-0.5 shrink-0 text-red-500" size={20} />}
              <div>
                <p className="font-medium">{r.question}</p>
                <p className="mt-1 text-sm text-stone-600">{r.feedback}</p>
              </div>
            </div>
          ))}
        </div>
        <button onClick={() => setPhase('idle')} className="mt-5 w-full rounded-xl bg-emerald-600 py-3 text-lg font-semibold text-white hover:bg-emerald-700">
          Take another quiz
        </button>
      </div>
    )
  }

  return (
    <div className={wrap}>
      <div className="rounded-3xl border border-stone-200 bg-white p-6 shadow-sm">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700"><ClipboardCheck size={24} /></div>
        <h2 className="mt-3 text-xl font-bold">Test yourself</h2>
        <p className="mt-1 text-sm text-stone-500">Questions are written from your own textbook chapter.</p>
        <div className="mt-4">
          <Picker subjects={subjects} subject={subject} chapter={chosenChapter} onSubject={setSubject} onChapter={setChapter} allowAll={false} />
        </div>
        <div className="mt-4 flex items-center gap-3">
          <span className="text-sm text-stone-600">Questions:</span>
          {[3, 5].map((k) => (
            <button key={k} onClick={() => setN(k)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium ${n === k ? 'bg-emerald-600 text-white' : 'bg-stone-100 text-stone-700'}`}>{k}</button>
          ))}
        </div>
        {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
        <button onClick={start} disabled={!chosenChapter}
          className="mt-5 w-full rounded-xl bg-emerald-600 py-3 text-lg font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
          Start quiz
        </button>
      </div>
    </div>
  )
}