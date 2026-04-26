from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

import requests
from django.conf import settings

from . import tmdb

ACTOR_FETCH_WORKERS = 16
CAST_FETCH_WORKERS = 12
FRONTIER_SCAN_BATCH = 8
CAST_EXPANSION_BATCH = 6
TIMELINE_MAX_DEGREES = 3
TIMELINE_MAX_WORKS = 8

SOURCE_SIDE = 'source'
TARGET_SIDE = 'target'

FAST_PROFILE = {
    'time_budget_seconds': 8,
    'max_frontier_size': 80,
    'max_credit_batch': 90,
    'frontier_limits': [80, 60, 45, 35, 30, 25],
    'credit_limits': [18, 12, 8, 6, 5, 4],
    'cast_limits': [22, 16, 12, 10, 8, 6],
    'episode_limits': [6, 3, 2, 1, 1, 1],
}

DEEP_PROFILE = {
    'time_budget_seconds': settings.SEARCH_DEEP_TIME_BUDGET_SECONDS,
    'max_frontier_size': None,
    'max_credit_batch': 170,
    'frontier_limits': [160, 55, 46, 38, 32, 26],
    'credit_limits': [30, 16, 11, 8, 6, 5],
    'cast_limits': [34, 20, 15, 10, 8, 6],
    'episode_limits': [8, 3, 2, 1, 1, 1],
}


class SearchBudgetExceeded(Exception):
    pass


class SearchCancelled(Exception):
    pass


def find_path(
    actor_a_id,
    actor_b_id,
    max_degrees=6,
    search_profile='fast',
    progress_callback=None,
    cancel_check=None,
):
    profile = DEEP_PROFILE if search_profile == 'deep' else FAST_PROFILE
    deadline = None
    if profile['time_budget_seconds'] is not None:
        deadline = perf_counter() + profile['time_budget_seconds']

    with ThreadPoolExecutor(max_workers=4) as pool:
        future_actor_a = pool.submit(tmdb.get_actor_summary, actor_a_id)
        future_actor_b = pool.submit(tmdb.get_actor_summary, actor_b_id)
        future_credits_a = pool.submit(tmdb.get_actor_all_credits, actor_a_id)
        future_credits_b = pool.submit(tmdb.get_actor_all_credits, actor_b_id)

        actor_a = future_actor_a.result()
        actor_b = future_actor_b.result()
        credits_a = future_credits_a.result()
        credits_b = future_credits_b.result()

    if actor_a_id == actor_b_id:
        result = [_build_step(actor_a, None)]
        _emit_progress(
            progress_callback,
            {
                'stage': 'found',
                'depth': 0,
                'explored_actors': 1,
                'frontier_size': 1,
                'frontier_sample': [actor_a['name']],
                'message': 'Os dois nomes apontam para a mesma pessoa.',
            },
        )
        return _enrich_short_path_timeline(result)

    credit_indexes = {
        actor_a_id: _index_credits(credits_a),
        actor_b_id: _index_credits(credits_b),
    }
    credits_cache = {
        actor_a_id: credits_a,
        actor_b_id: credits_b,
    }
    side_credit_indexes = {
        SOURCE_SIDE: {},
        TARGET_SIDE: {},
    }
    _add_actor_credits_to_side_index(side_credit_indexes[SOURCE_SIDE], actor_a_id, credits_a)
    _add_actor_credits_to_side_index(side_credit_indexes[TARGET_SIDE], actor_b_id, credits_b)

    direct_credit = _find_shared_credit(
        actor_a_id,
        credits_a,
        actor_b_id,
        credit_indexes[actor_b_id],
    )
    if direct_credit:
        result = [
            _build_step(actor_a, direct_credit),
            _build_step(actor_b, None),
        ]
        _emit_progress(
            progress_callback,
            {
                'stage': 'found',
                'depth': 1,
                'explored_actors': 2,
                'frontier_size': 2,
                'frontier_sample': [actor_a['name'], actor_b['name']],
                'message': 'Conexao direta encontrada.',
                'history_entry': {
                    'depth': 1,
                    'label': 'Conexao direta',
                    'sample_names': [actor_a['name'], actor_b['name']],
                    'discovered_count': 2,
                },
            },
        )
        return _enrich_short_path_timeline(result)

    visited = {
        SOURCE_SIDE: {
            actor_a_id: {
                'parent': None,
                'credit': None,
                'depth': 0,
                'actor': actor_a,
            },
        },
        TARGET_SIDE: {
            actor_b_id: {
                'parent': None,
                'credit': None,
                'depth': 0,
                'actor': actor_b,
            },
        },
    }
    frontiers = {
        SOURCE_SIDE: [actor_a_id],
        TARGET_SIDE: [actor_b_id],
    }
    expanded_credits = {
        SOURCE_SIDE: set(),
        TARGET_SIDE: set(),
    }

    _emit_progress(
        progress_callback,
        {
            'stage': 'starting',
            'depth': 0,
            'explored_actors': 2,
            'frontier_size': 2,
            'frontier_sample': [actor_a['name'], actor_b['name']],
            'message': (
                f'Busca bidirecional entre {actor_a["name"]} e '
                f'{actor_b["name"]}.'
            ),
        },
    )

    while frontiers[SOURCE_SIDE] or frontiers[TARGET_SIDE]:
        _check_runtime_constraints(deadline, cancel_check)

        side = _select_side_to_expand(frontiers, visited, max_degrees)
        if not side:
            break

        other_side = _other_side(side)
        frontier = frontiers[side]
        current_depth = _frontier_depth(frontier, visited[side])
        frontier = _trim_frontier(frontier, profile, current_depth)
        frontiers[side] = frontier
        if _frontier_exceeded(frontier, profile):
            raise SearchBudgetExceeded()

        credit_limit = _limit_for_depth(profile['credit_limits'], current_depth)
        cast_limit = _limit_for_depth(profile['cast_limits'], current_depth)
        episode_limit = _limit_for_depth(profile['episode_limits'], current_depth)

        _emit_progress(
            progress_callback,
            {
                'stage': 'exploring',
                'depth': current_depth,
                'explored_actors': _visited_count(visited),
                'frontier_size': len(frontier),
                'frontier_sample': _sample_frontier_names(frontier, visited[side]),
                'message': (
                    f'Expandindo {_side_label(side)} no grau '
                    f'{current_depth + 1} de {max_degrees}.'
                ),
            },
        )

        credits_by_actor = {}
        for frontier_chunk in _iter_chunks(frontier, FRONTIER_SCAN_BATCH):
            chunk_credits = _load_frontier_credits(frontier_chunk, credit_limit)
            credits_by_actor.update(chunk_credits)
            for actor_id, credits in chunk_credits.items():
                cached_credits = credits_cache.get(actor_id)
                if cached_credits is None or len(credits) > len(cached_credits):
                    credits_cache[actor_id] = credits
                    credit_indexes[actor_id] = _index_credits(credits)
                    _add_actor_credits_to_side_index(
                        side_credit_indexes[side],
                        actor_id,
                        credits,
                    )

            direct_result = _find_direct_bridge(
                side=side,
                frontier_chunk=frontier_chunk,
                chunk_credits=chunk_credits,
                visited=visited,
                credit_indexes=credit_indexes,
                side_credit_indexes=side_credit_indexes,
                max_degrees=max_degrees,
            )
            if direct_result:
                direct_result = _enrich_short_path_timeline(direct_result)
                _emit_found(progress_callback, direct_result, visited, frontiers)
                return direct_result

        if current_depth >= max_degrees:
            frontiers[side] = []
            continue

        credits_to_expand = _collect_credits_to_expand(
            side,
            frontier,
            credits_by_actor,
            expanded_credits[side],
            profile['max_credit_batch'],
        )

        next_frontier = []
        queued = set()

        for credit_chunk in _iter_chunks(credits_to_expand, CAST_EXPANSION_BATCH):
            for (actor_id, credit), neighbors in _load_neighbor_edges(
                credit_chunk,
                cast_limit,
                episode_limit,
            ):
                _check_runtime_constraints(deadline, cancel_check)
                actor_node = visited[side][actor_id]
                neighbor_depth = actor_node['depth'] + 1

                for member, edge_credit in neighbors:
                    member_id = member.get('id')
                    if not member_id or member_id == actor_id:
                        continue

                    if member_id in visited[other_side]:
                        if member_id not in visited[side]:
                            visited[side][member_id] = {
                                'parent': actor_id,
                                'credit': edge_credit,
                                'depth': neighbor_depth,
                                'actor': member,
                            }

                        if _combined_depth(member_id, visited) <= max_degrees:
                            result = _build_bidirectional_path(
                                member_id,
                                visited[SOURCE_SIDE],
                                visited[TARGET_SIDE],
                            )
                            result = _enrich_short_path_timeline(result)
                            _emit_found(progress_callback, result, visited, frontiers)
                            return result

                    if member_id in visited[side]:
                        continue

                    visited[side][member_id] = {
                        'parent': actor_id,
                        'credit': edge_credit,
                        'depth': neighbor_depth,
                        'actor': member,
                    }
                    if member_id not in queued:
                        queued.add(member_id)
                        next_frontier.append(member_id)

        next_frontier = _trim_frontier(next_frontier, profile, current_depth + 1)

        _emit_progress(
            progress_callback,
            {
                'stage': 'layer_complete',
                'depth': current_depth + 1,
                'explored_actors': _visited_count(visited),
                'frontier_size': len(next_frontier),
                'frontier_sample': _sample_frontier_names(next_frontier, visited[side]),
                'message': f'{_side_label(side).capitalize()} grau {current_depth + 1} concluido.',
                'history_entry': {
                    'depth': current_depth + 1,
                    'label': f'{_side_label(side).capitalize()} grau {current_depth + 1}',
                    'sample_names': _sample_frontier_names(next_frontier, visited[side], limit=5),
                    'discovered_count': len(next_frontier),
                },
            },
        )

        frontiers[side] = next_frontier

    _emit_progress(
        progress_callback,
        {
            'stage': 'not_found',
            'depth': max_degrees,
            'explored_actors': _visited_count(visited),
            'frontier_size': 0,
            'frontier_sample': [],
            'message': f'Nenhuma conexao encontrada em ate {max_degrees} graus.',
        },
    )
    return None


def _load_frontier_credits(frontier, credit_limit):
    if len(frontier) == 1:
        actor_id = frontier[0]
        return {actor_id: _safe_get_actor_credits(actor_id, credit_limit)}

    results = {}
    with ThreadPoolExecutor(max_workers=min(ACTOR_FETCH_WORKERS, len(frontier))) as pool:
        future_map = {
            pool.submit(tmdb.get_actor_credits, actor_id, credit_limit): actor_id
            for actor_id in frontier
        }
        for future in as_completed(future_map):
            actor_id = future_map[future]
            try:
                results[actor_id] = future.result()
            except requests.RequestException:
                results[actor_id] = []
    return results


def _load_neighbor_edges(actor_credit_pairs, cast_limit, episode_limit):
    if not actor_credit_pairs:
        return []

    if len(actor_credit_pairs) == 1:
        actor_id, credit = actor_credit_pairs[0]
        return [
            (
                (actor_id, credit),
                _safe_get_credit_cast(actor_id, credit, cast_limit, episode_limit),
            )
        ]

    results = [None] * len(actor_credit_pairs)
    with ThreadPoolExecutor(max_workers=min(CAST_FETCH_WORKERS, len(actor_credit_pairs))) as pool:
        future_map = {
            pool.submit(
                tmdb.get_credit_cast,
                actor_id,
                credit,
                cast_limit,
                episode_limit,
            ): idx
            for idx, (actor_id, credit) in enumerate(actor_credit_pairs)
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                results[idx] = future.result()
            except requests.RequestException:
                results[idx] = []

    return list(zip(actor_credit_pairs, results))


def _find_direct_bridge(
    side,
    frontier_chunk,
    chunk_credits,
    visited,
    credit_indexes,
    side_credit_indexes,
    max_degrees,
):
    other_side = _other_side(side)
    other_credit_index = side_credit_indexes[other_side]

    for actor_id in frontier_chunk:
        node = visited[side][actor_id]
        credits = chunk_credits.get(actor_id) or []

        other_node = visited[other_side].get(actor_id)
        if other_node and node['depth'] + other_node['depth'] <= max_degrees:
            return _build_bidirectional_path(
                actor_id,
                visited[SOURCE_SIDE],
                visited[TARGET_SIDE],
            )

        for credit in credits:
            credit_key = _credit_key(credit)
            if not credit_key:
                continue

            candidate_actor_ids = other_credit_index.get(credit_key)
            if not candidate_actor_ids:
                continue

            for other_actor_id in candidate_actor_ids:
                other_node = visited[other_side].get(other_actor_id)
                if not other_node:
                    continue

                if actor_id == other_actor_id:
                    continue

                if node['depth'] + other_node['depth'] + 1 > max_degrees:
                    continue

                target_index = credit_indexes.get(other_actor_id)
                if target_index is None:
                    continue

                shared_credit = _find_shared_credit(
                    actor_id,
                    [credit],
                    other_actor_id,
                    target_index,
                )
                if not shared_credit:
                    continue

                if side == SOURCE_SIDE:
                    return _build_path_between_trees(
                        actor_id,
                        other_actor_id,
                        shared_credit,
                        visited[SOURCE_SIDE],
                        visited[TARGET_SIDE],
                    )

                return _build_path_between_trees(
                    other_actor_id,
                    actor_id,
                    shared_credit,
                    visited[SOURCE_SIDE],
                    visited[TARGET_SIDE],
                )

    return None


def _find_shared_credit(actor_id, credits, target_actor_id, target_index):
    for credit in credits:
        target = target_index.get(_credit_key(credit))
        if not target:
            continue

        if credit.get('type') == 'tv':
            try:
                shared_episode = tmdb.find_shared_tv_episode(actor_id, credit, target_actor_id, target)
            except requests.RequestException:
                shared_episode = None
            if shared_episode:
                return shared_episode
            continue

        return {
            'id': credit.get('id'),
            'type': 'movie',
            'title': credit.get('title') or target.get('title'),
            'year': credit.get('year') or target.get('year'),
            'poster': credit.get('poster') or target.get('poster'),
        }
    return None


def _enrich_short_path_timeline(path):
    degrees = len(path) - 1
    if degrees <= 0 or degrees > TIMELINE_MAX_DEGREES:
        return path

    for idx in range(degrees):
        actor_left = path[idx].get('actor') or {}
        actor_right = path[idx + 1].get('actor') or {}
        primary_work = path[idx].get('movie')

        try:
            timeline = _find_shared_works(
                actor_left.get('id'),
                actor_right.get('id'),
                primary_work,
            )
        except requests.RequestException:
            timeline = []

        if not timeline and primary_work:
            timeline = [primary_work]

        if timeline:
            path[idx]['timeline_total'] = len(timeline)
            path[idx]['timeline'] = _limit_timeline(timeline, primary_work)

    return path


def _find_shared_works(actor_a_id, actor_b_id, primary_work=None):
    if not actor_a_id or not actor_b_id:
        return []

    credits_a = tmdb.get_actor_all_credits(actor_a_id)
    credits_b = tmdb.get_actor_all_credits(actor_b_id)
    index_b = _index_credits(credits_b)
    shared = []
    seen = set()

    _add_timeline_work(shared, seen, primary_work)

    for credit in credits_a:
        target = index_b.get(_credit_key(credit))
        if not target:
            continue

        if credit.get('type') == 'tv':
            try:
                works = tmdb.find_shared_tv_episodes(actor_a_id, credit, actor_b_id, target)
            except requests.RequestException:
                continue
            if not works:
                continue
            _add_timeline_work(
                shared,
                seen,
                _build_tv_series_timeline_work(credit, target, works),
            )
            continue
        else:
            work = {
                'id': credit.get('id'),
                'type': 'movie',
                'title': credit.get('title') or target.get('title'),
                'year': credit.get('year') or target.get('year'),
                'poster': credit.get('poster') or target.get('poster'),
            }

        _add_timeline_work(shared, seen, _build_movie(work))

    return sorted(shared, key=_timeline_sort_key)


def _add_timeline_work(shared, seen, work):
    if not work:
        return

    normalized = _build_timeline_work(work)
    work_key = _timeline_work_key(normalized)
    if not work_key:
        return

    if work_key in seen:
        for existing in shared:
            if _timeline_work_key(existing) == work_key:
                _merge_timeline_work(existing, normalized)
                break
        return

    seen.add(work_key)
    shared.append(normalized)


def _build_timeline_work(work):
    if work.get('type') == 'tv':
        series_id = work.get('series_id') or work.get('id')
        series_title = work.get('series_title') or work.get('title')
        timeline_work = {
            'id': series_id,
            'type': 'tv',
            'title': series_title,
            'year': str(work.get('year') or ''),
            'poster': work.get('poster'),
            'series_id': series_id,
            'series_title': series_title,
        }
        if work.get('shared_episode_count') is not None:
            timeline_work['shared_episode_count'] = work.get('shared_episode_count')
        return timeline_work

    return _build_movie(work)


def _build_tv_series_timeline_work(credit, target, episode_works):
    first_episode = episode_works[0] if episode_works else {}
    series_title = (
        first_episode.get('series_title')
        or credit.get('title')
        or target.get('title')
        or first_episode.get('title')
    )
    return {
        'id': credit.get('id') or target.get('id') or first_episode.get('series_id'),
        'type': 'tv',
        'title': series_title,
        'year': credit.get('year') or target.get('year') or first_episode.get('year'),
        'poster': credit.get('poster') or target.get('poster') or first_episode.get('poster'),
        'series_id': credit.get('id') or target.get('id') or first_episode.get('series_id'),
        'series_title': series_title,
        'shared_episode_count': len(episode_works),
    }


def _merge_timeline_work(existing, incoming):
    for key in ('title', 'year', 'poster', 'series_id', 'series_title'):
        if not existing.get(key) and incoming.get(key):
            existing[key] = incoming.get(key)

    incoming_episode_count = incoming.get('shared_episode_count')
    if incoming_episode_count is not None:
        existing['shared_episode_count'] = max(
            existing.get('shared_episode_count') or 0,
            incoming_episode_count,
        )


def _limit_timeline(timeline, primary_work):
    if len(timeline) <= TIMELINE_MAX_WORKS:
        return timeline

    limited = timeline[:TIMELINE_MAX_WORKS]
    primary_key = _timeline_work_key(primary_work)
    if primary_key and primary_key not in {_timeline_work_key(work) for work in limited}:
        limited[-1] = _build_timeline_work(primary_work)
        limited = sorted(limited, key=_timeline_sort_key)
    return limited


def _timeline_work_key(work):
    if not work:
        return None

    if work.get('type') == 'tv':
        return (
            'tv',
            work.get('series_id') or work.get('id'),
        )
    return work.get('type'), work.get('id')


def _timeline_sort_key(work):
    year = _timeline_year(work)
    return (
        year if year else 9999,
        (work.get('title') or '').lower(),
        work.get('id') or 0,
    )


def _timeline_year(work):
    try:
        return int(work.get('year') or 0)
    except (TypeError, ValueError):
        return 0


def _safe_get_actor_credits(actor_id, credit_limit):
    try:
        return tmdb.get_actor_credits(actor_id, credit_limit)
    except requests.RequestException:
        return []


def _safe_get_credit_cast(actor_id, credit, cast_limit, episode_limit):
    try:
        return tmdb.get_credit_cast(actor_id, credit, cast_limit, episode_limit)
    except requests.RequestException:
        return []


def _collect_credits_to_expand(side, frontier, credits_by_actor, expanded_credits, max_credit_batch):
    credits_to_expand = []

    for actor_id, credit in _iter_round_robin_credits(frontier, credits_by_actor):
        expansion_key = _expansion_key(actor_id, credit)
        if expansion_key in expanded_credits:
            continue

        expanded_credits.add(expansion_key)
        credits_to_expand.append((actor_id, credit))
        if max_credit_batch and len(credits_to_expand) >= max_credit_batch:
            return credits_to_expand

    return credits_to_expand


def _iter_round_robin_credits(frontier, credits_by_actor):
    ordered_credits = {
        actor_id: _order_credits_for_expansion(credits_by_actor.get(actor_id, []))
        for actor_id in frontier
    }
    depth = 0
    while True:
        yielded = False
        for actor_id in frontier:
            credits = ordered_credits.get(actor_id) or []
            if depth >= len(credits):
                continue

            yielded = True
            yield actor_id, credits[depth]

        if not yielded:
            return

        depth += 1


def _order_credits_for_expansion(credits):
    movies = [credit for credit in credits if credit.get('type') == 'movie']
    tv = [credit for credit in credits if credit.get('type') == 'tv']
    return list(_interleave(movies, tv))


def _interleave(primary, secondary):
    max_len = max(len(primary), len(secondary))
    for idx in range(max_len):
        if idx < len(primary):
            yield primary[idx]
        if idx < len(secondary):
            yield secondary[idx]


def _expansion_key(actor_id, credit):
    if credit.get('type') == 'tv':
        return ('tv', actor_id, credit.get('id'), credit.get('credit_id'))
    return ('movie', credit.get('id'))


def _credit_key(credit):
    credit_id = credit.get('id')
    credit_type = credit.get('type')
    if not credit_id or not credit_type:
        return None
    return credit_id, credit_type


def _index_credits(credits):
    return {
        _credit_key(credit): credit
        for credit in credits
        if _credit_key(credit)
    }


def _add_actor_credits_to_side_index(side_index, actor_id, credits):
    for credit in credits:
        credit_key = _credit_key(credit)
        if not credit_key:
            continue
        side_index.setdefault(credit_key, set()).add(actor_id)


def _build_bidirectional_path(meet_actor_id, source_visited, target_visited):
    source_nodes = _path_from_root(meet_actor_id, source_visited)
    target_nodes = _path_to_root(meet_actor_id, target_visited)

    steps = []
    for idx, current in enumerate(source_nodes):
        if idx < len(source_nodes) - 1:
            next_credit = source_nodes[idx + 1]['credit']
        elif len(target_nodes) > 1:
            next_credit = target_nodes[0]['credit']
        else:
            next_credit = None
        steps.append(_build_step(current['actor'], next_credit))

    for idx in range(1, len(target_nodes)):
        current = target_nodes[idx]
        next_credit = current['credit'] if idx < len(target_nodes) - 1 else None
        steps.append(_build_step(current['actor'], next_credit))

    return steps


def _build_path_between_trees(source_actor_id, target_actor_id, bridge_credit, source_visited, target_visited):
    if source_actor_id == target_actor_id:
        return _build_bidirectional_path(source_actor_id, source_visited, target_visited)

    source_nodes = _path_from_root(source_actor_id, source_visited)
    target_nodes = _path_to_root(target_actor_id, target_visited)

    steps = []
    for idx, current in enumerate(source_nodes):
        next_credit = source_nodes[idx + 1]['credit'] if idx < len(source_nodes) - 1 else bridge_credit
        steps.append(_build_step(current['actor'], next_credit))

    for idx, current in enumerate(target_nodes):
        next_credit = current['credit'] if idx < len(target_nodes) - 1 else None
        steps.append(_build_step(current['actor'], next_credit))

    return steps


def _path_from_root(actor_id, visited):
    nodes = _path_to_root(actor_id, visited)
    nodes.reverse()
    return nodes


def _path_to_root(actor_id, visited):
    nodes = []
    node = actor_id
    while node is not None:
        nodes.append(visited[node])
        node = visited[node]['parent']
    return nodes


def _combined_depth(actor_id, visited):
    return visited[SOURCE_SIDE][actor_id]['depth'] + visited[TARGET_SIDE][actor_id]['depth']


def _select_side_to_expand(frontiers, visited, max_degrees):
    candidates = []
    for side in (SOURCE_SIDE, TARGET_SIDE):
        frontier = frontiers[side]
        if not frontier:
            continue
        if _frontier_depth(frontier, visited[side]) >= max_degrees:
            continue
        candidates.append(side)

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda side: (
            len(frontiers[side]),
            _frontier_depth(frontiers[side], visited[side]),
        ),
    )


def _frontier_depth(frontier, visited):
    if not frontier:
        return 0
    return min(visited[actor_id]['depth'] for actor_id in frontier)


def _trim_frontier(frontier, profile, depth):
    frontier_limit = _limit_for_depth(profile.get('frontier_limits', []), depth)
    if frontier_limit is None:
        return frontier
    return frontier[:frontier_limit]


def _limit_for_depth(limits, depth):
    if not limits:
        return None
    if depth < len(limits):
        return limits[depth]
    return limits[-1]


def _frontier_exceeded(frontier, profile):
    max_frontier_size = profile['max_frontier_size']
    return bool(max_frontier_size and len(frontier) > max_frontier_size)


def _check_runtime_constraints(deadline, cancel_check):
    if cancel_check and cancel_check():
        raise SearchCancelled()
    if deadline is not None and perf_counter() > deadline:
        raise SearchBudgetExceeded()


def _sample_frontier_names(frontier, visited, limit=4):
    names = []
    for actor_id in frontier[:limit]:
        actor = visited.get(actor_id, {}).get('actor')
        if actor:
            names.append(actor.get('name'))
    return names


def _visited_count(visited):
    return len(set(visited[SOURCE_SIDE]) | set(visited[TARGET_SIDE]))


def _iter_chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _other_side(side):
    return TARGET_SIDE if side == SOURCE_SIDE else SOURCE_SIDE


def _side_label(side):
    return 'origem' if side == SOURCE_SIDE else 'destino'


def _emit_progress(progress_callback, payload):
    if progress_callback:
        progress_callback(payload)


def _emit_found(progress_callback, result, visited, frontiers):
    _emit_progress(
        progress_callback,
        {
            'stage': 'found',
            'depth': len(result) - 1,
            'explored_actors': _visited_count(visited),
            'frontier_size': len(frontiers[SOURCE_SIDE]) + len(frontiers[TARGET_SIDE]),
            'frontier_sample': (
                _sample_frontier_names(frontiers[SOURCE_SIDE], visited[SOURCE_SIDE], limit=2)
                + _sample_frontier_names(frontiers[TARGET_SIDE], visited[TARGET_SIDE], limit=2)
            ),
            'message': 'Conexao encontrada.',
            'history_entry': {
                'depth': len(result) - 1,
                'label': f'Conexao em {len(result) - 1} graus',
                'sample_names': [step['actor']['name'] for step in result[:5]],
                'discovered_count': len(result),
            },
        },
    )


def _build_step(actor, credit):
    return {
        'actor': actor,
        'movie': _build_movie(credit) if credit else None,
    }


def _build_movie(credit):
    movie = {
        'id': credit.get('id'),
        'title': credit.get('title'),
        'year': str(credit.get('year') or ''),
        'poster': credit.get('poster'),
        'type': credit.get('type'),
    }
    for key in (
        'series_id',
        'series_title',
        'episode_title',
        'season_number',
        'episode_number',
    ):
        if credit.get(key) is not None:
            movie[key] = credit.get(key)
    return movie
