const selectClass =
  'rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200'

export default function Picker({ subjects, subject, chapter, onSubject, onChapter, allowAll = true, language, onLanguage }) {
  const current = subjects.find((s) => s.name === subject)
  return (
    <div className="flex flex-wrap gap-2">
      <select className={selectClass} value={subject} onChange={(e) => onSubject(e.target.value)} aria-label="Subject">
        {subjects.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
      </select>
      <select className={`${selectClass} max-w-full`} value={chapter} onChange={(e) => onChapter(e.target.value)} aria-label="Chapter">
        {allowAll && <option value="">All chapters</option>}
        {current?.chapters.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
      </select>
      {onLanguage && (
        <select className={selectClass} value={language} onChange={(e) => onLanguage(e.target.value)} aria-label="Language">
          <option value="English">English</option>
          <option value="Hindi" disabled>Hindi (coming soon)</option>
          <option value="Kannada" disabled>Kannada (coming soon)</option>
        </select>
      )}
    </div>
  )
}