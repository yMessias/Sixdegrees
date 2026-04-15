import { useEffect, useRef, useState } from 'react'
import './PathGraph.css'

const NODE_R    = 56
const H_PADDING = 140

function PathGraph({ path, insights, insightState, showInsights, selection }) {
  const wrapRef = useRef(null)
  const [dims, setDims]         = useState({ w: 800, h: 500 })
  const [tip, setTip]           = useState(null)
  const [activeEdge, setActiveEdge] = useState(null)

  useEffect(() => {
    function update() {
      if (wrapRef.current)
        setDims({ w: wrapRef.current.clientWidth, h: wrapRef.current.clientHeight })
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  useEffect(() => {
    setTip(null)
    setActiveEdge(null)
  }, [path])

  if (!path || path.length === 0) return null

  const actors = path.map(step => step.actor)
  const edges  = path.slice(0, -1).map((step, i) => ({
    movie:   step.movie,
    fromIdx: i,
    toIdx:   i + 1,
  }))
  const bridgeActors = actors.slice(1, -1)
  const insightCards = edges.map((edge, i) => ({
    id: `${actors[edge.fromIdx].id}:${edge.movie?.id}:${actors[edge.toIdx].id}`,
    index: i,
    movie: edge.movie,
    actorLeft: actors[edge.fromIdx],
    actorRight: actors[edge.toIdx],
    insight: edge.movie ? getInsight(edge) : null,
  }))

  const total = actors.length
  const isCompact = dims.w < 980 || total > 4
  const canvas = {
    w: Math.max(dims.w, 420),
    h: isCompact ? Math.max(dims.h, 220 + (total - 1) * 170) : dims.h,
  }

  const positions = isCompact
    ? actors.map((_, i) => {
        const offset = Math.min(92, canvas.w * 0.16)
        const x =
          i === 0 || i === total - 1
            ? canvas.w / 2
            : canvas.w / 2 + (i % 2 === 0 ? -offset : offset)
        return {
          x,
          y: 110 + i * 170,
        }
      })
    : actors.map((_, i) => {
        const usableW = canvas.w - H_PADDING * 2
        const spacing = total > 1 ? usableW / (total - 1) : 0
        return {
          x: H_PADDING + i * spacing,
          y: canvas.h / 2,
        }
      })

  function getInsight(edge) {
    if (!insights?.insights) return null
    const key = `${actors[edge.fromIdx].id}:${edge.movie.id}:${actors[edge.toIdx].id}`
    return insights.insights.find(ins => ins.connection_key === key)
  }

  return (
    <div className="graph-wrap" ref={wrapRef}>
      <div className="graph-header">
        <div>
          <div className="graph-kicker">menor cadeia encontrada</div>
          <h2 className="graph-title">
            {selection?.actorA?.name || actors[0]?.name}
            <span> {' -> '} </span>
            {selection?.actorB?.name || actors[actors.length - 1]?.name}
          </h2>
          <p className="graph-lede">
            {bridgeActors.length === 0
              ? 'Os dois atores dividiram a mesma obra.'
              : bridgeActors.length === 1
                ? `${bridgeActors[0].name} conecta os dois nomes.`
                : `${bridgeActors.map(actor => actor.name).join(' -> ')} conecta os dois nomes.`}
          </p>
        </div>
      </div>

      {showInsights && (
        <section id="graph-insights" className="graph-insights-panel">
          <div className="graph-insights-header">
            <div>
              <div className="graph-kicker">curiosidades da cadeia</div>
              <h3 className="graph-insights-title">Cada conexão, com contexto</h3>
            </div>
          </div>

          <div className="graph-insights-grid">
            {insightCards.map(card => (
              <article key={card.id} className="graph-insight-card">
                <div className="graph-insight-topline">
                  <span className="graph-summary-index">{card.index + 1}</span>
                  <div className="graph-insight-movie">
                    {card.movie?.title || 'Conexão encontrada'}
                    {card.movie?.year ? ` (${card.movie.year})` : ''}
                  </div>
                </div>

                <div className="graph-insight-pair">
                  {card.actorLeft.name} · {card.actorRight.name}
                </div>

                {card.insight?.curiosity ? (
                  <p className="graph-insight-text">{card.insight.curiosity}</p>
                ) : insightState === 'error' ? (
                  <p className="graph-insight-text muted">
                    O grafo foi montado, mas essa curiosidade não voltou agora.
                  </p>
                ) : (
                  <p className="graph-insight-text muted">
                    A IA ainda está montando essa curiosidade.
                  </p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}

      <svg
        className="graph-svg"
        width={canvas.w}
        height={canvas.h}
        viewBox={`0 0 ${canvas.w} ${canvas.h}`}
      >
        <defs>
          {actors.map((_, i) => (
            <clipPath key={`clip-${i}`} id={`clip-${i}`}>
              <circle cx={positions[i].x} cy={positions[i].y} r={NODE_R - 2} />
            </clipPath>
          ))}
          <filter id="glow">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Arestas */}
        {edges.map((edge, i) => {
          const a  = positions[edge.fromIdx]
          const b  = positions[edge.toIdx]
          const mx = (a.x + b.x) / 2
          const my = (a.y + b.y) / 2
          const isActive = activeEdge === i

          const ins = edge.movie ? getInsight(edge) : null

          return (
            <g key={`edge-${i}`}>
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                className={`graph-edge ${isActive ? 'active' : ''}`}
              />

              {/* Área invisível de hover */}
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke="transparent" strokeWidth={40}
                style={{ cursor: 'pointer', pointerEvents: 'stroke' }}
                onMouseEnter={ev => {
                  setActiveEdge(i)
                  if (edge.movie) {
                    const rect = wrapRef.current.getBoundingClientRect()
                    setTip({
                      x:          ev.clientX - rect.left,
                      y:          ev.clientY - rect.top,
                      movie:      edge.movie,
                      actorLeft:  actors[edge.fromIdx].name,
                      actorRight: actors[edge.toIdx].name,
                      insight:    ins?.curiosity || null,
                    })
                  }
                }}
                onMouseMove={ev => {
                  if (tip) {
                    const rect = wrapRef.current.getBoundingClientRect()
                    setTip(t => ({ ...t, x: ev.clientX - rect.left, y: ev.clientY - rect.top }))
                  }
                }}
                onMouseLeave={() => { setActiveEdge(null); setTip(null) }}
              />

              {/* Poster no meio da aresta */}
              {edge.movie?.poster && (
                <>
                  <clipPath id={`edge-clip-${i}`}>
                    <rect x={mx - 22} y={my - 32} width={44} height={60} rx={6} />
                  </clipPath>
                  <image
                    href={edge.movie.poster}
                    x={mx - 22} y={my - 32}
                    width={44} height={60}
                    clipPath={`url(#edge-clip-${i})`}
                    preserveAspectRatio="xMidYMid slice"
                    className={`graph-poster ${isActive ? 'active' : ''}`}
                    style={{ pointerEvents: 'none' }}
                  />
                  <rect
                    x={mx - 22} y={my - 32} width={44} height={60} rx={6}
                    fill="none"
                    stroke={isActive ? 'rgba(251,146,60,0.9)' : 'rgba(251,146,60,0.3)'}
                    strokeWidth={1.5}
                    style={{ pointerEvents: 'none' }}
                  />
                </>
              )}

              {/* Título do filme */}
              {edge.movie && (
                <text
                  x={mx}
                  y={my + (edge.movie.poster ? 48 : 16)}
                  textAnchor="middle"
                  className={`graph-movie-label ${isActive ? 'active' : ''}`}
                >
                  {edge.movie.title}
                  {edge.movie.year ? ` (${edge.movie.year})` : ''}
                  {edge.movie.type === 'tv' ? ' · série' : ''}
                </text>
              )}
            </g>
          )
        })}

        {/* Nós (atores) */}
        {actors.map((actor, i) => {
          const { x, y } = positions[i]
          const isFirst  = i === 0
          const isLast   = i === actors.length - 1

          return (
            <g key={`actor-${i}`} className="graph-actor-group">
              <circle cx={x} cy={y} r={NODE_R + 5}
                className={`graph-ring ${isFirst ? 'first' : isLast ? 'last' : ''}`}
              />
              <circle cx={x} cy={y} r={NODE_R} className="graph-circle" />

              {actor.photo ? (
                <image
                  href={actor.photo}
                  x={x - NODE_R} y={y - NODE_R}
                  width={NODE_R * 2} height={NODE_R * 2}
                  clipPath={`url(#clip-${i})`}
                  preserveAspectRatio="xMidYMid slice"
                />
              ) : (
                <text x={x} y={y} textAnchor="middle"
                  dominantBaseline="middle" style={{ fontSize: '1.8rem' }}>👤</text>
              )}

              {(isFirst || isLast) && (
                <text x={x} y={y - NODE_R - 12} textAnchor="middle"
                  className={`graph-badge-top ${isFirst ? 'first' : 'last'}`}>
                  {isFirst ? 'origem' : 'destino'}
                </text>
              )}

              <text x={x} y={y + NODE_R + 18} textAnchor="middle"
                className="graph-actor-label">
                {actor.name}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Tooltip */}
      {tip && (
        <div
          className="graph-tooltip"
          style={{
            left: Math.min(tip.x + 16, dims.w - 300),
            top:  Math.max(tip.y - 100, 10),
          }}
        >
          {tip.movie.poster && (
            <img src={tip.movie.poster} alt={tip.movie.title}
              className="graph-tooltip-poster" />
          )}
          <div className="graph-tooltip-body">
            <div className="graph-tooltip-title">
              {tip.movie.title}
              {tip.movie.year ? ` (${tip.movie.year})` : ''}
              {tip.movie.type === 'tv' && (
                <span className="graph-tooltip-badge">série</span>
              )}
            </div>
            <div className="graph-tooltip-actors">
              {tip.actorLeft} · {tip.actorRight}
            </div>
            {tip.insight ? (
              <div className="graph-tooltip-text">{tip.insight}</div>
            ) : insightState === 'error' ? (
              <div className="graph-tooltip-text muted">
                O grafo ficou pronto, mas a curiosidade dessa conexão não voltou agora.
              </div>
            ) : (
              <div className="graph-tooltip-text muted">Carregando curiosidade...</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default PathGraph
