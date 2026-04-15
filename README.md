# Six Degrees - Teoria dos 6 Graus entre Atores

Descubra como dois atores se conectam por filmes e series em comum.

## Como rodar localmente

### Backend

1. Copie `backend/.env.example` para `backend/.env` e preencha as chaves.
2. Rode:

```bash
cd backend
pip install -r requirements.txt
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Com Docker

1. Copie `backend/.env.example` para `backend/.env` e preencha as chaves.
2. Suba:

```bash
docker-compose up --build
```

Acesse `http://localhost`.

## Deploy no Render

Use o painel web do Render:

- Backend: `Web Service` apontando para `backend/`
- Frontend: `Static Site` apontando para `frontend/`
- Configure as env vars necessarias no backend e `VITE_API_BASE` no frontend

## APIs utilizadas

- TMDB - dados de atores, filmes e series
- Groq (`llama-3.3-70b`) - curiosidades sobre as conexoes
