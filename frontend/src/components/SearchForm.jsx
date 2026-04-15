import { useState, useEffect, useRef } from 'react'
import { searchActor } from '../services/api'
import './SearchForm.css'

function ActorInput({ label, value, onChange }) {
  const [query, setQuery]         = useState(value?.name || '')
  const [results, setResults]     = useState([])
  const [loading, setLoading]     = useState(false)
  const [open, setOpen]           = useState(false)
  const debounceRef               = useRef(null)
  const wrapRef                   = useRef(null)
  const abortRef                  = useRef(null)

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
      return
    }

    debounceRef.current = setTimeout(async () => {
      const controller = new AbortController()
      abortRef.current = controller
      setLoading(true)
      try {
        const data = await searchActor(term, controller.signal)
        setResults(data)
        setOpen(data.length > 0)
      } catch (error) {
        if (error.name !== 'AbortError') {
          setResults([])
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
  }, [query, value?.name])

  useEffect(() => {
    function handleClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function select(actor) {
    setQuery(actor.name)
    setResults([])
    setOpen(false)
    onChange(actor)
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
          placeholder="Nome do ator..."
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

      {open && results.length > 0 && (
        <ul className="actor-dropdown">
          {results.map(actor => (
            <li key={actor.id} className="actor-option" onMouseDown={() => select(actor)}>
              {actor.photo
                ? <img src={actor.photo} alt={actor.name} className="actor-option-photo" />
                : <div className="actor-option-photo placeholder">?</div>
              }
              <div>
                <div className="actor-option-name">{actor.name}</div>
                {actor.known_for && (
                  <div className="actor-option-known">{actor.known_for}</div>
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
  const [actorA, setActorA] = useState(null)
  const [actorB, setActorB] = useState(null)
  const sameActor = actorA && actorB && actorA.id === actorB.id

  function handleSubmit() {
    if (!actorA || !actorB) return
    if (sameActor) return
    onSearch(actorA, actorB)
  }

  function swapActors() {
    setActorA(actorB)
    setActorB(actorA)
  }

  return (
    <div className="search-form">
      <div className="search-eyebrow">teoria dos 6 graus de separação</div>
      <h1 className="search-headline">
        Conecte <span>atores</span> pelo cinema
      </h1>

      <div className="search-inputs">
        <ActorInput label="Ator A" value={actorA} onChange={setActorA} />
        <button
          type="button"
          className="search-swap-btn"
          onClick={swapActors}
          disabled={!actorA && !actorB}
          aria-label="Inverter atores"
        >
          ⇄
        </button>
        <ActorInput label="Ator B" value={actorB} onChange={setActorB} />
      </div>

      <button
        className="search-btn"
        onClick={handleSubmit}
        disabled={!actorA || !actorB || sameActor || loading}
      >
        {loading ? 'Buscando...' : 'Encontrar Conexão'}
      </button>

      {sameActor && (
        <p className="search-warning">
          Escolha dois atores diferentes para montar a cadeia.
        </p>
      )}

      <p className="search-hint">
        Digite pelo menos 2 letras em cada campo e descubra a menor cadeia que o app encontrar
      </p>
    </div>
  )
}

export default SearchForm
