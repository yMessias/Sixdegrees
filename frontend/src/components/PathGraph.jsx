import { useEffect, useRef, useState } from 'react'
import './PathGraph.css'

const BASE_NODE_R = 52
const MIN_NODE_R = 28
const DESKTOP_ZIGZAG_OFFSET = 105

function PathGraph({ path, insights, insightState, selection }) {
  const wrapRef = useRef(null)
  const stageRef = useRef(null)
  const [dims, setDims] = useState({ w: 800, h: 500 })
  const [tip, setTip] = useState(null)
  const [activeEdge, setActiveEdge] = useState(null)

  useEffect(() => {
    function update() {
      const el = stageRef.current || wrapRef.current
      if (el) {
        setDims({ w: el.clientWidth, h: el.clientHeight })
      }
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
  const edges = path.slice(0, -1).map((step, i) => ({
    movie: step.movie,
    fromIdx: i,
    toIdx: i + 1,
  }))
  const total = actors.length
  const isCompact = dims.w < 760
  const availableW = Math.max(dims.w, 420)
  const sidePadding = isCompact ? 0 : clamp(availableW * 0.055, 72, 132)
  const desktopSpacing = total > 1 ? (availableW - sidePadding * 2) / (total - 1) : 0
  const fitScale = isCompact ? 1 : clamp(desktopSpacing / 360, 0.56, 1)
  const nodeR = isCompact
    ? BASE_NODE_R
    : Math.round(clamp(desktopSpacing * 0.15, MIN_NODE_R, BASE_NODE_R))
  const posterPad = Math.max(6, Math.round(10 * fitScale))
  const posterW = Math.max(34, Math.round(62 * fitScale))
  const posterH = Math.max(46, Math.round(84 * fitScale))
  const posterGap = Math.max(10, Math.round(16 * fitScale))
  const titleX = posterPad + posterW + posterGap
  const stageHeight = Math.max(380, dims.h - 128)
  const canvas = {
    w: availableW,
    h: isCompact ? Math.max(stageHeight, 230 + (total - 1) * 186) : Math.max(stageHeight, 460),
  }

  const positions = isCompact
    ? actors.map((_, i) => {
        const offset = Math.min(104, canvas.w * 0.16)
        const x =
          i === 0 || i === total - 1
            ? canvas.w / 2
            : canvas.w / 2 + (i % 2 === 0 ? -offset : offset)
        return {
          x,
          y: 126 + i * 186,
        }
      })
    : actors.map((_, i) => {
        const usableW = canvas.w - sidePadding * 2
        const spacing = total > 1 ? usableW / (total - 1) : 0
        const offset = total <= 2 ? 0 : Math.min(DESKTOP_ZIGZAG_OFFSET, canvas.h * 0.22)
        return {
          x: total === 1 ? canvas.w / 2 : sidePadding + i * spacing,
          y: total === 1 ? canvas.h / 2 : canvas.h / 2 + (i % 2 === 0 ? -offset : offset),
        }
      })

  function getInsight(edge) {
    if (!insights?.insights) return null
    const key = `${actors[edge.fromIdx].id}:${edge.movie.id}:${actors[edge.toIdx].id}`
    return insights.insights.find(ins => ins.connection_key === key)
  }

  function edgePath(a, b, index) {
    const mx = (a.x + b.x) / 2
    const my = (a.y + b.y) / 2
    const bend = edgeBend(index)

    return `M ${a.x} ${a.y} Q ${mx} ${my + bend} ${b.x} ${b.y}`
  }

  function edgeBend(index) {
    if (total <= 2) return -38
    if (isCompact) return index % 2 === 0 ? -48 : 48
    return index % 2 === 0 ? 58 : -58
  }

  function edgeLabel(movie) {
    if (!movie) return 'Conexao'
    const title = movie.title || 'Conexao'
    return movie.year ? `${title} (${movie.year})` : title
  }

  function mediaTypeLabel(movie) {
    return movie?.type === 'tv' ? 'serie' : 'filme'
  }

  function showEdgeTip(ev, edge, insight) {
    setActiveEdge(edge.index)
    if (!edge.movie || !wrapRef.current) return

    const rect = wrapRef.current.getBoundingClientRect()
    setTip({
      x: ev.clientX - rect.left,
      y: ev.clientY - rect.top,
      movie: edge.movie,
      actorLeft: actors[edge.fromIdx].name,
      actorRight: actors[edge.toIdx].name,
      insight: insight?.curiosity || null,
    })
  }

  function moveTip(ev) {
    if (tip && wrapRef.current) {
      const rect = wrapRef.current.getBoundingClientRect()
      setTip(t => ({ ...t, x: ev.clientX - rect.left, y: ev.clientY - rect.top }))
    }
  }

  const edgeVisuals = edges.map((edge, i) => {
    const a = positions[edge.fromIdx]
    const b = positions[edge.toIdx]
    const mx = (a.x + b.x) / 2
    const my = (a.y + b.y) / 2
    const bend = edgeBend(i)
    const label = edgeLabel(edge.movie)
    const hasPoster = Boolean(edge.movie?.poster)
    const cardMax = isCompact
      ? 390
      : Math.max(108, desktopSpacing - nodeR * 1.8)
    const cardMin = hasPoster
      ? Math.min(cardMax, Math.max(112, 190 * fitScale))
      : Math.min(cardMax, 130)
    const desiredCardWidth = hasPoster
      ? titleX + Math.min(210, label.length * 7) + 14
      : label.length * 7 + 32
    const cardWidth = Math.round(clamp(desiredCardWidth, cardMin, cardMax))
    const cardHeight = hasPoster ? posterH + posterPad * 2 : 50
    const labelX = clamp(mx, cardWidth / 2 + 8, canvas.w - cardWidth / 2 - 8)
    const labelY = clamp(my + bend / 2, cardHeight / 2 + 10, canvas.h - cardHeight / 2 - 10)
    const ins = edge.movie ? getInsight(edge) : null

    return {
      edge,
      index: i,
      pathD: edgePath(a, b, i),
      isActive: activeEdge === i,
      label,
      mediaType: mediaTypeLabel(edge.movie),
      hasPoster,
      cardWidth,
      cardHeight,
      labelX,
      labelY,
      ins,
      edgeWithIndex: { ...edge, index: i },
    }
  })

  return (
    <div className="graph-wrap" ref={wrapRef}>
      <div className="graph-header">
        <h2 className="graph-title">
          {selection?.actorA?.name || actors[0]?.name}
          <span> {' -> '} </span>
          {selection?.actorB?.name || actors[actors.length - 1]?.name}
        </h2>
      </div>

      <div className="graph-stage" ref={stageRef}>
        <svg
          className="graph-svg"
          width={canvas.w}
          height={canvas.h}
          viewBox={`0 0 ${canvas.w} ${canvas.h}`}
        >
          <defs>
            {actors.map((_, i) => (
              <clipPath key={`clip-${i}`} id={`clip-${i}`}>
                <circle cx={positions[i].x} cy={positions[i].y} r={nodeR - 2} />
              </clipPath>
            ))}
          </defs>

          {edgeVisuals.map(visual => (
              <g key={`edge-${visual.index}`}>
                <path
                  d={visual.pathD}
                  fill="none"
                  className={`graph-edge ${visual.isActive ? 'active' : ''}`}
                />

                <path
                  d={visual.pathD}
                  stroke="transparent"
                  strokeWidth={58}
                  fill="none"
                  style={{ cursor: 'pointer', pointerEvents: 'stroke' }}
                  onMouseEnter={ev => showEdgeTip(ev, visual.edgeWithIndex, visual.ins)}
                  onClick={ev => showEdgeTip(ev, visual.edgeWithIndex, visual.ins)}
                  onMouseMove={moveTip}
                  onMouseLeave={() => { setActiveEdge(null); setTip(null) }}
                />
              </g>
          ))}

          {actors.map((actor, i) => {
            const { x, y } = positions[i]
            const isFirst = i === 0
            const isLast = i === actors.length - 1

            return (
              <g key={`actor-${i}`} className="graph-actor-group">
                <circle cx={x} cy={y} r={nodeR + 7}
                  className={`graph-ring ${isFirst ? 'first' : isLast ? 'last' : ''}`}
                />
                <circle cx={x} cy={y} r={nodeR} className="graph-circle" />

                {actor.photo ? (
                  <image
                    href={actor.photo}
                    x={x - nodeR} y={y - nodeR}
                    width={nodeR * 2} height={nodeR * 2}
                    clipPath={`url(#clip-${i})`}
                    preserveAspectRatio="xMidYMid slice"
                  />
                ) : (
                  <text x={x} y={y} textAnchor="middle"
                    dominantBaseline="middle" className="graph-avatar-placeholder">?</text>
                )}

                {(isFirst || isLast) && (
                  <text x={x} y={y - nodeR - 16} textAnchor="middle"
                    className={`graph-badge-top ${isFirst ? 'first' : 'last'}`}>
                    {isFirst ? 'origem' : 'destino'}
                  </text>
                )}

                <text x={x} y={y + nodeR + 24} textAnchor="middle"
                  className="graph-actor-label">
                  {actor.name}
                </text>
              </g>
            )
          })}
        </svg>

        <div
          className="graph-edge-cards"
          style={{ width: canvas.w, height: canvas.h }}
        >
          {edgeVisuals.filter(visual => visual.edge.movie).map(visual => (
            <button
              type="button"
              key={`edge-card-${visual.index}`}
              className={`graph-edge-card ${visual.isActive ? 'active' : ''}`}
              style={{
                left: visual.labelX,
                top: visual.labelY,
                width: visual.cardWidth,
                minHeight: visual.cardHeight,
                '--poster-w': `${posterW}px`,
                '--poster-h': `${posterH}px`,
                '--poster-pad': `${posterPad}px`,
              }}
              aria-label={`Ver curiosidade sobre ${visual.label}`}
              onMouseEnter={ev => showEdgeTip(ev, visual.edgeWithIndex, visual.ins)}
              onMouseMove={moveTip}
              onMouseLeave={() => { setActiveEdge(null); setTip(null) }}
              onFocus={ev => {
                const rect = ev.currentTarget.getBoundingClientRect()
                showEdgeTip(
                  { clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 },
                  visual.edgeWithIndex,
                  visual.ins,
                )
              }}
              onBlur={() => { setActiveEdge(null); setTip(null) }}
              onClick={ev => showEdgeTip(ev, visual.edgeWithIndex, visual.ins)}
            >
              {visual.hasPoster && (
                <img
                  src={visual.edge.movie.poster}
                  alt={visual.edge.movie.title}
                  className="graph-edge-card-poster"
                  draggable="false"
                />
              )}
              <span className="graph-edge-card-copy">
                <span className="graph-edge-card-title">{visual.label}</span>
                <span className="graph-edge-card-kind">{visual.mediaType}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      {tip && (
        <div
          className="graph-tooltip"
          style={{
            left: Math.min(Math.max(tip.x + 16, 12), Math.max(12, dims.w - 310)),
            top: Math.max(tip.y - 104, 12),
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
                <span className="graph-tooltip-badge">serie</span>
              )}
            </div>
            <div className="graph-tooltip-actors">
              {tip.actorLeft} - {tip.actorRight}
            </div>
            {tip.insight ? (
              <div className="graph-tooltip-text">{tip.insight}</div>
            ) : insightState === 'error' ? (
              <div className="graph-tooltip-text muted">
                O grafo ficou pronto, mas a curiosidade dessa conexao nao voltou agora.
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

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

export default PathGraph
