import re
from functools import lru_cache
from time import sleep
from unicodedata import normalize

import requests
from django.conf import settings

BASE = 'https://api.themoviedb.org/3'
IMG = 'https://image.tmdb.org/t/p/w300'
DEFAULT_LANGUAGE = 'pt-BR'
DEFAULT_CREDIT_LIMIT = 18
DEFAULT_CAST_LIMIT = 18
DEFAULT_TV_EPISODE_LIMIT = 12
REQUEST_TIMEOUT = (4, 12)
REQUEST_RETRIES = 2
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

EXCLUDED_TV_GENRES = {
    99,     # Documentary
    10763,  # News
    10764,  # Reality
    10767,  # Talk
}
EXCLUDED_MOVIE_GENRES = {
    99,  # Documentary
}
EXCLUDED_TITLE_TERMS = (
    ' academy awards ',
    ' after show ',
    ' award ceremony ',
    ' awards ',
    ' bafta ',
    ' critics choice ',
    ' emmy ',
    ' golden globe ',
    ' grammy ',
    ' mtv movie and tv awards ',
    ' oscar ',
    ' oscars ',
    ' premios ',
    ' premio ',
    ' premiacao ',
    ' premiacoes ',
    ' red carpet ',
    ' sag awards ',
    ' talk show ',
)
SELF_CHARACTER_PREFIXES = (
    'self',
    'himself',
    'herself',
    'themself',
    'themselves',
)
NON_FICTION_CHARACTER_TERMS = {
    'announcer',
    'contestant',
    'guest',
    'host',
    'interviewer',
    'judge',
    'panelist',
    'presenter',
}


def _normalize_params(params):
    return tuple(sorted(params.items()))


@lru_cache(maxsize=2048)
def _get_cached(path, params_key):
    params = dict(params_key)
    params['api_key'] = settings.TMDB_API_KEY
    params['language'] = DEFAULT_LANGUAGE
    last_error = None

    for attempt in range(REQUEST_RETRIES):
        try:
            res = requests.get(f'{BASE}{path}', params=params, timeout=REQUEST_TIMEOUT)
            if res.status_code in RETRY_STATUS_CODES and attempt < REQUEST_RETRIES - 1:
                sleep(_retry_delay(attempt, res))
                continue

            res.raise_for_status()
            return res.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_error = exc
            if attempt >= REQUEST_RETRIES - 1:
                raise
            sleep(_retry_delay(attempt))

    if last_error:
        raise last_error


def _get(path, **params):
    return _get_cached(path, _normalize_params(params))


@lru_cache(maxsize=256)
def search_actor(name):
    data = _get('/search/person', query=name)
    return data.get('results', [])


def get_actor(actor_id):
    return _get(f'/person/{actor_id}')


def get_actor_summary(actor_id):
    raw = get_actor(actor_id)
    return {
        'id': raw.get('id'),
        'name': raw.get('name'),
        'photo': photo_url(raw.get('profile_path')),
    }


@lru_cache(maxsize=1024)
def get_actor_all_credits(actor_id):
    """
    Return only eligible movies and scripted TV series.

    The filter removes "Self" appearances, talk/reality/news/documentary
    credits and common award-show titles, because those credits create false
    connections for this app.
    """
    cast = _get(f'/person/{actor_id}/combined_credits').get('cast', [])
    combined = []
    seen = set()

    for credit in cast:
        credit_type = credit.get('media_type')
        if not _is_supported_credit(credit):
            continue

        key = (credit.get('id'), credit_type)
        if key in seen:
            continue
        seen.add(key)

        title = credit.get('title') or credit.get('name')
        if not title:
            continue

        release_date = credit.get('release_date') or credit.get('first_air_date') or ''
        year = int(release_date[:4] or 0) if release_date[:4].isdigit() else 0

        combined.append({
            'id': credit.get('id'),
            'type': credit_type,
            'title': title,
            'year': year,
            'popularity': credit.get('popularity', 0),
            'vote_count': credit.get('vote_count', 0),
            'poster': photo_url(credit.get('poster_path')),
            'credit_id': credit.get('credit_id'),
            'character': credit.get('character'),
            'episode_count': credit.get('episode_count'),
            'genre_ids': tuple(credit.get('genre_ids') or ()),
        })

    combined.sort(
        key=lambda item: (
            item['popularity'],
            item['vote_count'],
            item['year'],
        ),
        reverse=True,
    )
    return combined


def get_actor_credits(actor_id, limit=DEFAULT_CREDIT_LIMIT):
    return get_actor_all_credits(actor_id)[:limit]


@lru_cache(maxsize=2048)
def _get_full_movie_cast(credit_id):
    data = _get(f'/movie/{credit_id}/credits')
    return _normalize_cast_list(data.get('cast', []))


def get_movie_cast(credit_id, credit_type='movie', limit=DEFAULT_CAST_LIMIT):
    if credit_type == 'tv':
        return _get_full_tv_series_cast(credit_id)[:limit]
    return _get_full_movie_cast(credit_id)[:limit]


def get_credit_cast(actor_id, credit, cast_limit=DEFAULT_CAST_LIMIT, episode_limit=DEFAULT_TV_EPISODE_LIMIT):
    """
    Return (actor, work) pairs connected to actor_id.

    For movies, the work is the movie. For TV, the work is a confirmed episode
    where actor_id and the returned actor both appear.
    """
    if credit.get('type') == 'tv':
        return get_tv_episode_cast(actor_id, credit, cast_limit, episode_limit)

    movie_credit = _build_movie_edge(credit)
    cast = [
        member
        for member in get_movie_cast(credit['id'], 'movie', cast_limit)
        if member.get('id') != actor_id
    ]
    return [(member, movie_credit) for member in cast]


def get_tv_episode_cast(actor_id, credit, cast_limit=DEFAULT_CAST_LIMIT, episode_limit=DEFAULT_TV_EPISODE_LIMIT):
    if episode_limit is not None and episode_limit <= 0:
        return []

    episodes = get_tv_credit_episode_refs(
        credit.get('id'),
        credit.get('credit_id'),
        episode_limit,
    )
    if not episodes:
        return []

    results = []
    seen_members = set()
    for episode in episodes:
        try:
            episode_cast = _get_tv_episode_cast(
                credit['id'],
                episode['season_number'],
                episode['episode_number'],
            )
        except requests.RequestException:
            continue

        if not _cast_has_actor(episode_cast, actor_id):
            continue

        edge_credit = _build_tv_episode_edge(credit, episode)

        for member in episode_cast:
            member_id = member.get('id')
            if member_id == actor_id or member_id in seen_members:
                continue
            seen_members.add(member_id)
            results.append((member, edge_credit))
            if cast_limit and len(results) >= cast_limit:
                return results

    return results


def find_shared_tv_episode(actor_a_id, credit_a, actor_b_id, credit_b):
    if not credit_a.get('credit_id') or not credit_b.get('credit_id'):
        return None

    series_id = credit_a.get('id')
    if series_id != credit_b.get('id'):
        return None

    episodes_b = {
        episode['id']: episode
        for episode in get_tv_credit_episode_refs(series_id, credit_b.get('credit_id'), None)
    }
    for episode in get_tv_credit_episode_refs(series_id, credit_a.get('credit_id'), None):
        if episode['id'] not in episodes_b:
            continue
        if not _episode_has_actors(
            series_id,
            episode['season_number'],
            episode['episode_number'],
            actor_a_id,
            actor_b_id,
        ):
            continue
        return _build_tv_episode_edge(_merge_series_credit(credit_a, credit_b), episode)
    return None


@lru_cache(maxsize=4096)
def get_tv_credit_episode_refs(series_id, credit_id, episode_limit=DEFAULT_TV_EPISODE_LIMIT):
    if episode_limit is not None and episode_limit <= 0:
        return tuple()

    if not series_id or not credit_id:
        return tuple()

    detail = _get(f'/credit/{credit_id}')
    media = detail.get('media') or {}
    episodes = {}

    for episode in media.get('episodes') or []:
        ref = _episode_ref(episode)
        if ref:
            episodes[ref['id']] = ref

    # Do not expand season summaries into individual episodes. TMDb can list a
    # regular actor as credited for a whole season even when they were absent
    # from specific episodes, which creates false "same episode" connections.
    # Only explicit episode refs are precise enough for this app.

    ordered = sorted(
        episodes.values(),
        key=lambda item: (
            item.get('season_number') or 0,
            item.get('episode_number') or 0,
            item.get('id') or 0,
        ),
    )
    if episode_limit is not None:
        ordered = ordered[:episode_limit]
    return tuple(ordered)


@lru_cache(maxsize=4096)
def _get_tv_episode_cast(series_id, season_number, episode_number):
    data = _get(f'/tv/{series_id}/season/{season_number}/episode/{episode_number}/credits')
    return _normalize_cast_list(
        list(data.get('cast') or []) + list(data.get('guest_stars') or [])
    )


def _episode_has_actors(series_id, season_number, episode_number, *actor_ids):
    episode_cast = _get_tv_episode_cast(series_id, season_number, episode_number)
    return all(_cast_has_actor(episode_cast, actor_id) for actor_id in actor_ids)


def _cast_has_actor(cast, actor_id):
    return any(member.get('id') == actor_id for member in cast)


@lru_cache(maxsize=1024)
def _get_full_tv_series_cast(series_id):
    data = _get(f'/tv/{series_id}/credits')
    return _normalize_cast_list(data.get('cast', []))


def get_movie(credit_id, credit_type='movie'):
    if credit_type == 'tv':
        raw = _get(f'/tv/{credit_id}')
        return {
            'id': raw.get('id'),
            'title': raw.get('name'),
            'release_date': raw.get('first_air_date', ''),
            'poster_path': raw.get('poster_path'),
        }
    return _get(f'/movie/{credit_id}')


def photo_url(path):
    if not path:
        return None
    return f'{IMG}{path}'


def _retry_delay(attempt, response=None):
    if response is not None:
        retry_after = response.headers.get('Retry-After')
        if retry_after and retry_after.isdigit():
            return min(int(retry_after), 2)
    return 0.4 * (attempt + 1)


def _is_supported_credit(credit):
    credit_type = credit.get('media_type') or credit.get('type')
    if credit_type not in {'movie', 'tv'}:
        return False

    if credit.get('adult') or credit.get('softcore') or credit.get('video'):
        return False

    title = credit.get('title') or credit.get('name') or ''
    if not title or _has_excluded_title_term(title):
        return False

    genre_ids = set(credit.get('genre_ids') or ())
    if credit_type == 'tv':
        if not credit.get('credit_id'):
            return False
        if genre_ids & EXCLUDED_TV_GENRES:
            return False
    elif genre_ids & EXCLUDED_MOVIE_GENRES:
        return False

    return not _looks_like_self_credit(credit.get('character'))


def _normalize_cast_list(raw_cast):
    cast = []
    seen = set()
    for member in raw_cast:
        member_id = member.get('id')
        if not member_id or member_id in seen:
            continue
        if _looks_like_self_credit(member.get('character')):
            continue
        seen.add(member_id)
        cast.append({
            'id': member_id,
            'name': member.get('name'),
            'photo': photo_url(member.get('profile_path')),
            'character': member.get('character'),
        })
    return tuple(cast)


def _build_movie_edge(credit):
    return {
        'id': credit.get('id'),
        'type': 'movie',
        'title': credit.get('title'),
        'year': credit.get('year'),
        'poster': credit.get('poster'),
    }


def _build_tv_episode_edge(series_credit, episode):
    series_title = series_credit.get('title') or series_credit.get('name') or 'Serie'
    episode_title = episode.get('name') or ''
    season_number = episode.get('season_number')
    episode_number = episode.get('episode_number')
    episode_label = _format_episode_label(series_title, episode_title, season_number, episode_number)
    air_date = episode.get('air_date') or ''
    year = int(air_date[:4] or 0) if air_date[:4].isdigit() else series_credit.get('year')

    return {
        'id': episode.get('id'),
        'series_id': series_credit.get('id'),
        'type': 'tv',
        'title': episode_label,
        'series_title': series_title,
        'episode_title': episode_title,
        'season_number': season_number,
        'episode_number': episode_number,
        'year': year,
        'poster': series_credit.get('poster') or photo_url(episode.get('still_path')),
    }


def _format_episode_label(series_title, episode_title, season_number, episode_number):
    if season_number is not None and episode_number is not None:
        label = f'{series_title} - S{int(season_number):02d}E{int(episode_number):02d}'
    else:
        label = series_title

    if episode_title:
        return f'{label}: {episode_title}'
    return label


def _episode_ref(episode, season_number=None):
    episode_id = episode.get('id')
    if not episode_id:
        return None

    resolved_season = episode.get('season_number')
    if resolved_season is None:
        resolved_season = season_number

    episode_number = episode.get('episode_number')
    if resolved_season is None or episode_number is None:
        return None

    return {
        'id': episode_id,
        'season_number': int(resolved_season),
        'episode_number': int(episode_number),
        'name': episode.get('name'),
        'air_date': episode.get('air_date') or '',
        'still_path': episode.get('still_path'),
    }


def _merge_series_credit(primary, fallback):
    merged = dict(fallback or {})
    merged.update({k: v for k, v in (primary or {}).items() if v is not None})
    return merged


def _has_excluded_title_term(title):
    normalized = f' {_normalize_text(title)} '
    return any(term in normalized for term in EXCLUDED_TITLE_TERMS)


def _looks_like_self_credit(character):
    if not character:
        return False

    normalized = _normalize_text(character)
    if not normalized:
        return False

    if normalized.startswith(SELF_CHARACTER_PREFIXES):
        return True

    parts = [
        part.strip()
        for part in re.split(r'[/,;|()\-]+', normalized)
        if part.strip()
    ]
    return any(part in NON_FICTION_CHARACTER_TERMS for part in parts)


def _normalize_text(value):
    text = normalize('NFKD', str(value))
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = text.lower().replace('&', ' and ')
    return ' '.join(text.split())
