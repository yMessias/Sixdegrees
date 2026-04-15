from functools import lru_cache

import requests
from django.conf import settings

BASE = 'https://api.themoviedb.org/3'
IMG = 'https://image.tmdb.org/t/p/w300'
DEFAULT_LANGUAGE = 'pt-BR'
DEFAULT_CREDIT_LIMIT = 18
DEFAULT_CAST_LIMIT = 18


def _normalize_params(params):
    return tuple(sorted(params.items()))


@lru_cache(maxsize=2048)
def _get_cached(path, params_key):
    params = dict(params_key)
    params['api_key'] = settings.TMDB_API_KEY
    params['language'] = DEFAULT_LANGUAGE
    res = requests.get(f'{BASE}{path}', params=params, timeout=10)
    res.raise_for_status()
    return res.json()


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
    Retorna filmes e séries do ator usando combined_credits para reduzir
    requisições. O resultado fica ordenado por popularidade, ano e votos.
    """
    cast = _get(f'/person/{actor_id}/combined_credits').get('cast', [])
    combined = []
    seen = set()

    for credit in cast:
        credit_type = credit.get('media_type')
        if credit_type not in {'movie', 'tv'}:
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
def _get_full_movie_cast(credit_id, credit_type='movie'):
    if credit_type == 'tv':
        data = _get(f'/tv/{credit_id}/credits')
    else:
        data = _get(f'/movie/{credit_id}/credits')

    cast = []
    for member in data.get('cast', []):
        cast.append({
            'id': member.get('id'),
            'name': member.get('name'),
            'photo': photo_url(member.get('profile_path')),
        })
    return cast


def get_movie_cast(credit_id, credit_type='movie', limit=DEFAULT_CAST_LIMIT):
    return _get_full_movie_cast(credit_id, credit_type)[:limit]


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
