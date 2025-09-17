import re
import xml.etree.ElementTree as ET
import pandas as pd

NS = {"n": "http://nfse.goiania.go.gov.br/xsd/nfse_gyn_v02.xsd"}

def _gettext(elem, path):
    found = elem.find(path, NS)
    return (found.text.strip() if (found is not None and found.text is not None) else "")

def _join_address(addr_elem):
    if addr_elem is None:
        return ""
    parts = [
        _gettext(addr_elem, "n:Endereco"),
        _gettext(addr_elem, "n:Numero"),
        _gettext(addr_elem, "n:Complemento"),
        _gettext(addr_elem, "n:Bairro"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts)

def _normalize_disc(raw: str) -> str:
    if not raw:
        return ""
    txt = raw.replace("\\s\\n", "\n").replace("\\n", "\n")
    txt = re.sub(r"[ \t]+\n", "\n", txt)
    txt = re.sub(r"\n[ \t]+", "\n", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    return txt.strip()

def _extract_last_percent(s: str) -> str:
    m = list(re.finditer(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", s))
    if not m:
        return ""
    g = m[-1].group(0)
    return re.sub(r"\s*%$", "%", g.strip())

def _extract_iss_from_disc(raw_disc: str):
    """
    A partir do texto de Discriminação (inteiro), extrai APENAS três campos:
    - Base de Cálculo do ISS/ISSQN  (texto, ex.: 'R$49.262,77')
    - ISS/ISSQN Retido              (texto, ex.: 'R$2.463,15')
    - Porcentagem do ISS/ISSQN      (texto, ex.: '5%')
    Mantém valores exatamente como no texto (com R$ e vírgulas).
    """
    if not raw_disc:
        return ("", "", "")

    disc_txt = _normalize_disc(raw_disc)
    lines = [ln.strip() for ln in disc_txt.split("\n") if ln.strip()]
    whole = "\n".join(lines)

    # BASE DE CÁLCULO (ISS/ISSQN) — aceita variações: DE/DO/DA, acentos e ISSQN/ISS QN
    base_iss = ""
    m = re.search(
        r"BASE\s+DE\s*C[ÁA]LCULO\s+(?:DE|DO|DA)\s+(?:ISS(?:\s*QN)?|ISSQN)\b.*?(R\$\s*[0-9\.\s]*,\d{2})",
        whole, flags=re.IGNORECASE | re.MULTILINE
    )
    if m:
        base_iss = m.group(1).strip()

    # RETENÇÃO (linha que fala de retenção de ISS/ISSQN)
    ret_line = None
    # 1) padrão clássico "RETENÇÃO DE ISS/ISSQN"
    for ln in lines:
        if re.search(r"RETEN[ÇC][AÃ]O\s+DE?\s+(?:ISS(?:\s*QN)?|ISSQN)\b", ln, flags=re.IGNORECASE):
            ret_line = ln
            break
    # 2) alternativa "ISS/ISSQN RETIDO"
    if ret_line is None:
        for ln in lines:
            if re.search(r"(?:ISS(?:\s*QN)?|ISSQN).{0,40}RETID", ln, flags=re.IGNORECASE):
                ret_line = ln
                break

    ret_iss = ""
    pct_iss = ""
    if ret_line:
        # Pega o ÚLTIMO valor monetário da linha (ex.: pode ter base + valor)
        mv = re.findall(r"(R\$\s*[0-9\.\s]*,\d{2})", ret_line, flags=re.IGNORECASE)
        if mv:
            ret_iss = mv[-1].strip()
        pct_iss = _extract_last_percent(ret_line)

    return (base_iss, ret_iss, pct_iss)

def parse_nfse_text_to_rows(txt: str, include_disc_integral: bool = True) -> list[dict]:
    """
    Converte o conteúdo TXT/XML de NFSe (Goiânia) em linhas.
    >>> MUDANÇA: Discriminação volta como texto integral + SOMENTE 3 colunas ISS/ISSQN extraídas dela.
    """
    wrapped = f"<root>{txt}</root>"
    wrapped = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", wrapped)
    root = ET.fromstring(wrapped)

    rows = []
    for comp in root.findall(".//n:CompNfse", NS):
        inf = comp.find(".//n:InfNfse", NS)
        if inf is None:
            continue

        numero = _gettext(inf, "n:Numero")
        verif = _gettext(inf, "n:CodigoVerificacao")
        dt_emissao = _gettext(inf, "n:DataEmissao")

        base_calc_nfse = _gettext(inf, "n:ValoresNfse/n:BaseCalculo")
        aliquota_nfse = _gettext(inf, "n:ValoresNfse/n:Aliquota")
        valor_iss_nfse = _gettext(inf, "n:ValoresNfse/n:ValorIss")

        competencia = iss_retido_flag = cod_trib_mun = ""
        cod_municipio = exig_iss = municipio_incidencia = ""
        prestador_cnpj = prestador_im = ""
        tomador_cnpj = tomador_razao = tomador_endereco = tomador_cep = tomador_cod_mun = ""
        optante_simples = ""
        val_serv = val_ded = val_pis = val_cofins = val_inss = val_ir = val_csll = val_iss = aliq = ""

        discriminacao_raw = ""

        decl = inf.find(".//n:DeclaracaoPrestacaoServico/n:InfDeclaracaoPrestacaoServico", NS)
        if decl is not None:
            competencia = _gettext(decl, "n:Competencia")
            serv = decl.find(".//n:Servico", NS)
            if serv is not None:
                valores = serv.find("n:Valores", NS)
                if valores is not None:
                    val_serv = _gettext(valores, "n:ValorServicos")
                    val_ded = _gettext(valores, "n:ValorDeducoes")
                    val_pis = _gettext(valores, "n:ValorPis")
                    val_cofins = _gettext(valores, "n:ValorCofins")
                    val_inss = _gettext(valores, "n:ValorInss")
                    val_ir = _gettext(valores, "n:ValorIr")
                    val_csll = _gettext(valores, "n:ValorCsll")
                    val_iss = _gettext(valores, "n:ValorIss")
                    aliq = _gettext(valores, "n:Aliquota")
                iss_retido_flag = _gettext(serv, "n:IssRetido")
                cod_trib_mun = _gettext(serv, "n:CodigoTributacaoMunicipio")

                disc_elem = serv.find("n:Discriminacao", NS)
                discriminacao_raw = disc_elem.text if (disc_elem is not None and disc_elem.text is not None) else ""

                cod_municipio = _gettext(serv, "n:CodigoMunicipio")
                exig_iss = _gettext(serv, "n:ExigibilidadeISS")
                municipio_incidencia = _gettext(serv, "n:MunicipioIncidencia")

            prestador = decl.find(".//n:Prestador", NS)
            if prestador is not None:
                prestador_cnpj = _gettext(prestador, "n:CpfCnpj/n:Cnpj")
                prestador_im = _gettext(prestador, "n:InscricaoMunicipal")

            tomador = decl.find(".//n:Tomador", NS)
            if tomador is not None:
                tomador_cnpj = _gettext(tomador, "n:IdentificacaoTomador/n:CpfCnpj/n:Cnpj")
                tomador_razao = _gettext(tomador, "n:RazaoSocial")
                tomador_end_elem = tomador.find("n:Endereco", NS)
                tomador_endereco = _join_address(tomador_end_elem)
                tomador_cep = _gettext(tomador, "n:Endereco/n:Cep")
                tomador_cod_mun = _gettext(tomador, "n:Endereco/n:CodigoMunicipio")

            optante_simples = _gettext(decl, "n:OptanteSimplesNacional")

        # >>> NOVO: extrair APENAS os 3 campos ISS/ISSQN da Discriminação
        base_iss, ret_iss, pct_iss = _extract_iss_from_disc(discriminacao_raw)

        # Monta a linha (ordem preservada): Discriminação integral e, logo depois, as 3 colunas ISS/ISSQN.
        row = {
            "Numero": numero,
            "CodigoVerificacao": verif,
            "DataEmissao": dt_emissao,
            "Competencia": competencia,

            "ValorServicos": val_serv,
            "ValorDeducoes": val_ded,
            "ValorPis": val_pis,
            "ValorCofins": val_cofins,
            "ValorInss": val_inss,
            "ValorIr": val_ir,
            "ValorCsll": val_csll,
            "ValorIss": val_iss,
            "Aliquota": aliq,
            "IssRetido": iss_retido_flag,
            "CodigoTributacaoMunicipio": cod_trib_mun,

            # Aqui volta a Discriminação completa (original)
            "Discriminação": discriminacao_raw,

            # E imediatamente depois, SOMENTE estas 3 colunas do ISS/ISSQN
            "Base de cálculo do ISS/ISSQN": base_iss,
            "ISS/ISSQN Retido": ret_iss,
            "Percentual do ISS/ISSQN": pct_iss,

            # Demais campos do serviço
            "CodigoMunicipio": cod_municipio,
            "ExigibilidadeISS": exig_iss,
            "MunicipioIncidencia": municipio_incidencia,

            # Prestador / Tomador
            "Prestador_CNPJ": prestador_cnpj,
            "Prestador_IM": prestador_im,
            "Tomador_CNPJ": tomador_cnpj,
            "Tomador_RazaoSocial": tomador_razao,
            "Tomador_Endereco": tomador_endereco,
            "Tomador_CEP": tomador_cep,
            "Tomador_CodigoMunicipio": tomador_cod_mun,

            # Resumo NFSe
            "OptanteSimplesNacional": optante_simples,
            "ValoresNfse_BaseCalculo": base_calc_nfse,
            "ValoresNfse_Aliquota": aliquota_nfse,
            "ValoresNfse_ValorIss": valor_iss_nfse,
        }

        rows.append(row)

    return rows

def df_for_rows(rows: list[dict], include_disc_integral: bool = True) -> "pd.DataFrame":
    # Nesta versão a Discriminação sempre está presente; mantemos a assinatura por compatibilidade.
    return pd.DataFrame(rows)
