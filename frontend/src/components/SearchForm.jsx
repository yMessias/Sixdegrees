import { useState, useEffect, useRef } from 'react'
import { searchActor } from '../services/api'
import './SearchForm.css'

const FORM_CONFIG = {
  headline: <>Conecte <span>atores</span> pelo cinema</>,
  labels: ['Ator A', 'Ator B'],
  placeholder: 'Nome do ator...',
  warning: 'Escolha dois atores diferentes para montar a cadeia.',
  button: 'Buscar conexão no cinema',
  loading: 'Buscando no cinema...',
  search: searchActor,
}

function EntityInput({ label, value, onChange, config }) {
  const [query, setQuery] = useState(value?.name || '')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState(null)
  const debounceRef = useRef(null)
  const wrapRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    setQuery(value?.name || '')
  }, [value?.id, value?.name])

  useEffect(() => {
    clearTimeout(debounceRef.current)
    abortRef.current?.abort()

    const term = query.trim()
    if (term.length < 2 || term === value?.name) {
      setResults([])
      setOpen(false)
      setLoading(false)
      setError(null)
      return
    }

    debounceRef.current = setTimeout(async () => {
      const controller = new AbortController()
      abortRef.current = controller
      setLoading(true)
      setError(null)
      try {
        const data = await config.search(term, controller.signal)
        setResults(data)
        setOpen(data.length > 0)
      } catch (err) {
        if (err.name !== 'AbortError') {
          setResults([])
          setOpen(false)
          setError(err.message)
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }, 220)

    return () => {
      clearTimeout(debounceRef.current)
      abortRef.current?.abort()
    }
  }, [query, value?.name, config])

  useEffect(() => {
    function handleClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function select(entity) {
    setQuery(entity.name)
    setResults([])
    setOpen(false)
    setError(null)
    onChange(entity)
  }

  return (
    <div className="actor-input-wrap" ref={wrapRef}>
      <label className="actor-input-label">{label}</label>
      <div className="actor-input-box">
        {value?.photo && (
          <img src={value.photo} alt={value.name} className="actor-input-photo" />
        )}
        <input
          className="actor-input"
          placeholder={config.placeholder}
          value={query}
          onChange={e => { setQuery(e.target.value); if (!e.target.value) onChange(null) }}
          onKeyDown={e => {
            if (e.key === 'Escape') setOpen(false)
          }}
          onFocus={() => results.length && setOpen(true)}
          autoComplete="off"
        />
        {loading && <div className="actor-input-spinner" />}
      </div>

      {error && <div className="actor-input-error">{error}</div>}

      {open && results.length > 0 && (
        <ul className="actor-dropdown">
          {results.map(entity => (
            <li key={entity.id} className="actor-option" onMouseDown={() => select(entity)}>
              {entity.photo
                ? <img src={entity.photo} alt={entity.name} className="actor-option-photo" />
                : <div className="actor-option-photo placeholder">?</div>
              }
              <div>
                <div className="actor-option-name">{entity.name}</div>
                {entity.known_for && (
                  <div className="actor-option-known">{entity.known_for}</div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SearchForm({ onSearch, loading }) {
  const config = FORM_CONFIG
  const [entityA, setEntityA] = useState(null)
  const [entityB, setEntityB] = useState(null)
  const sameEntity = entityA && entityB && entityA.id === entityB.id

  function handleSubmit() {
    if (!entityA || !entityB) return
    if (sameEntity) return
    onSearch(entityA, entityB)
  }

  return (
    <div className="search-form">
      <h1 className="search-headline">{config.headline}</h1>

      <div className="search-inputs">
        <EntityInput label={config.labels[0]} value={entityA} onChange={setEntityA} config={config} />
        <EntityInput label={config.labels[1]} value={entityB} onChange={setEntityB} config={config} />
      </div>

      <button
        className="search-btn"
        onClick={handleSubmit}
        disabled={!entityA || !entityB || sameEntity || loading}
      >
        {loading ? config.loading : config.button}
      </button>

      {sameEntity && (
        <p className="search-warning">{config.warning}</p>
      )}

    </div>
  )
}

export default SearchForm
