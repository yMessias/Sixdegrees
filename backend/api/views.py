import requests
import json
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from . import tmdb
from .graph import SearchBudgetExceeded, find_path
from .jobs import cancel_job, get_job, start_connection_job


@api_view(['GET'])
def health(_request):
    return Response({'status': 'ok'})


@api_view(['GET'])
def search_actor(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return Response([])

    results = tmdb.search_actor(query)
    actors = [
        {
            'id':    a['id'],
            'name':  a['name'],
            'photo': tmdb.photo_url(a.get('profile_path')),
            'known_for': ', '.join(
                m.get('title') or m.get('name', '')
                for m in a.get('known_for', [])[:2]
            ),
        }
        for a in results
        if a.get('known_for_department') == 'Acting'
    ][:6]
    return Response(actors)


@api_view(['GET'])
def find_connection(request):
    actor_a = request.GET.get('actor_a')
    actor_b = request.GET.get('actor_b')

    if not actor_a or not actor_b:
        return Response(
            {'error': 'Informe actor_a e actor_b'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        path = find_path(int(actor_a), int(actor_b))
    except SearchBudgetExceeded:
        return Response(
            {'error': 'Essa conexão demorou demais para o modo rápido. Tente outro par de atores.'},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if path is None:
        return Response(
            {'error': 'Conexão não encontrada em até 6 graus.'},
            status=404
        )

    return Response({'path': path, 'degrees': len(path) - 1})


@api_view(['POST'])
def start_connection_search(request):
    actor_a = request.data.get('actor_a')
    actor_b = request.data.get('actor_b')

    if not actor_a or not actor_b:
        return Response(
            {'error': 'Informe actor_a e actor_b'},
            status=status.HTTP_400_BAD_REQUEST
        )

    job = start_connection_job(int(actor_a), int(actor_b))
    return Response(job, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
def connection_search_status(request, job_id):
    job = get_job(job_id)
    if not job:
        return Response({'error': 'Busca nao encontrada'}, status=status.HTTP_404_NOT_FOUND)
    return Response(job)


@api_view(['POST'])
def cancel_connection_search(request, job_id):
    job = cancel_job(job_id)
    if not job:
        return Response({'error': 'Busca nao encontrada'}, status=status.HTTP_404_NOT_FOUND)
    return Response(job)


@api_view(['POST'])
def ai_insight(request):
    path = request.data.get('path', [])
    if not path:
        return Response({'error': 'Path vazio'}, status=400)

    # Monta lista de conexões: "Ator A e Ator B em Filme X (ano)"
    connections = []
    for i in range(len(path) - 1):
        actor_left_id = path[i]['actor']['id']
        actor_right_id = path[i + 1]['actor']['id']
        actor_left  = path[i]['actor']['name']
        actor_right = path[i + 1]['actor']['name']
        movie       = path[i].get('movie')
        if movie:
            title = movie['title']
            year  = movie.get('year', '')
            label = f"{title} ({year})" if year else title
            connections.append({
                'key':         f'{actor_left_id}:{movie["id"]}:{actor_right_id}',
                'label':       f"{actor_left} e {actor_right} em {label}",
                'actor_left':  actor_left,
                'actor_right': actor_right,
                'movie':       label,
            })

    if not connections:
        return Response({'error': 'Sem conexões para analisar'}, status=400)

    connections_text = '\n'.join(
        f"- key={c['key']} | {c['label']}"
        for c in connections
    )

    prompt = f"""Você é um especialista em cinema e televisão. As seguintes conexões foram encontradas:

{connections_text}

Para CADA conexão acima, escreva uma curiosidade interessante que mencione AMBOS os atores e o que eles fizeram juntos nessa obra. Seja específico: personagens, cenas, bastidores ou impacto cultural.
Use exatamente a chave de conexão correspondente em "connection_key" para cada item.

Responda SOMENTE com JSON válido, sem markdown, neste formato exato:
{{
  "insights": [
    {{
      "connection_key": "idA:idObra:idB",
      "connection": "Ator A e Ator B em Obra X",
      "curiosity": "texto mencionando os dois atores e o que fizeram juntos"
    }}
  ],
  "fun_fact": "Um fato surpreendente sobre toda essa cadeia de conexões"
}}"""

    try:
        res = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.GROQ_API_KEY}',
            },
            json={
                'model': 'llama-3.3-70b-versatile',
                'max_tokens': 1200,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=30,
        )
        res.raise_for_status()
        content = res.json()['choices'][0]['message']['content']
        content = content.replace('```json', '').replace('```', '').strip()
        data = json.loads(content)
        return Response(data)

    except Exception as e:
        return Response({'error': str(e)}, status=500)
