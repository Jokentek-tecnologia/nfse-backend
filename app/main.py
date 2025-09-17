
from fastapi import FastAPI, UploadFile, File, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from datetime import datetime
from io import BytesIO
import zipfile

from app.parser_nfse import parse_nfse_text_to_rows, df_for_rows

app = FastAPI(title="NFSe Plataforma — v3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://vertex-convert.netlify.app"],  # <— seu domínio Netlify, sem barra no final
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)

templates = Jinja2Templates(directory="app/templates")

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "version": "v3"})

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return raw.decode(enc, errors="ignore")
        except Exception:
            continue
    return raw.decode(errors="ignore")

def _xlsx_bytes_from_df(df) -> bytes:
    from pandas import ExcelWriter
    buf = BytesIO()
    with ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="NFSe_Completa")
    return buf.getvalue()

@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    include_raw_disc: bool = Query(True, description="Incluir a última coluna 'Discriminação' na íntegra"),
):
    raw = await file.read()
    text = _decode_bytes(raw)
    rows = parse_nfse_text_to_rows(text, include_disc_integral=include_raw_disc)
    df = df_for_rows(rows, include_disc_integral=include_raw_disc)
    xbytes = _xlsx_bytes_from_df(df)

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"NFSe_Completa_{ts}.xlsx"
    return StreamingResponse(BytesIO(xbytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/upload-multi")
async def upload_multi(
    files: list[UploadFile] = File(...),
    out: str = Query("combined", regex="^(combined|zip)$", description="'combined' = uma planilha única; 'zip' = uma planilha por arquivo"),
    include_raw_disc: bool = Query(True, description="Incluir a última coluna 'Discriminação' na íntegra"),
):
    if out == "combined":
        all_rows = []
        for f in files:
            text = _decode_bytes(await f.read())
            rows = parse_nfse_text_to_rows(text, include_disc_integral=include_raw_disc)
            for r in rows:
                r["_Arquivo"] = f.filename
            all_rows.extend(rows)
        import pandas as pd
        df = df_for_rows(all_rows, include_disc_integral=include_raw_disc)
        xbytes = _xlsx_bytes_from_df(df)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"NFSe_Completa_Lote_{ts}.xlsx"
        return StreamingResponse(BytesIO(xbytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        # out == "zip": cria um ZIP com um XLSX por arquivo
        zbuf = BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                text = _decode_bytes(await f.read())
                rows = parse_nfse_text_to_rows(text, include_disc_integral=include_raw_disc)
                df = df_for_rows(rows, include_disc_integral=include_raw_disc)
                xbytes = _xlsx_bytes_from_df(df)
                # nome do arquivo de saída baseado no nome de entrada
                base = (f.filename.rsplit(".", 1)[0] if "." in f.filename else f.filename)
                z.writestr(f"{base}.xlsx", xbytes)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"NFSe_Planilhas_{ts}.zip"
        return StreamingResponse(BytesIO(zbuf.getvalue()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

@app.post("/upload-zip")
async def upload_zip(
    file: UploadFile = File(...),
    out: str = Query("zip", regex="^(zip|combined)$", description="'zip' = várias planilhas dentro do zip; 'combined' = uma planilha única"),
    include_raw_disc: bool = Query(True, description="Incluir a última coluna 'Discriminação' na íntegra"),
):
    # Recebe um ZIP contendo TXT/XML; retorna outro ZIP ou uma planilha única.
    raw = await file.read()
    from io import BytesIO
    import zipfile, pandas as pd

    if out == "combined":
        all_rows = []
        with zipfile.ZipFile(BytesIO(raw)) as zin:
            for name in zin.namelist():
                if name.lower().endswith((".txt", ".xml")):
                    text = _decode_bytes(zin.read(name))
                    rows = parse_nfse_text_to_rows(text, include_disc_integral=include_raw_disc)
                    for r in rows:
                        r["_Arquivo"] = name
                    all_rows.extend(rows)
        df = df_for_rows(all_rows, include_disc_integral=include_raw_disc)
        xbytes = _xlsx_bytes_from_df(df)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"NFSe_Completa_Lote_{ts}.xlsx"
        return StreamingResponse(BytesIO(xbytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        outzip = BytesIO()
        with zipfile.ZipFile(outzip, "w", zipfile.ZIP_DEFLATED) as zout:
            with zipfile.ZipFile(BytesIO(raw)) as zin:
                for name in zin.namelist():
                    if name.lower().endswith((".txt", ".xml")):
                        text = _decode_bytes(zin.read(name))
                        rows = parse_nfse_text_to_rows(text, include_disc_integral=include_raw_disc)
                        df = df_for_rows(rows, include_disc_integral=include_raw_disc)
                        xbytes = _xlsx_bytes_from_df(df)
                        base = name.rsplit("/", 1)[-1]
                        base = (base.rsplit(".", 1)[0] if "." in base else base)
                        zout.writestr(f"{base}.xlsx", xbytes)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"NFSe_Planilhas_{ts}.zip"
        return StreamingResponse(BytesIO(outzip.getvalue()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
