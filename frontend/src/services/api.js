const rawBase = import.meta.env.VITE_API_BASE || '/api'
const BASE = rawBase.replace(/\/$/, '')

export async function searchActor(query, signal) {
  const res = await fetch(`${BASE}/search/?q=${encodeURIComponent(query)}`, { signal })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Erro na busca')
  return data
}

export async function findConnection(actorAId, actorBId, signal) {
  const res = await fetch(
    `${BASE}/connect/?actor_a=${actorAId}&actor_b=${actorBId}`,
    { signal },
  )
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Erro ao buscar conexão')
  return data
}

export async function getInsight(path, signal) {
  const res = await fetch(`${BASE}/insight/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
    signal,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Erro ao buscar insight')
  return data
}

export async function startConnectionJob(actorAId, actorBId, signal) {
  const res = await fetch(`${BASE}/connect/start/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor_a: actorAId, actor_b: actorBId }),
    signal,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Erro ao iniciar busca')
  return data
}

export async function getConnectionJob(jobId, signal) {
  const res = await fetch(`${BASE}/connect/status/${jobId}/`, { signal })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Erro ao consultar busca')
  return data
}

export async function cancelConnectionJob(jobId) {
  try {
    await fetch(`${BASE}/connect/cancel/${jobId}/`, { method: 'POST' })
  } catch {
    // Melhor esforço; ignoramos falha ao cancelar no backend.
  }
}
