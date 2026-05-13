# Six Degrees - Teoria dos 6 Graus entre Atores

Descubra como dois atores se conectam por filmes e séries em comum. O projeto combina uma API em Django com uma interface React para buscar atores, calcular a cadeia de conexão e gerar curiosidades sobre cada obra compartilhada.

## Funcionalidades

- Busca de atores pelo TMDB.
- Cálculo de conexão entre dois atores em até 6 graus.
- Busca profunda assíncrona com acompanhamento de progresso.
- Visualização da cadeia encontrada no frontend.
- Geração de curiosidades com Groq para contextualizar as conexões.

## Stack

- Backend: Django, Django REST Framework e Requests.
- Frontend: React, Vite e CSS modular por componente.
- Infra local: Docker Compose com serviços separados para backend e frontend.

## Pré-requisitos

- Python 3.11+.
- Node.js 20+.
- Conta e chave de API do TMDB.
- Chave da Groq para gerar insights.
- Docker e Docker Compose, caso prefira rodar tudo em containers.

## Variáveis de ambiente

Copie `backend/.env.example` para `backend/.env` e preencha:

```env
TMDB_API_KEY=sua-chave-tmdb
GROQ_API_KEY=sua-chave-groq
DJANGO_SECRET_KEY=uma-chave-local
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=
SEARCH_DEEP_TIME_BUDGET_SECONDS=180
```

No frontend, `frontend/.env.example` mostra a variável opcional:

```env
VITE_API_BASE=https://seu-backend.onrender.com/api
```

Em desenvolvimento local com Vite, a API usa `/api` e o proxy envia as chamadas para `http://localhost:8000`.

## Como rodar localmente

### Backend

```bash
cd backend
pip install -r requirements.txt
python manage.py runserver
```

A API fica disponível em `http://localhost:8000/api`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

A interface fica disponível em `http://localhost:5173`.

### Com Docker

```bash
docker-compose up --build
```

Acesse `http://localhost`.

## Endpoints principais

- `GET /api/health/` - verifica se a API está online.
- `GET /api/search/?q=nome` - pesquisa atores.
- `POST /api/connect/start/` - inicia a busca de conexão.
- `GET /api/connect/status/<job_id>/` - consulta o progresso da busca.
- `POST /api/connect/cancel/<job_id>/` - cancela uma busca em andamento.
- `POST /api/insight/` - gera curiosidades sobre o caminho encontrado.

## Deploy no Render

Use o painel web do Render:

- Backend: `Web Service` apontando para `backend/`.
- Frontend: `Static Site` apontando para `frontend/`.
- Configure as variáveis de ambiente necessárias no backend.
- Configure `VITE_API_BASE` no frontend com a URL pública do backend terminando em `/api`.

## APIs utilizadas

- TMDB - dados de atores, filmes e séries.
- Groq (`llama-3.3-70b-versatile`) - curiosidades sobre as conexões.
