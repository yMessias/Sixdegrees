# Deploy no Render (backend + frontend)

Este projeto jÃ¡ tem Dockerfiles para `backend/` e `frontend/`. Para subir no Render, vocÃª normalmente vai criar **dois serviÃ§os**: um para a API (Django) e um para o site (Vite).

## 1) PrÃ©-requisitos

- Coloque o projeto em um repositÃ³rio Git (GitHub/GitLab/Bitbucket).
- Tenha as chaves:
  - `TMDB_API_KEY`
  - `GROQ_API_KEY`

> Importante: nÃ£o commite `.env`/chaves no repo. Use as env vars do Render.

## 2) Backend (Django) como Web Service (Docker)

No Render:

- New â†’ **Web Service**
- Runtime: **Docker**
- Root directory: `backend`

Env vars (Settings â†’ Environment):

- `TMDB_API_KEY`
- `GROQ_API_KEY`
- `DJANGO_SECRET_KEY` (uma chave longa e aleatÃ³ria)
- `DEBUG=False`
- (Opcional) `CORS_ALLOWED_ORIGINS=https://seu-frontend.onrender.com`

SaÃºde:

- Endpoint: `GET /api/health/`

Porta:

- O `backend/Dockerfile` jÃ¡ faz bind em `0.0.0.0:$PORT` (com fallback para `8000`).

## 3) Frontend (Vite) como Static Site

No Render:

- New â†’ **Static Site**
- Root directory: `frontend`
- Build command: `npm ci && npm run build`
- Publish directory: `dist`

Env vars (para build do Vite):

- `VITE_API_BASE=https://SEU-BACKEND.onrender.com/api`

## 4) Alternativa: frontend como Web Service (Docker + nginx)

Se vocÃª quiser manter `BASE=/api` e fazer proxy via nginx, dÃ¡ para publicar o `frontend/` como Web Service (Docker). AÃ­ vocÃª precisa ajustar o `frontend/nginx.conf` para fazer `proxy_pass` para a URL do backend no Render (ou gerar o arquivo a partir de template com env var).

## 5) Blueprint (opcional)

Existe um `render.yaml` na raiz para criar os dois serviÃ§os via Blueprint. VocÃª ainda vai preencher os valores com `sync: false` no fluxo inicial do Render.
