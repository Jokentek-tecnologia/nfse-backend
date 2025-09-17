
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
    matches = list(re.finditer(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", s))
    if not matches:
        return ""
    g = matches[-1].group(0)
    g = re.sub(r"\s*%$", "%", g.strip())
    return g

def parse_nfse_text_to_rows(txt: str, include_disc_integral: bool = True) -> list[dict]:
    """
    Converte o conteúdo de um arquivo TXT/XML de NFSe (Goiânia) em linhas (dicts)
    com TODAS as colunas do XML + Discriminacao expandida em colunas.
    Se include_disc_integral=False, a coluna final 'Discriminação' NÃO é incluída.
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

        tipo_servico = periodo = centro_custo = cno = ""
        base_calc_inss_text = retencao_inss_text = perc_inss_text = ""
        base_calc_iss_text = retencao_iss_text = perc_iss_text = ""
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

                disc_txt = _normalize_disc(discriminacao_raw)
                lines = [ln.strip() for ln in disc_txt.split("\n") if ln.strip()]
                whole = "\n".join(lines)

                tipo_servico = lines[0] if lines else ""
                pm = re.search(r"PER[IÍ]ODO[:\s]+(.+)$", whole, flags=re.IGNORECASE | re.MULTILINE)
                periodo = pm.group(1).strip() if pm else ""
                ccm = re.search(r"CENTRO\s+DE\s+CUSTO[:\s]+(.+)$", whole, flags=re.IGNORECASE | re.MULTILINE)
                centro_custo = ccm.group(1).strip() if ccm else ""
                cnom = re.search(r"\bCNO[:\s]*([^\s].+)$", whole, flags=re.IGNORECASE | re.MULTILINE)
                cno = cnom.group(1).strip() if cnom else ""

                m = re.search(r"BASE\s+DE\s*CALCULO\s+DE\s+INSS.*?(R\$\s*[0-9\.\s]*,\d{2})", whole, flags=re.IGNORECASE | re.MULTILINE)
                base_calc_inss_text = m.group(1).strip() if m else ""
                m = re.search(r"RETEN[ÇC][AÃ]O\s*DE?\s*INSS.*?(R\$\s*[0-9\.\s]*,\d{2})", whole, flags=re.IGNORECASE | re.MULTILINE)
                retencao_inss_text = m.group(1).strip() if m else ""
                for ln in lines:
                    if re.search(r"RETEN[ÇC][AÃ]O\s*DE?\s*INSS", ln, flags=re.IGNORECASE):
                        perc_inss_text = _extract_last_percent(ln)
                        break

                m = re.search(r"BASE\s+DE\s*CALCULO\s+DE\s+ISS.*?(R\$\s*[0-9\.\s]*,\d{2})", whole, flags=re.IGNORECASE | re.MULTILINE)
                base_calc_iss_text = m.group(1).strip() if m else ""
                for ln in lines:
                    if re.search(r"RETEN[ÇC][AÃ]O\s*DE?\s*ISS", ln, flags=re.IGNORECASE):
                        mv = re.search(r"(R\$\s*[0-9\.\s]*,\d{2})(?!.*R\$)", ln, flags=re.IGNORECASE)
                        if mv:
                            retencao_iss_text = mv.group(1).strip()
                        else:
                            m2 = re.search(r"(R\$\s*[0-9\.\s]*,\d{2})", ln, flags=re.IGNORECASE)
                            if m2:
                                retencao_iss_text = m2.group(1).strip()
                        perc_iss_text = _extract_last_percent(ln)
                        break

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

            "Tipo de serviço": tipo_servico,
            "Período": periodo,
            "Centro de custo": centro_custo,
            "CNO": cno,
            "Base de cálculo do INSS": base_calc_inss_text,
            "Retenção de INSS": retencao_inss_text,
            "Retenção de INSS (%)": perc_inss_text,
            "Base de cálculo de ISS": base_calc_iss_text,
            "Retenção de ISS": retencao_iss_text,
            "Retenção de ISS (%)": perc_iss_text,

            "CodigoMunicipio": cod_municipio,
            "ExigibilidadeISS": exig_iss,
            "MunicipioIncidencia": municipio_incidencia,

            "Prestador_CNPJ": prestador_cnpj,
            "Prestador_IM": prestador_im,
            "Tomador_CNPJ": tomador_cnpj,
            "Tomador_RazaoSocial": tomador_razao,
            "Tomador_Endereco": tomador_endereco,
            "Tomador_CEP": tomador_cep,
            "Tomador_CodigoMunicipio": tomador_cod_mun,

            "OptanteSimplesNacional": optante_simples,

            "ValoresNfse_BaseCalculo": base_calc_nfse,
            "ValoresNfse_Aliquota": aliquota_nfse,
            "ValoresNfse_ValorIss": valor_iss_nfse,
        }
        if include_disc_integral:
            row["Discriminação"] = discriminacao_raw

        rows.append(row)

    return rows

def df_for_rows(rows: list[dict], include_disc_integral: bool = True) -> "pd.DataFrame":
    df = pd.DataFrame(rows)
    if not include_disc_integral and "Discriminação" in df.columns:
        df = df.drop(columns=["Discriminação"])
    return df
