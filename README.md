# NFSe Plataforma — v3
Converte **TXT/XML → XLSX** com Discriminação expandida em colunas, suporta **lotes**, gera **planilha única** ou **ZIP com uma planilha por arquivo**, e opcionalmente inclui a coluna **“Discriminação”** integral ao final.

## Endpoints
- `POST /upload?include_raw_disc=true|false` — 1 arquivo → 1 XLSX
- `POST /upload-multi?out=combined|zip&include_raw_disc=true|false`
  - `combined` → 1 XLSX com todos os arquivos (coluna `_Arquivo`)
  - `zip` → ZIP com um XLSX por arquivo
- `POST /upload-zip?out=combined|zip&include_raw_disc=true|false`
  - Envie um ZIP contendo vários TXT/XML

## Rodando local
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate ; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
# Abra http://localhost:8080
```

## Deploy (Render)
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Configure CORS em `main.py` com o domínio do seu Netlify.

## Frontend (Netlify)
- A pasta `frontend/` contém uma página pronta que chama os endpoints relativos (útil se você servirá a UI pelo próprio backend). Se for hospedar no Netlify, troque as URLs `fetch("/upload"...` pelos seus endpoints absolutos (ex.: `https://sua-api.onrender.com/upload`).

## Observações
- Valores e percentuais extraídos da Discriminação são preservados exatamente como texto (R$, vírgula).
- A coluna final **“Discriminação”** pode ser ligada/desligada pela UI.
- O endpoint `/upload-multi` modo `zip` cria um arquivo ZIP contendo um XLSX por arquivo enviado.
