import { startTransition, useEffect, useRef, useState } from 'react'
import SearchForm from '../components/SearchForm'
import PathGraph from '../components/PathGraph'
import cinemaWallpaper from '../assets/theend.jfif'
import {
  cancelConnectionJob,
  getConnectionJob,
  getInsight,
  startConnectionJob,
} from '../services/api'
import './Home.css'

const POLL_INTERVAL_MS = 1200

const APP_CONFIG = {
  logo: ['Six', 'Degrees'],
  loading: 'Buscando conexao completa...',
  queued: 'Iniciando busca profunda...',
  pairSeparator: '->',
  maxDegrees: 6,
  wallpaper: cinemaWallpaper,
}

function Home() {
  const [state, setState] = useState('idle')
  const [result, setResult] = useState(null)
  const [insights, setInsights] = useState(null)
  const [error, setError] = useState(null)
  const [degrees, setDegrees] = useState(null)
  const [searchMs, setSearchMs] = useState(null)
  const [insightState, setInsightState] = useState('idle')
  const [selection, setSelection] = useState(null)
  const [progress, setProgress] = useState(null)
  const [loadingMs, setLoadingMs] = useState(0)
  const requestRef = useRef({ connection: null, insight: null, jobId: null })
  const searchStartedAtRef = useRef(null)

  async function handleSearch(actorA, actorB) {
    cancelActiveSearch()

    const connectionController = new AbortController()
    requestRef.current.connection = connectionController
    requestRef.current.insight = null
    requestRef.current.jobId = null

    searchStartedAtRef.current = performance.now()
    setLoadingMs(0)
    setState('loading')
    setResult(null)
    setInsights(null)
    setError(null)
    setDegrees(null)
    setSearchMs(null)
    setInsightState('idle')
    setSelection({ actorA, actorB })
    setProgress({
      stage: 'queued',
      depth: 0,
      explored_actors: 0,
      frontier_size: 0,
      frontier_sample: [],
      history: [],
      message: APP_CONFIG.queued,
    })

    try {
      const job = await startConnectionJob(actorA.id, actorB.id, connectionController.signal)
      if (connectionController.signal.aborted) return

      requestRef.current.jobId = job.id
      setProgress(job.progress)
      await pollConnectionJob(job.id, connectionController)
    } catch (err) {
      if (err.name === 'AbortError') return
      setError(err.message)
      setState('error')
    }
  }

  async function pollConnectionJob(jobId, controller) {
    while (!controller.signal.aborted) {
      const job = await getConnectionJob(jobId, controller.signal)
      if (controller.signal.aborted) return

      setProgress(job.progress)

      if (job.status === 'pending' || job.status === 'running' || job.status === 'cancel_requested') {
        await waitForNextPoll(controller.signal)
        continue
      }

      if (job.status === 'completed') {
        const totalMs = searchStartedAtRef.current
          ? Math.round(performance.now() - searchStartedAtRef.current)
          : null

        setResult(job.path)
        setDegrees(job.degrees)
        setSearchMs(totalMs)
        setState('result')
        setProgress(job.progress)

        const insightController = new AbortController()
        requestRef.current.insight = insightController
        setInsightState('loading')

        getInsight(job.path, insightController.signal)
          .then(ins => {
            if (insightController.signal.aborted) return
            startTransition(() => {
              setInsights(ins)
              setInsightState('ready')
            })
          })
          .catch(err => {
            if (err.name !== 'AbortError') {
              setInsightState('error')
            }
          })
        return
      }

      if (job.status === 'not_found') {
        setError(job.progress?.message || 'Conexao nao encontrada.')
        setState('error')
        return
      }

      if (job.status === 'timeout') {
        setError(job.error || job.progress?.message || 'A busca excedeu o tempo permitido.')
        setState('error')
        return
      }

      if (job.status === 'cancelled') {
        return
      }

      if (job.status === 'error') {
        throw new Error(job.error || 'Erro durante a busca profunda')
      }
    }
  }

  function cancelActiveSearch() {
    requestRef.current.connection?.abort()
    requestRef.current.insight?.abort()
    if (requestRef.current.jobId) {
      cancelConnectionJob(requestRef.current.jobId)
      requestRef.current.jobId = null
    }
  }

  function reset() {
    cancelActiveSearch()
    searchStartedAtRef.current = null
    setState('idle')
    setResult(null)
    setInsights(null)
    setError(null)
    setDegrees(null)
    setSearchMs(null)
    setInsightState('idle')
    setSelection(null)
    setProgress(null)
    setLoadingMs(0)
  }

  useEffect(() => {
    if (state !== 'loading' || !searchStartedAtRef.current) {
      return undefined
    }

    const timer = window.setInterval(() => {
      setLoadingMs(Math.round(performance.now() - searchStartedAtRef.current))
    }, 250)

    return () => window.clearInterval(timer)
  }, [state])

  useEffect(() => {
    return () => {
      cancelActiveSearch()
    }
  }, [])

  return (
    <div
      className={`home home-state-${state}`}
      style={{ '--mode-wallpaper': `url(${APP_CONFIG.wallpaper})` }}
    >
      <header className="home-header">
        <div className="home-logo">
          {APP_CONFIG.logo[0]}<span>{APP_CONFIG.logo[1]}</span>
        </div>

        {state === 'result' && (
          <div className="home-header-right">
            <div className="home-degrees">
              <span className="home-degrees-num">{degrees}</span>
              <span className="home-degrees-label">
                {degrees === 1 ? 'grau' : 'graus'} de separacao
              </span>
            </div>
            <div className="home-meta-pills">
              {searchMs !== null && (
                <span className="home-pill">
                  busca {formatElapsed(searchMs)}
                </span>
              )}
            </div>
            <button className="home-reset-btn" onClick={reset}>
              Nova busca
            </button>
          </div>
        )}
      </header>

      {state === 'loading' && (
        <div className="home-loading home-loading-deep">
          <div className="home-ring" />
          <div className="home-loading-label">{APP_CONFIG.loading}</div>
          {selection && (
            <div className="home-loading-subtitle">
              {selection.actorA.name} {APP_CONFIG.pairSeparator} {selection.actorB.name}
            </div>
          )}

          <div className="home-loading-status">
            <span>{formatElapsed(loadingMs)}</span>
            <span>grau {Math.min((progress?.depth ?? 0) + 1, APP_CONFIG.maxDegrees)} de {APP_CONFIG.maxDegrees}</span>
          </div>

          <div className="home-progress-line">
            {progress?.message || 'Explorando conexoes...'}
          </div>

          <button className="home-back-btn" onClick={reset}>Cancelar busca</button>
        </div>
      )}

      {state === 'error' && (
        <div className="home-center">
          <div className="home-error">{error}</div>
          <button className="home-back-btn" onClick={reset}>Tentar novamente</button>
        </div>
      )}

      {state === 'idle' && (
        <div className="home-center">
          <SearchForm onSearch={handleSearch} loading={false} />
        </div>
      )}

      {state === 'result' && (
        <PathGraph
          path={result}
          insights={insights}
          insightState={insightState}
          selection={selection}
        />
      )}
    </div>
  )
}

function waitForNextPoll(signal) {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', handleAbort)
      resolve()
    }, POLL_INTERVAL_MS)

    function handleAbort() {
      window.clearTimeout(timer)
      signal.removeEventListener('abort', handleAbort)
      reject(new DOMException('Aborted', 'AbortError'))
    }

    signal.addEventListener('abort', handleAbort, { once: true })
  })
}

function formatElapsed(ms) {
  if (ms < 1000) {
    return `${ms}ms`
  }

  const totalSeconds = ms / 1000
  if (totalSeconds < 60) {
    return `${totalSeconds.toFixed(1)}s`
  }

  const minutes = Math.floor(totalSeconds / 60)
  const seconds = Math.round(totalSeconds % 60)
  if (seconds === 60) {
    return `${minutes + 1}m 0s`
  }

  return `${minutes}m ${seconds}s`
}

export default Home
