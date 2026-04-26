import { useEffect, useRef, useState } from 'react'
import './PathGraph.css'

const BASE_NODE_R = 52
const MIN_NODE_R = 28
const DESKTOP_ZIGZAG_OFFSET = 105
const TIMELINE_CARD_LIMIT = 8

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
  const edges = path.slice(0, -1).map((step, i) => {
    const timeline = getStepTimeline(step)
    const timelineTotal = Math.max(Number(step.timeline_total || 0), timeline.length)

    return {
      movie: step.movie,
      timeline,
      timelineTotal,
      fromIdx: i,
      toIdx: i + 1,
    }
  })
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
  const stageHeight = Math.max(320, dims.h || 460)
  const canvas = {
    w: availableW,
    h: stageHeight,
  }

  const positions = isCompact
    ? actors.map((_, i) => {
        const offset = Math.min(104, canvas.w * 0.16)
        const topPad = 90
        const bottomPad = 90
        const spacing = total > 1
          ? Math.max(96, (canvas.h - topPad - bottomPad) / (total - 1))
          : 0
        const x =
          i === 0 || i === total - 1
            ? canvas.w / 2
            : canvas.w / 2 + (i % 2 === 0 ? -offset : offset)
        return {
          x,
          y: total === 1 ? canvas.h / 2 : topPad + i * spacing,
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

  function getInsight(edge, work = edge.movie) {
    if (!insights?.insights || !work) return null
    const key = `${actors[edge.fromIdx].id}:${work.id}:${actors[edge.toIdx].id}`
    return insights.insights.find(ins => ins.connection_key === key)
  }

  function edgePath(a, b, index) {
    const mx = (a.x + b.x) / 2
    const my = (a.y + b.y) / 2
    const bend = edgeBend(index)

    return `M ${a.x} ${a.y} Q ${mx} ${my + bend} ${b.x} ${b.y}`
  }

  function timelinePath(cards) {
    if (!cards || cards.length < 2) return null

    let pathD = ''
    for (let index = 0; index < cards.length - 1; index += 1) {
      const current = cards[index]
      const next = cards[index + 1]
      const start = rectAnchorPoint(current, next)
      const end = rectAnchorPoint(next, current)
      pathD += `${pathD ? ' ' : ''}M ${start.x} ${start.y} L ${end.x} ${end.y}`
    }
    return pathD
  }

  function timelineConnectorPath(actor, card, actorRadius) {
    if (!card) return null

    const start = circleAnchorPoint(actor, card, actorRadius)
    const end = rectAnchorPoint(card, actor)
    return `M ${start.x} ${start.y} L ${end.x} ${end.y}`
  }

  function edgeBend(index) {
    if (total <= 2) return -38
    if (isCompact) return index % 2 === 0 ? -48 : 48
    return index % 2 === 0 ? 58 : -58
  }

  function edgeLabel(edge) {
    if ((edge.timelineTotal || 0) > 1) {
      return `${edge.timelineTotal} obras juntos`
    }

    return workLabel(singleDisplayWork(edge))
  }

  function mediaTypeLabel(edge) {
    if ((edge.timelineTotal || 0) > 1) return 'linha do tempo'
    return singleDisplayWork(edge)?.type === 'tv' ? 'serie' : 'filme'
  }

  function showEdgeTip(ev, edge, insight, work = null) {
    setActiveEdge(edge.index)
    if ((!edge.movie && !edge.timeline?.length) || !wrapRef.current) return

    const selectedWork = work || edge.displayWork || edge.movie
    const rect = wrapRef.current.getBoundingClientRect()
    setTip({
      x: ev.clientX - rect.left,
      y: ev.clientY - rect.top,
      movie: selectedWork,
      timeline: work ? [work] : edge.timeline || [],
      timelineTotal: work ? 1 : edge.timelineTotal || edge.timeline?.length || 0,
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
    const timelineTotal = edge.timelineTotal || edge.timeline.length
    const isTimeline = timelineTotal > 1
    const displayWork = singleDisplayWork(edge)
    const timelineWorks = edge.timeline.slice(0, TIMELINE_CARD_LIMIT)
    const hiddenTimelineCount = Math.max(0, timelineTotal - timelineWorks.length)
    const label = edgeLabel(edge)
    const hasPoster = !isTimeline && Boolean(displayWork?.poster)
    const cardMax = isCompact
      ? 390
      : Math.max(isTimeline ? 190 : 108, desktopSpacing - nodeR * 1.8)
    const cardMin = hasPoster
      ? Math.min(cardMax, Math.max(112, 190 * fitScale))
      : isTimeline
        ? Math.min(cardMax, Math.max(174, 250 * fitScale))
      : Math.min(cardMax, 130)
    const longestTimelineLabel = timelineWorks.reduce(
      (longest, work) => Math.max(longest, workLabel(work).length),
      label.length,
    )
    const desiredCardWidth = hasPoster
      ? titleX + Math.min(210, label.length * 7) + 14
      : isTimeline
        ? Math.min(360, Math.max(230, 110 + longestTimelineLabel * 5.2))
      : label.length * 7 + 32
    const cardWidth = Math.round(clamp(desiredCardWidth, Math.min(cardMin, cardMax), cardMax))
    const cardHeight = isTimeline
      ? 58
      : hasPoster ? posterH + posterPad * 2 : 50
    const timelineCards = isTimeline
      ? buildTimelineCards({
          works: timelineWorks,
          a,
          b,
          bend,
          canvas,
          nodeR,
          fitScale,
          isCompact,
          hiddenTimelineCount,
        })
      : []
    const labelX = clamp(mx, cardWidth / 2 + 8, canvas.w - cardWidth / 2 - 8)
    const labelY = clamp(my + bend / 2, cardHeight / 2 + 10, canvas.h - cardHeight / 2 - 10)
    const ins = edge.movie ? getInsight(edge) : null

    return {
      edge,
      index: i,
      pathD: edgePath(a, b, i),
      connectorStartPathD: isTimeline ? timelineConnectorPath(a, timelineCards[0], nodeR + 7) : null,
      connectorEndPathD: isTimeline ? timelineConnectorPath(b, timelineCards[timelineCards.length - 1], nodeR + 7) : null,
      timelinePathD: isTimeline ? timelinePath(timelineCards) : null,
      isActive: activeEdge === i,
      label,
      mediaType: mediaTypeLabel(edge),
      isTimeline,
      displayWork,
      timelineCards: timelineCards.map(card => ({
        ...card,
        ins: getInsight(edge, card.work),
      })),
      hiddenTimelineCount,
      hasPoster,
      cardWidth,
      cardHeight,
      labelX,
      labelY,
      ins,
      edgeWithIndex: { ...edge, index: i, displayWork },
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
                {!visual.isTimeline && (
                  <path
                    d={visual.pathD}
                    fill="none"
                    className={`graph-edge ${visual.isActive ? 'active' : ''}`}
                  />
                )}

                {visual.connectorStartPathD && (
                  <path
                    d={visual.connectorStartPathD}
                    fill="none"
                    className={`graph-edge ${visual.isActive ? 'active' : ''}`}
                  />
                )}

                {visual.connectorEndPathD && (
                  <path
                    d={visual.connectorEndPathD}
                    fill="none"
                    className={`graph-edge ${visual.isActive ? 'active' : ''}`}
                  />
                )}

                {visual.timelinePathD && (
                  <path
                    d={visual.timelinePathD}
                    fill="none"
                    className={`graph-timeline-link ${visual.isActive ? 'active' : ''}`}
                  />
                )}

                {!visual.isTimeline && (
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
                )}
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
          {edgeVisuals.filter(visual => visual.edge.movie && !visual.isTimeline).map(visual => (
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
              aria-label={
                visual.isTimeline
                  ? `Ver linha do tempo de ${actors[visual.edge.fromIdx].name} e ${actors[visual.edge.toIdx].name}`
                  : `Ver curiosidade sobre ${visual.label}`
              }
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
                  src={visual.displayWork.poster}
                  alt={visual.displayWork.title}
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

          {edgeVisuals.filter(visual => visual.edge.movie && visual.isTimeline).map(visual => (
            <div key={`timeline-cards-${visual.index}`} className="graph-timeline-cards">
              {visual.timelineCards.map(card => (
                <button
                  type="button"
                  key={`timeline-card-${visual.index}-${workKey(card.work, card.index)}`}
                  className={`graph-timeline-card ${visual.isActive ? 'active' : ''}`}
                  style={{
                    left: card.x,
                    top: card.y,
                    width: card.width,
                    minHeight: card.height,
                  }}
                  aria-label={`${card.work.year || 'Ano desconhecido'} - ${card.work.title || 'Obra sem titulo'}`}
                  onMouseEnter={ev => showEdgeTip(ev, visual.edgeWithIndex, card.ins, card.work)}
                  onMouseMove={moveTip}
                  onMouseLeave={() => { setActiveEdge(null); setTip(null) }}
                  onFocus={ev => {
                    const rect = ev.currentTarget.getBoundingClientRect()
                    showEdgeTip(
                      { clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 },
                      visual.edgeWithIndex,
                      card.ins,
                      card.work,
                    )
                  }}
                  onBlur={() => { setActiveEdge(null); setTip(null) }}
                  onClick={ev => showEdgeTip(ev, visual.edgeWithIndex, card.ins, card.work)}
                >
                  {card.work.poster ? (
                    <img
                      src={card.work.poster}
                      alt={card.work.title || 'Obra sem titulo'}
                      className="graph-timeline-poster"
                      draggable="false"
                    />
                  ) : (
                    <span className="graph-timeline-placeholder">
                      {card.work.type === 'tv' ? 'Serie' : 'Filme'}
                    </span>
                  )}
                  <span className="graph-timeline-copy">
                    <span className="graph-timeline-year">{card.work.year || '----'}</span>
                    <span className="graph-timeline-title">
                      {card.work.title || 'Obra sem titulo'}
                    </span>
                    <span className="graph-timeline-kind">{mediaTypeLabel({ movie: card.work, timelineTotal: 0, timeline: [] })}</span>
                    {workMeta(card.work) && (
                      <span className="graph-timeline-meta">{workMeta(card.work)}</span>
                    )}
                  </span>
                </button>
              ))}

              {visual.hiddenTimelineCount > 0 && visual.timelineCards.length > 0 && (
                <span
                  className="graph-timeline-more"
                  style={{
                    left: visual.timelineCards[visual.timelineCards.length - 1].x,
                    top: visual.timelineCards[visual.timelineCards.length - 1].y + 46,
                  }}
                >
                  +{visual.hiddenTimelineCount}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {tip && (
        <div
          className="graph-tooltip"
          style={{
            left: Math.min(Math.max(tip.x + 16, 12), Math.max(12, dims.w - 372)),
            top: Math.max(tip.y - 104, 12),
          }}
        >
          {(tip.timelineTotal || 0) <= 1 && tip.movie?.poster && (
            <img src={tip.movie.poster} alt={tip.movie.title}
              className="graph-tooltip-poster" />
          )}
          <div className="graph-tooltip-body">
            {(tip.timelineTotal || 0) > 1 ? (
              <>
                <div className="graph-tooltip-title">
                  {tip.timelineTotal} obras em comum
                </div>
                <div className="graph-tooltip-actors">
                  {tip.actorLeft} - {tip.actorRight}
                </div>
                <div className="graph-tooltip-timeline">
                  {tip.timeline.map((work, workIndex) => (
                    <div className="graph-tooltip-timeitem" key={workKey(work, workIndex)}>
                      <span className="graph-tooltip-year">{work.year || '----'}</span>
                      <span className="graph-tooltip-work">
                        {work.title || 'Obra sem titulo'}
                        {workMeta(work) && (
                          <span className="graph-tooltip-meta">{workMeta(work)}</span>
                        )}
                      </span>
                    </div>
                  ))}
                  {tip.timelineTotal > tip.timeline.length && (
                    <div className="graph-tooltip-more">
                      +{tip.timelineTotal - tip.timeline.length} obras
                    </div>
                  )}
                </div>
                {tip.insight && (
                  <div className="graph-tooltip-text">{tip.insight}</div>
                )}
              </>
            ) : (
              <>
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
                {workMeta(tip.movie) && (
                  <div className="graph-tooltip-text muted">
                    {workMeta(tip.movie)} em comum nessa serie.
                  </div>
                )}
                {tip.insight ? (
                  <div className="graph-tooltip-text">{tip.insight}</div>
                ) : insightState === 'loading' ? (
                  <div className="graph-tooltip-text muted">Carregando curiosidade...</div>
                ) : insightState === 'error' ? (
                  <div className="graph-tooltip-text muted">
                    O grafo ficou pronto, mas a curiosidade dessa conexao nao voltou agora.
                  </div>
                ) : (
                  <div className="graph-tooltip-text muted">
                    {tip.actorLeft} e {tip.actorRight} aparecem juntos nessa obra da linha do tempo.
                  </div>
                )}
              </>
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

function buildTimelineCards({
  works,
  a,
  b,
  bend,
  canvas,
  nodeR,
  fitScale,
  isCompact,
  hiddenTimelineCount,
}) {
  const count = works.length
  if (!count) return []

  const distance = Math.hypot(b.x - a.x, b.y - a.y)
  const gap = isCompact ? 10 : Math.max(10, Math.round(14 * fitScale))
  const usable = Math.max(120, distance - nodeR * 2 - 44)
  const rawWidth = (usable - gap * Math.max(0, count - 1)) / count
  const maxWidth = isCompact ? Math.min(212, canvas.w - 64) : Math.round(clamp(176 * fitScale, 122, 176))
  const minWidth = isCompact ? 138 : 108
  const width = Math.round(clamp(rawWidth, Math.min(minWidth, maxWidth), maxWidth))
  const height = isCompact ? 74 : Math.round(clamp(76 * fitScale, 58, 76))
  const moreLift = hiddenTimelineCount ? 8 : 0
  const laneAmplitude = isCompact
    ? Math.min(52, canvas.h * 0.12)
    : Math.min(70, canvas.h * 0.16)

  return works.map((work, index) => {
    const point = quadraticPoint(a, b, bend, (index + 1) / (count + 1))
    const tangent = quadraticTangent(a, b, bend, (index + 1) / (count + 1))
    const normal = normalizeVector({ x: -tangent.y, y: tangent.x })
    const laneSign = index % 2 === 0 ? -1 : 1
    const laneOffset = count === 1 ? 0 : laneSign * laneAmplitude
    const cardX = point.x + normal.x * laneOffset
    const cardY = point.y + normal.y * laneOffset

    const x = clamp(cardX, width / 2 + 8, canvas.w - width / 2 - 8)
    const y = clamp(
      cardY - moreLift,
      height / 2 + 10,
      canvas.h - height / 2 - 10,
    )

    return {
      work,
      index,
      x,
      y,
      width,
      height,
    }
  })
}

function quadraticPoint(a, b, bend, t) {
  const mx = (a.x + b.x) / 2
  const my = (a.y + b.y) / 2
  const control = { x: mx, y: my + bend }
  const inv = 1 - t

  return {
    x: inv * inv * a.x + 2 * inv * t * control.x + t * t * b.x,
    y: inv * inv * a.y + 2 * inv * t * control.y + t * t * b.y,
  }
}

function quadraticTangent(a, b, bend, t) {
  const mx = (a.x + b.x) / 2
  const my = (a.y + b.y) / 2
  const control = { x: mx, y: my + bend }

  return {
    x: 2 * (1 - t) * (control.x - a.x) + 2 * t * (b.x - control.x),
    y: 2 * (1 - t) * (control.y - a.y) + 2 * t * (b.y - control.y),
  }
}

function normalizeVector(vector) {
  const length = Math.hypot(vector.x, vector.y)
  if (!length) return { x: 0, y: -1 }

  return {
    x: vector.x / length,
    y: vector.y / length,
  }
}

function rectAnchorPoint(card, target) {
  const halfW = card.width / 2
  const halfH = card.height / 2
  const dx = target.x - card.x
  const dy = target.y - card.y

  if (!dx && !dy) {
    return { x: card.x, y: card.y }
  }

  const scale = 1 / Math.max(
    Math.abs(dx) / Math.max(halfW, 1),
    Math.abs(dy) / Math.max(halfH, 1),
  )

  return {
    x: card.x + dx * scale,
    y: card.y + dy * scale,
  }
}

function circleAnchorPoint(circle, target, radius) {
  const dx = target.x - circle.x
  const dy = target.y - circle.y
  const normal = normalizeVector({ x: dx, y: dy })

  return {
    x: circle.x + normal.x * radius,
    y: circle.y + normal.y * radius,
  }
}

function getStepTimeline(step) {
  const timeline = Array.isArray(step.timeline)
    ? step.timeline.filter(Boolean)
    : []

  if (timeline.length > 0) return timeline
  return step.movie ? [step.movie] : []
}

function workLabel(work) {
  if (!work) return 'Conexao'

  const title = work.title || 'Conexao'
  return work.year ? `${title} (${work.year})` : title
}

function singleDisplayWork(edge) {
  const timelineWork = edge.timeline?.[0]
  if (
    edge.timelineTotal <= 1
    && timelineWork?.type === 'tv'
    && timelineWork.shared_episode_count
  ) {
    return timelineWork
  }

  return edge.movie || timelineWork
}

function workMeta(work) {
  const episodeCount = Number(work?.shared_episode_count || 0)
  if (episodeCount <= 1) return null
  return `${episodeCount} eps.`
}

function workKey(work, index) {
  if (!work) return `work-${index}`

  const id = work.type === 'tv'
    ? work.id || `${work.series_id}-${work.season_number}-${work.episode_number}`
    : work.id
  return `${work.type || 'work'}-${id || index}`
}

export default PathGraph
