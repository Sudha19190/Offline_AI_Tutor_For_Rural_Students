import { useEffect, useState } from 'react'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Loader2, Trophy } from 'lucide-react'
import { getProgress } from '../api'

export default function ProgressPage({ student }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getProgress(student.id).then(setData).catch((e) => setError(e.message))
  }, [student.id])

  const wrap = 'mx-auto h-full max-w-2xl overflow-y-auto px-4 py-5'
  if (error) return <div className={wrap}><p className="rounded-xl bg-red-50 px-4 py-3 text-red-700">{error}</p></div>
  if (!data) return <div className={`${wrap} flex items-center justify-center`}><Loader2 className="animate-spin text-emerald-600" size={32} /></div>

  const chapters = data.chapters
  const totalScore = chapters.reduce((a, c) => a + c.score, 0)
  const totalQs = chapters.reduce((a, c) => a + c.total, 0)
  const attempts = chapters.reduce((a, c) => a + c.attempts, 0)
  const overall = totalQs ? Math.round((100 * totalScore) / totalQs) : 0
  const chart = chapters.map((c) => ({ name: c.chapter, accuracy: c.accuracy }))

  return (
    <div className={wrap}>
      <h2 className="text-xl font-bold">{data.student_name}'s progress</h2>

      {attempts === 0 ? (
        <div className="mt-6 rounded-3xl border border-stone-200 bg-white p-8 text-center text-stone-500">
          <Trophy className="mx-auto text-stone-300" size={40} />
          <p className="mt-3 font-medium text-stone-700">No quizzes yet</p>
          <p className="text-sm">Take a quiz and your progress will appear here.</p>
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-stone-200 bg-white p-4"><p className="text-sm text-stone-500">Quizzes taken</p><p className="text-3xl font-bold">{attempts}</p></div>
            <div className="rounded-2xl border border-stone-200 bg-white p-4"><p className="text-sm text-stone-500">Overall accuracy</p><p className="text-3xl font-bold text-emerald-700">{overall}%</p></div>
          </div>

          <div className="mt-5 rounded-2xl border border-stone-200 bg-white p-4">
            <p className="mb-2 font-semibold">Accuracy by chapter</p>
            <ResponsiveContainer width="100%" height={Math.max(140, chart.length * 56)}>
              <BarChart data={chart} layout="vertical" margin={{ left: 4, right: 16 }}>
                <XAxis type="number" domain={[0, 100]} unit="%" />
                <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v) => `${v}%`} />
                <Bar dataKey="accuracy" fill="#059669" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-5">
            <p className="mb-2 font-semibold">Recent quizzes</p>
            <div className="space-y-2">
              {data.history.map((h) => (
                <div key={h.id} className="flex items-center justify-between rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
                  <div><p className="font-medium">{h.chapter}</p><p className="text-stone-500">{h.created_at.slice(0, 10)}</p></div>
                  <p className="text-lg font-bold text-emerald-700">{h.score}/{h.total}</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}