// All calls to the FastAPI backend live here. Vite proxies /api to port 8000.
const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function parse(res) {
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') msg = data.detail
    } catch { /* keep default message */ }
    throw new Error(msg)
  }
  return res.json()
}

export const getCatalog = () => fetch('/api/catalog').then(parse)

export const createStudent = (name) =>
  fetch('/api/students', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ name }) }).then(parse)

export const generateQuiz = (subject, chapter, n) =>
  fetch('/api/quiz/generate', {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ subject, chapter, n }),
  }).then(parse)

export const submitQuiz = (quiz_id, answers, student_id) =>
  fetch('/api/quiz/submit', {
    method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ quiz_id, answers, student_id }),
  }).then(parse)

export const getProgress = (studentId) => fetch(`/api/progress/${studentId}`).then(parse)

// Reads the answer as it streams in (Server-Sent Events over a POST request).
// onEvent receives: {type:'token'|'sources'|'not_found'|'error'|'done', ...}
export async function askStream({ question, subject, chapter, language }, onEvent, signal) {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ question, subject: subject || null, chapter: chapter || null, language: language || null }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() // keep the unfinished part for the next round
    for (const block of blocks) {
      const line = block.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      try { onEvent(JSON.parse(line.slice(6))) } catch { /* ignore a broken event */ }
    }
  }
}