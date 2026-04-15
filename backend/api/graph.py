from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

from . import tmdb

ACTOR_FETCH_WORKERS = 16
CAST_FETCH_WORKERS = 12
FRONTIER_SCAN_BATCH = 8
CAST_EXPANSION_BATCH = 6

FAST_PROFILE = {
    'time_budget_seconds': 8,
    'max_frontier_size': 80,
    'max_credit_batch': 120,
    'two_hop_source_credit_limit': 18,
    'two_hop_cast_limit': 48,
    'two_hop_candidate_credit_limit': 24,
    'two_hop_candidate_limit': 72,
    'two_hop_candidate_batch': 6,
    'target_neighbor_credit_limit': 24,
    'target_neighbor_cast_limit': 48,
    'credit_limits': [16, 10, 6, 4],
    'cast_limits': [16, 10, 6, 4],
}

DEEP_PROFILE = {
    'time_budget_seconds': None,
    'max_frontier_size': None,
    'max_credit_batch': None,
    'two_hop_source_credit_limit': 30,
    'two_hop_cast_limit': 120,
    'two_hop_candidate_credit_limit': 40,
    'two_hop_candidate_limit': 160,
    'two_hop_candidate_batch': 8,
    'target_neighbor_credit_limit': 60,
    'target_neighbor_cast_limit': 120,
    'credit_limits': [28, 22, 16, 12, 10, 8],
    'cast_limits': [28, 22, 16, 12, 10, 8],
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
        return result

    target_credits = {
        (credit['id'], credit['type']): credit
        for credit in credits_b
    }

    direct_credit = _find_shared_credit(credits_a, target_credits)
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
        return result

    _emit_progress(
        progress_callback,
        {
            'stage': 'starting',
            'depth': 0,
            'explored_actors': 2,
            'frontier_size': 1,
            'frontier_sample': [actor_b['name']],
            'message': f'Mapeando conexoes mais fortes de {actor_b["name"]}.',
        },
    )

    two_hop_result = _find_two_hop_path(
        actor_a=actor_a,
        actor_b=actor_b,
        credits_a=credits_a,
        target_credits=target_credits,
        profile=profile,
        deadline=deadline,
        cancel_check=cancel_check,
    )
    if two_hop_result:
        _emit_progress(
            progress_callback,
            {
                'stage': 'found',
                'depth': 2,
                'explored_actors': 3,
                'frontier_size': 3,
                'frontier_sample': [step['actor']['name'] for step in two_hop_result],
                'message': 'Conexao em 2 graus encontrada.',
                'history_entry': {
                    'depth': 2,
                    'label': 'Conexao em 2 graus',
                    'sample_names': [step['actor']['name'] for step in two_hop_result],
                    'discovered_count': 3,
                },
            },
        )
        return two_hop_result

    target_neighbor_limit = profile['target_neighbor_credit_limit']
    target_neighbor_credits = _credit_window(credits_b, target_neighbor_limit)
    target_neighbor_map = _build_target_neighbor_map(
        actor_b_id=actor_b_id,
        target_credits=target_neighbor_credits,
        cast_limit=profile['target_neighbor_cast_limit'],
        deadline=deadline,
        cancel_check=cancel_check,
    )

    visited = {
        actor_a_id: {
            'parent': None,
            'credit': None,
            'depth': 0,
            'actor': actor_a,
        }
    }
    frontier = [actor_a_id]
    visited_credits = set()

    _emit_progress(
        progress_callback,
        {
            'stage': 'starting',
            'depth': 0,
            'explored_actors': 1,
            'frontier_size': 1,
            'frontier_sample': [actor_a['name']],
            'message': f'Partindo de {actor_a["name"]} em direcao a {actor_b["name"]}.',
        },
    )

    while frontier:
        _check_runtime_constraints(deadline, cancel_check)
        current_depth = visited[frontier[0]]['depth']
        if _frontier_exceeded(frontier, profile):
            raise SearchBudgetExceeded()

        credit_limit = _limit_for_depth(profile['credit_limits'], current_depth)
        cast_limit = _limit_for_depth(profile['cast_limits'], current_depth)
        credits_by_actor = {}

        _emit_progress(
            progress_callback,
            {
                'stage': 'exploring',
                'depth': current_depth,
                'explored_actors': len(visited),
                'frontier_size': len(frontier),
                'frontier_sample': _sample_frontier_names(frontier, visited),
                'message': f'Explorando a camada {current_depth + 1} de ate {max_degrees} graus.',
            },
        )

        for frontier_chunk in _iter_chunks(frontier, FRONTIER_SCAN_BATCH):
            chunk_credits = _load_frontier_credits(frontier_chunk, credit_limit)
            credits_by_actor.update(chunk_credits)

            for actor_id in frontier_chunk:
                node = visited[actor_id]
                credits = credits_by_actor[actor_id]
                shared_credit = _find_shared_credit(credits, target_credits)
                if shared_credit and node['depth'] + 1 <= max_degrees:
                    visited[actor_b_id] = {
                        'parent': actor_id,
                        'credit': shared_credit,
                        'depth': node['depth'] + 1,
                        'actor': actor_b,
                    }
                    result = _reconstruct(actor_b_id, visited)
                    _emit_progress(
                        progress_callback,
                        {
                            'stage': 'found',
                            'depth': node['depth'] + 1,
                            'explored_actors': len(visited),
                            'frontier_size': len(frontier),
                            'frontier_sample': _sample_frontier_names(frontier, visited),
                            'message': 'Conexao encontrada.',
                        },
                    )
                    return result

        if current_depth >= max_degrees - 1:
            break

        next_frontier = []
        queued = set()
        max_credit_batch = profile['max_credit_batch']
        credits_to_expand = []

        for actor_id in frontier:
            for credit in credits_by_actor[actor_id]:
                credit_key = (credit['id'], credit['type'])
                if credit_key in visited_credits:
                    continue
                visited_credits.add(credit_key)
                credits_to_expand.append((actor_id, credit))
                if max_credit_batch and len(credits_to_expand) >= max_credit_batch:
                    break
            if max_credit_batch and len(credits_to_expand) >= max_credit_batch:
                break

        for credit_chunk in _iter_chunks(credits_to_expand, CAST_EXPANSION_BATCH):
            credit_owners = [item[0] for item in credit_chunk]
            credit_batch = [item[1] for item in credit_chunk]

            for (actor_id, credit), cast in _load_casts(credit_owners, credit_batch, cast_limit):
                _check_runtime_constraints(deadline, cancel_check)
                for member in cast:
                    member_id = member['id']
                    if member_id == actor_id:
                        continue

                    if _connect_via_target_neighbor(
                        actor_id=actor_id,
                        actor_b=actor_b,
                        actor_b_id=actor_b_id,
                        credit=credit,
                        member=member,
                        target_neighbor_map=target_neighbor_map,
                        visited=visited,
                        max_degrees=max_degrees,
                    ):
                        result = _reconstruct(actor_b_id, visited)
                        _emit_progress(
                            progress_callback,
                            {
                                'stage': 'found',
                                'depth': len(result) - 1,
                                'explored_actors': len(visited),
                                'frontier_size': len(next_frontier),
                                'frontier_sample': _sample_frontier_names(next_frontier, visited),
                                'message': 'Conexao encontrada.',
                            },
                        )
                        return result

                    if member_id in visited:
                        continue

                    visited[member_id] = {
                        'parent': actor_id,
                        'credit': credit,
                        'depth': visited[actor_id]['depth'] + 1,
                        'actor': member,
                    }
                    if member_id not in queued:
                        queued.add(member_id)
                        next_frontier.append(member_id)

        _emit_progress(
            progress_callback,
            {
                'stage': 'layer_complete',
                'depth': current_depth + 1,
                'explored_actors': len(visited),
                'frontier_size': len(next_frontier),
                'frontier_sample': _sample_frontier_names(next_frontier, visited),
                'message': f'Camada {current_depth + 1} concluida.',
                'history_entry': {
                    'depth': current_depth + 1,
                    'label': f'Grau {current_depth + 1}',
                    'sample_names': _sample_frontier_names(next_frontier, visited, limit=5),
                    'discovered_count': len(next_frontier),
                },
            },
        )

        frontier = next_frontier

    _emit_progress(
        progress_callback,
        {
            'stage': 'not_found',
            'depth': max_degrees,
            'explored_actors': len(visited),
            'frontier_size': 0,
            'frontier_sample': [],
            'message': f'Nenhuma conexao encontrada em ate {max_degrees} graus.',
        },
    )
    return None


def _load_frontier_credits(frontier, credit_limit):
    if len(frontier) == 1:
        actor_id = frontier[0]
        return {actor_id: tmdb.get_actor_credits(actor_id, credit_limit)}

    results = {}
    with ThreadPoolExecutor(max_workers=min(ACTOR_FETCH_WORKERS, len(frontier))) as pool:
        future_map = {
            pool.submit(tmdb.get_actor_credits, actor_id, credit_limit): actor_id
            for actor_id in frontier
        }
        for future in as_completed(future_map):
            actor_id = future_map[future]
            results[actor_id] = future.result()
    return results


def _load_casts(credit_owners, credits, cast_limit):
    if not credits:
        return []

    if len(credits) == 1:
        credit = credits[0]
        return [
            (
                (credit_owners[0], credit),
                tmdb.get_movie_cast(credit['id'], credit['type'], cast_limit),
            )
        ]

    results = [None] * len(credits)
    with ThreadPoolExecutor(max_workers=min(CAST_FETCH_WORKERS, len(credits))) as pool:
        future_map = {
            pool.submit(tmdb.get_movie_cast, credit['id'], credit['type'], cast_limit): idx
            for idx, credit in enumerate(credits)
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            results[idx] = future.result()

    return list(zip(zip(credit_owners, credits), results))


def _build_target_neighbor_map(actor_b_id, target_credits, cast_limit, deadline, cancel_check):
    target_neighbors = {}
    for credit_chunk in _iter_chunks(target_credits, CAST_EXPANSION_BATCH):
        _check_runtime_constraints(deadline, cancel_check)
        credit_owners = [actor_b_id] * len(credit_chunk)
        for (_, credit), cast in _load_casts(credit_owners, credit_chunk, cast_limit):
            _check_runtime_constraints(deadline, cancel_check)
            for member in cast:
                member_id = member['id']
                if member_id == actor_b_id or member_id in target_neighbors:
                    continue
                target_neighbors[member_id] = credit
    return target_neighbors


def _find_two_hop_path(actor_a, actor_b, credits_a, target_credits, profile, deadline, cancel_check):
    source_credits = _credit_window(credits_a, profile['two_hop_source_credit_limit'])
    if not source_credits or not target_credits:
        return None

    source_groups = []
    for credit_chunk in _iter_chunks(source_credits, CAST_EXPANSION_BATCH):
        _check_runtime_constraints(deadline, cancel_check)
        credit_owners = [actor_a['id']] * len(credit_chunk)
        for (_, credit), cast in _load_casts(credit_owners, credit_chunk, profile['two_hop_cast_limit']):
            _check_runtime_constraints(deadline, cancel_check)
            ordered_cast = [member for member in cast if member['id'] != actor_a['id']]
            if ordered_cast:
                source_groups.append({
                    'credit': credit,
                    'cast': ordered_cast,
                })

    candidate_limit = profile['two_hop_candidate_limit']
    candidate_batch = profile['two_hop_candidate_batch']
    candidate_credit_limit = profile['two_hop_candidate_credit_limit']

    for candidate_chunk in _iter_chunks(
        list(_iter_round_robin_source_candidates(source_groups, candidate_limit)),
        candidate_batch,
    ):
        _check_runtime_constraints(deadline, cancel_check)
        candidate_ids = [candidate['actor']['id'] for candidate in candidate_chunk]
        candidate_credits = _load_frontier_credits(candidate_ids, candidate_credit_limit)

        for candidate in candidate_chunk:
            _check_runtime_constraints(deadline, cancel_check)
            shared_credit = _find_shared_credit(
                candidate_credits[candidate['actor']['id']],
                target_credits,
            )
            if not shared_credit:
                continue

            return [
                _build_step(actor_a, candidate['credit']),
                _build_step(candidate['actor'], shared_credit),
                _build_step(actor_b, None),
            ]

    return None


def _iter_round_robin_source_candidates(source_groups, limit=None):
    seen = set()
    yielded = 0
    depth = 0
    while source_groups:
        yielded_in_round = False
        for group in source_groups:
            cast = group['cast']
            if depth >= len(cast):
                continue

            member = cast[depth]
            member_id = member['id']
            if member_id in seen:
                continue

            seen.add(member_id)
            yielded += 1
            yielded_in_round = True
            yield {
                'actor': member,
                'credit': group['credit'],
            }

            if limit is not None and yielded >= limit:
                return

        if not yielded_in_round:
            return
        depth += 1


def _connect_via_target_neighbor(
    actor_id,
    actor_b,
    actor_b_id,
    credit,
    member,
    target_neighbor_map,
    visited,
    max_degrees,
):
    member_id = member['id']
    target_credit = target_neighbor_map.get(member_id)
    if not target_credit:
        return False

    if member_id not in visited:
        visited[member_id] = {
            'parent': actor_id,
            'credit': credit,
            'depth': visited[actor_id]['depth'] + 1,
            'actor': member,
        }

    member_depth = visited[member_id]['depth']
    if member_depth + 1 > max_degrees:
        return False

    visited[actor_b_id] = {
        'parent': member_id,
        'credit': target_credit,
        'depth': member_depth + 1,
        'actor': actor_b,
    }
    return True


def _find_shared_credit(credits, target_credits):
    for credit in credits:
        target = target_credits.get((credit['id'], credit['type']))
        if not target:
            continue

        return {
            'id': credit['id'],
            'type': credit['type'],
            'title': credit.get('title') or target.get('title'),
            'year': credit.get('year') or target.get('year'),
            'poster': credit.get('poster') or target.get('poster'),
        }
    return None


def _limit_for_depth(limits, depth):
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


def _iter_chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _emit_progress(progress_callback, payload):
    if progress_callback:
        progress_callback(payload)


def _reconstruct(target_actor_id, visited):
    nodes = []
    node = target_actor_id
    while node is not None:
        nodes.append(visited[node])
        node = visited[node]['parent']
    nodes.reverse()

    steps = []
    for idx, current in enumerate(nodes):
        next_credit = nodes[idx + 1]['credit'] if idx < len(nodes) - 1 else None
        steps.append(_build_step(current['actor'], next_credit))
    return steps


def _build_step(actor, credit):
    return {
        'actor': actor,
        'movie': _build_movie(credit) if credit else None,
    }


def _build_movie(credit):
    return {
        'id': credit.get('id'),
        'title': credit.get('title'),
        'year': str(credit.get('year') or ''),
        'poster': credit.get('poster'),
        'type': credit.get('type'),
    }


def _credit_window(credits, limit):
    if limit is None:
        return credits
    return credits[:limit]
