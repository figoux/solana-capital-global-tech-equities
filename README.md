# Solana Global Tech — dashboard privado

Dashboard interno de earnings, temas macro e pair trading em tech global.
Stack: FastAPI + SQLite + Alpine.js/Tailwind + yfinance/Finnhub.

## Deploy: acesso pro time da Solana

### Arquitetura
- **Servidor (Render.com)**: serve dashboard em `https://solana-tech.onrender.com` com HTTP Basic auth
- **ETL (laptop Filipe)**: roda seeds + yfinance + Finnhub localmente, gera `backend/db/dashboard.db`
- **Deploy pipeline**: `python -m backend.etl.*` → `git add backend/db/dashboard.db` → `git commit` → `git push` → Render auto-deploya em ~2 min

### Credenciais
- **Usuário**: `solana`
- **Senha**: `REDACTED_PASSWORD` ← **salva num 1Password do time, NÃO commita no git**

---

## Setup inicial (uma vez só)

### 1. Criar repo privado no GitHub
```
https://github.com/new
  → Nome: solana-global-tech
  → Visibility: Private
  → NÃO inicializar com README (já tenho)
```
Depois de criar, copia o URL SSH ou HTTPS (ex: `git@github.com:filipe_gouveia/solana-global-tech.git`).

### 2. Push inicial (no laptop, PowerShell)
```powershell
cd "C:\Users\filip\OneDrive\Documentos\Claude\Projects\Solana Global Tech"
git init
git add .gitignore README.md render.yaml requirements.txt universe.csv
git add backend/ frontend/ scripts/
git add BUSINESS_EXPOSURES.md PLANO.md
git commit -m "Initial commit: Solana Global Tech dashboard"
git branch -M main
git remote add origin git@github.com:<SEU_USER>/solana-global-tech.git
git push -u origin main
```

### 3. Conectar no Render
1. Entre em https://dashboard.render.com
2. **New +** → **Blueprint**
3. Conecte sua conta do GitHub e selecione o repo `solana-global-tech`
4. Render detecta o `render.yaml` e propõe o service `solana-tech`
5. **Antes de clicar "Apply"**, na seção de env vars adicione:
   - `DASHBOARD_PASSWORD` = `REDACTED_PASSWORD`
6. Clique **Apply** → primeiro build leva ~5 min
7. URL final: `https://solana-tech.onrender.com`

### 4. Teste
Abrir a URL → deve pedir usuário/senha (`solana` / a senha acima) → depois abre o dashboard normal.

---

## Atualizações (dia a dia)

Toda vez que rodar ETL ou editar seeds, faz push do DB atualizado:

```powershell
cd "C:\Users\filip\OneDrive\Documentos\Claude\Projects\Solana Global Tech"

# 1. Rodar ETL local (exemplo pré-earnings)
python -m backend.etl.prices_yf
python -m backend.etl.fundamentals_yf
python -m backend.etl.events_finnhub
python -m backend.etl.pairs_compute

# 2. Commit DB + push
git add backend/db/dashboard.db
git commit -m "Daily ETL refresh"
git push

# Render auto-deploya em ~2 min. Time vê os dados novos.
```

Se editou código (não só dados):
```powershell
git add backend/ frontend/
git commit -m "descreva a mudança"
git push
```

---

## Free tier Render — coisas a saber

- **Spin-down**: após 15 min sem tráfego, serviço dorme. Primeiro request acorda (~30s de latência).
- **Quota**: 750h/mês (uma instância rodando 24/7 cabe).
- **RAM**: 512 MB — suficiente pro dashboard (SQLite + FastAPI).
- **Disk**: read-only no free tier — por isso DB fica no git.

Se o time reclamar da latência do spin-down, upgrade pra **Starter ($7/mês)** = sempre quente.

---

## Desenvolvimento local

```powershell
cd "C:\Users\filip\OneDrive\Documentos\Claude\Projects\Solana Global Tech"
python -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000
```

Local **não pede senha** porque `DASHBOARD_PASSWORD` não está setada no `.env` local. Se quiser testar auth localmente, seta antes:
```powershell
$env:DASHBOARD_PASSWORD="REDACTED_PASSWORD"
python -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000
```

---

## Rotatividade de senha

Se precisar trocar:
1. Gerar nova: `python -c "import secrets; print(secrets.token_urlsafe(18))"`
2. No Render dashboard: service → Environment → editar `DASHBOARD_PASSWORD`
3. Render faz redeploy automático em ~1 min
4. Comunica ao time (email/Slack)

Nenhum código precisa mudar.
