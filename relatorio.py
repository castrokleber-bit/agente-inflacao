"""
relatorio.py — ROBÔ 4: APRESENTAÇÃO.

Responsabilidade única: transformar números em um PDF apresentável — o
produto que sai da sua mão para o diretor. Gera um gráfico (matplotlib) e
monta o documento (reportlab), com um parágrafo de leitura automática dos
números. É o "analista júnior" que redige o primeiro rascunho.

Serve dois boletins com o mesmo molde, distinguidos por `resultado["indice"]`
("ipca" ou "ipca15", setado em modelagem.calcular_ipca/calcular_ipca15):
o IPCA-15 não tem núcleos/serviços/duráveis/monitorados/difusão (o BC não
publica essas aberturas para a prévia — ver config.py), então essas seções
são omitidas e a ausência é destacada explicitamente no texto.

O parâmetro `edicao` (1 ou 2) só é relevante para o IPCA cheio: a 1ª edição
sai logo após a divulgação do IPCA, quando os núcleos do mês ainda podem
não ter sido publicados pelo BC; a 2ª edição roda mais tarde no mesmo dia,
com os núcleos atualizados. O número da edição aparece no título do
e-mail/HTML e no cabeçalho do PDF. O IPCA-15 não tem esse conceito (edição
única) e por isso ignora `edicao`.

Só usa bibliotecas pip-instaláveis (matplotlib, reportlab) — nada preso a
um ambiente específico, então roda igual no seu notebook e no servidor.
"""

import logging
from datetime import datetime

import pandas as pd

import matplotlib
matplotlib.use("Agg")  # backend sem tela, para rodar em servidor
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
)

import config

log = logging.getLogger("relatorio")

MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

OBSERVACAO_IPCA15 = (
    "Observação: o IPCA-15 não conta com as aberturas de núcleos de inflação, "
    "quebra por durabilidade, preços monitorados nem índice de difusão — o "
    "Banco Central calcula esses recortes apenas para o IPCA cheio, a partir "
    "de microdados do IBGE, e não os replica para a prévia."
)


def _data_br(iso):
    """Converte 'aaaa-mm-dd' -> 'dd/mm/aaaa'; devolve como veio se não parsear."""
    if not iso:
        return "data não informada"
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _fmt(v, suf="%"):
    return f"{v:.2f}{suf}" if v == v else "s/d"


def _base_nome(r):
    """Prefixo de arquivo e chave de índice: 'ipca' ou 'ipca15'."""
    return "ipca15" if r.get("indice") == "ipca15" else "ipca"


def _rotulo_indice(r):
    return "IPCA-15" if _base_nome(r) == "ipca15" else "IPCA"


def _rotulo_edicao(r, edicao):
    """" — Nª edição" para o IPCA cheio; vazio para o IPCA-15 (edição única)."""
    if _base_nome(r) == "ipca15" or not edicao:
        return ""
    return f" — {edicao}ª edição"


def _kpis(r):
    """(cabecalho1, valores1, cabecalho2, valores2) — a 2ª tabela some
    serviços/núcleos/difusão quando o índice não os tem (IPCA-15)."""
    cab1 = ["No mês", "No ano", "12 meses", "Desvio da meta"]
    val1 = [f"{r['no_mes']:.2f}%", f"{r['no_ano']:.2f}%",
            f"{r['em_12m']:.2f}%", f"{r['desvio_meta']:+.2f} p.p."]
    if _base_nome(r) == "ipca15":
        cab2 = [f"Focus {r['focus_ano']} (IPCA-15)"]
        val2 = [_fmt(r["focus_mediana"])]
    else:
        cab2 = ["Serviços 12m", "Média núcleos 12m", "Difusão", f"Focus {r['focus_ano']}"]
        val2 = [_fmt(r["servicos_12m"]), _fmt(r["nucleos_12m"]),
                _fmt(r["difusao"]), _fmt(r["focus_mediana"])]
    return cab1, val1, cab2, val2


def _grafico(resultado):
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ref = resultado["referencia"]
    base = _base_nome(resultado)
    rotulo = _rotulo_indice(resultado)
    caminho = config.OUTPUT_DIR / f"grafico_{base}_{ref:%Y_%m}.png"

    mensal = resultado["serie_mensal"].tail(24)
    doze = resultado["serie_12m"].tail(24)
    nucleos = resultado.get("serie_nucleos_12m", pd.Series(dtype=float)).tail(24)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 5.4), sharex=True)

    ax1.bar(mensal.index, mensal.values, width=20, color="#1f4e79")
    ax1.set_title(f"{rotulo} — variação mensal (%)", fontsize=11, loc="left")
    ax1.axhline(0, color="#888", lw=0.6)
    ax1.grid(axis="y", alpha=0.25)

    ax2.plot(doze.index, doze.values, color="#c00000", lw=1.8,
              label=f"{rotulo} cheio" if base == "ipca" else rotulo)
    if len(nucleos):
        ax2.plot(nucleos.index, nucleos.values, color="#1f4e79", lw=1.6,
                 ls="-", label="Média dos núcleos")
    ax2.axhline(config.META_INFLACAO, color="#2e7d32", ls="--", lw=1, label="Meta")
    ax2.fill_between(
        doze.index,
        config.META_INFLACAO - config.META_TOLERANCIA,
        config.META_INFLACAO + config.META_TOLERANCIA,
        color="#2e7d32", alpha=0.10, label="Banda de tolerância",
    )
    titulo2 = f"{rotulo}" + (" e média dos núcleos" if len(nucleos) else "") + " — acumulado em 12 meses (%)"
    ax2.set_title(titulo2, fontsize=11, loc="left")
    ax2.grid(axis="y", alpha=0.25)
    # Reserva espaço acima dos dados para a legenda não sobrepor as linhas
    # (o pico das séries fica perto do topo do eixo, na mesma região onde a
    # legenda "upper left" é desenhada).
    ymin, ymax = ax2.get_ylim()
    ax2.set_ylim(ymin, ymax + (ymax - ymin) * 0.22)
    ax2.legend(fontsize=8, loc="upper left", ncol=2, framealpha=1,
               facecolor="white", edgecolor="#cccccc")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b/%y"))

    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    return caminho


def _comentario(r):
    """Leitura automática dos números, em português, com ressalvas honestas."""
    ref = r["referencia"]
    rotulo = _rotulo_indice(r)
    e15 = _base_nome(r) == "ipca15"
    sinal = "acima" if r["desvio_meta"] > 0 else "abaixo"
    status = "dentro" if r["dentro_banda"] else "fora"

    servicos_txt = (
        f"Serviços acumulam {r['servicos_12m']:.2f}% em 12 meses. "
        if not e15 and r.get("servicos_12m") == r.get("servicos_12m") else ""
    )
    peso_grupo_txt = (
        f"{r['peso_grupo_nome']}, o grupo de maior peso na cesta do {rotulo}, acumula "
        f"{r['peso_grupo_12m']:.2f}% em 12 meses. "
        if r.get("peso_grupo_nome") and r.get("peso_grupo_12m") == r.get("peso_grupo_12m")
        else ""
    )
    if not e15 and r.get("difusao") == r.get("difusao") and r.get("nucleos_12m") == r.get("nucleos_12m"):
        leitura = (
            f"A média dos núcleos em 12 meses está em {r['nucleos_12m']:.2f}% e o índice "
            f"de difusão em {r['difusao']:.1f}% dos subitens, o que ajuda a distinguir "
            f"pressão disseminada de choque localizado. "
        )
    elif e15:
        leitura = (
            "O IPCA-15 não inclui núcleos de inflação, quebra por durabilidade, "
            "preços monitorados nem índice de difusão — o Banco Central calcula "
            "esses recortes apenas para o IPCA cheio, divulgado posteriormente. "
        )
    else:
        leitura = ""
    focus_txt = (
        f"Para {r['focus_ano']}, a mediana das expectativas do Focus para o {rotulo} "
        f"divulgada em {_data_br(r['focus_data'])} aponta {r['focus_mediana']:.2f}%."
        if r["focus_mediana"] == r["focus_mediana"] else
        "A projeção do Focus não pôde ser carregada nesta execução."
    )
    return (
        f"Em {MESES[ref.month]} de {ref.year}, o {rotulo} geral variou {r['no_mes']:.2f}% no mês, "
        f"acumulando {r['no_ano']:.2f}% no ano e {r['em_12m']:.2f}% em doze meses. "
        f"O índice em 12 meses está {abs(r['desvio_meta']):.2f} p.p. {sinal} do centro "
        f"da meta ({r['meta']:.1f}%), portanto {status} da banda de tolerância "
        f"(±{r['banda']:.1f} p.p.). {servicos_txt}"
        f"{peso_grupo_txt}"
        f"{leitura}{focus_txt}"
    )


def _movimentos(r):
    """
    Leitura dos grupos do IPCA/IPCA-15 (IBGE/SIDRA) que mais contribuíram
    para o resultado do mês — contribuição em pontos percentuais (peso/100 *
    variação), não a variação bruta, para que grupos pesados não sejam
    ofuscados por grupos leves com variação percentual maior. Para cada
    grupo destacado, aponta também o subgrupo de maior contribuição dentro
    dele.
    """
    altas = r.get("grupos_altas", [])
    quedas = r.get("grupos_quedas", [])
    if not altas and not quedas:
        return ("Não há dados do IBGE/SIDRA disponíveis nesta execução para "
                "apontar os principais movimentos do mês.")

    def _detalhe(g):
        texto = f"{g['nome']} ({g['contribuicao']:+.2f} p.p.)"
        sub = g.get("subgrupo_principal")
        if sub:
            texto += f", com destaque para {sub['nome']} ({sub['contribuicao']:+.2f} p.p.)"
        return texto

    partes = []
    if altas:
        partes.append(
            "As maiores contribuições positivas para o índice no mês vieram de "
            + "; ".join(_detalhe(g) for g in altas) + "."
        )
    else:
        partes.append("Nenhum grupo teve contribuição positiva relevante no mês.")
    if quedas:
        partes.append(
            "As maiores contribuições negativas vieram de "
            + "; ".join(_detalhe(g) for g in quedas) + "."
        )
    else:
        partes.append("Nenhum grupo registrou contribuição negativa no mês.")

    return " ".join(partes)


def gerar_texto(resultado, edicao=1):
    """
    Versão em texto plano do relatório — mesmo conteúdo do PDF (sem os
    gráficos), pensada para caber direto no corpo de um e-mail sem precisar
    de anexo binário. Grava em `saidas/relatorio_{ipca|ipca15}_AAAA_MM.txt`.
    """
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ref = resultado["referencia"]
    base = _base_nome(resultado)
    rotulo = _rotulo_indice(resultado)
    sufixo_edicao = _rotulo_edicao(resultado, edicao)
    caminho = config.OUTPUT_DIR / f"relatorio_{base}_{ref:%Y_%m}.txt"

    cab1, val1, cab2, val2 = _kpis(resultado)
    linhas_kpi2 = [f"{c}:  {v}" for c, v in zip(cab2, val2)]

    linhas = [
        f"MONITOR DE INFLAÇÃO — {rotulo}{sufixo_edicao}",
        f"{config.INSTITUICAO}",
        f"Referência: {MESES[ref.month]}/{ref.year}",
        "",
        f"No mês:            {resultado['no_mes']:.2f}%",
        f"No ano:            {resultado['no_ano']:.2f}%",
        f"Em 12 meses:       {resultado['em_12m']:.2f}%",
        f"Desvio da meta:    {resultado['desvio_meta']:+.2f} p.p.",
        *linhas_kpi2,
        "",
        _comentario(resultado),
        "",
        "MOVIMENTOS DO MÊS",
        _movimentos(resultado),
        "",
    ]
    if base == "ipca15":
        linhas.append(OBSERVACAO_IPCA15)
        linhas.append("")
    linhas.append(
        f"Fontes: Banco Central do Brasil — SGS ({rotulo} e recortes), IBGE/SIDRA "
        "(peso por grupo) e Olinda/Expectativas de Mercado (mediana do "
        "Focus). Documento gerado automaticamente pelo Agente de Inflação."
    )
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    log.info("Texto do relatório gerado: %s", caminho)
    return caminho


def gerar_html(resultado, edicao=1):
    """
    Versão em HTML do relatório, para o corpo de e-mails — visual parecido
    com o PDF (tabelas de KPI coloridas, texto justificado).

    SEM o gráfico embutido — decisão deliberada após três tentativas reais
    de fazer a imagem aparecer no corpo do e-mail, todas malsucedidas:
    `<img src="URL">` (a ferramenta de e-mail remove qualquer `<img>` com
    `src` externo antes de enviar, mesmo URL pública — proteção contra pixel
    de rastreamento), base64 solto no texto do htmlBody (confundia a rotina)
    e anexo inline via Content-ID (`attachments` com `inline: true` — trava
    a rotina tentando gerar os ~80KB de base64 como argumento da chamada).
    Ver CLAUDE.md, seção Automação, para o histórico completo. O link
    "Baixar o PDF completo" no rodapé é o caminho para ver o gráfico.

    Cor de fundo das células via `background-color` + atributo `bgcolor`
    (não `background` sozinho — o Gmail costuma descartar essa propriedade
    shorthand, o que deixava o texto branco do cabeçalho invisível sobre
    fundo branco).

    Grava em `saidas/relatorio_{ipca|ipca15}_AAAA_MM.html`.
    """
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ref = resultado["referencia"]
    base = _base_nome(resultado)
    rotulo = _rotulo_indice(resultado)
    sufixo_edicao = _rotulo_edicao(resultado, edicao)
    caminho = config.OUTPUT_DIR / f"relatorio_{base}_{ref:%Y_%m}.html"

    pdf_url = f"{config.GITHUB_REPO_URL}/blob/main/saidas/relatorio_{base}_{ref:%Y_%m}.pdf"

    azul, azul_claro = "#1f4e79", "#eef2f7"
    verde, verde_claro = "#2e5a2e", "#eef4ee"

    def _kpi_table(cabecalho, valores, destaque, fundo):
        celulas_cab = "".join(
            f'<td bgcolor="{destaque}" style="background-color:{destaque};color:#ffffff;'
            f'padding:8px 4px;text-align:center;font-size:11px;font-family:Arial,sans-serif;">{c}</td>'
            for c in cabecalho
        )
        celulas_val = "".join(
            f'<td bgcolor="{fundo}" style="background-color:{fundo};padding:10px 4px;'
            f'text-align:center;font-size:16px;font-weight:bold;font-family:Arial,sans-serif;'
            f'color:#222222;">{v}</td>'
            for v in valores
        )
        return (
            '<table role="presentation" style="width:100%;border-collapse:collapse;'
            f'margin:0 0 8px 0;"><tr>{celulas_cab}</tr><tr>{celulas_val}</tr></table>'
        )

    cab1, val1, cab2, val2 = _kpis(resultado)
    kpis1 = _kpi_table(cab1, val1, azul, azul_claro)
    kpis2 = _kpi_table(cab2, val2, verde, verde_claro)

    observacao_html = (
        f'\n  <p style="font-size:12px;color:#555555;line-height:1.5;margin:0 0 16px 0;'
        f'font-style:italic;">{OBSERVACAO_IPCA15}</p>'
        if base == "ipca15" else ""
    )

    html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:640px;margin:0 auto;color:#222222;">
  <h1 style="color:{azul};font-size:22px;margin:0 0 2px 0;">Monitor de Inflação — {rotulo}{sufixo_edicao}</h1>
  <p style="color:{azul};font-size:12px;margin:0 0 16px 0;">
    {config.INSTITUICAO} &middot; referência: {MESES[ref.month]}/{ref.year}
  </p>

  {kpis1}
  {kpis2}

  <p style="line-height:1.55;font-size:14px;margin:16px 0;text-align:justify;">{_comentario(resultado)}</p>

  <h2 style="color:{azul};font-size:15px;margin:16px 0 6px 0;">Movimentos do mês</h2>
  <p style="line-height:1.55;font-size:14px;margin:0 0 16px 0;text-align:justify;">{_movimentos(resultado)}</p>
{observacao_html}
  <p style="font-size:11px;color:#888888;line-height:1.5;margin-top:24px;">
    Fontes: Banco Central do Brasil — SGS ({rotulo} e recortes), IBGE/SIDRA (peso por grupo)
    e Olinda/Expectativas de Mercado (mediana do Focus). Documento gerado automaticamente
    pelo Agente de Inflação.<br/>
    <a href="{pdf_url}" style="color:{azul};">Baixar o PDF completo</a>
  </p>
</div>
"""
    caminho.write_text(html, encoding="utf-8")
    log.info("HTML do relatório gerado: %s", caminho)
    return caminho


def gerar_pdf(resultado, edicao=1):
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    grafico = _grafico(resultado)
    ref = resultado["referencia"]
    base = _base_nome(resultado)
    rotulo = _rotulo_indice(resultado)
    sufixo_edicao = _rotulo_edicao(resultado, edicao)
    caminho = config.OUTPUT_DIR / f"relatorio_{base}_{ref:%Y_%m}.pdf"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Corpo", parent=styles["Normal"],
                              alignment=TA_JUSTIFY, fontSize=10.5, leading=15))
    styles.add(ParagraphStyle("Rodape", parent=styles["Normal"],
                              fontSize=7.5, textColor=colors.grey))
    titulo = ParagraphStyle("Titulo", parent=styles["Title"], fontSize=17, spaceAfter=2)
    subt = ParagraphStyle("Subt", parent=styles["Normal"], fontSize=9,
                          textColor=colors.HexColor("#1f4e79"), spaceAfter=10)
    secao = ParagraphStyle("Secao", parent=styles["Heading2"], fontSize=12,
                           textColor=colors.HexColor("#1f4e79"), spaceAfter=4)

    doc = SimpleDocTemplate(
        str(caminho), pagesize=A4,
        topMargin=1.4 * cm, bottomMargin=1.2 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"Monitor de Inflação — {rotulo}{sufixo_edicao} — {ref:%b/%Y}",
    )

    cab1, val1, cab2, val2 = _kpis(resultado)
    kpis = [cab1, val1]
    kpis2 = [cab2, val2]

    def _estilo(t, destaque="#1f4e79", fundo="#eef2f7"):
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(destaque)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, 1), 14),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 1), (-1, 1), 7),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.white),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor(fundo)),
        ]))
        return t

    largura_total = 16.4  # cm — igual à soma das 4 colunas originais
    tabela = _estilo(Table(kpis, colWidths=[largura_total / len(cab1) * cm] * len(cab1)))
    tabela2 = _estilo(Table(kpis2, colWidths=[largura_total / len(cab2) * cm] * len(cab2)),
                       destaque="#2e5a2e", fundo="#eef4ee")

    elems = [
        Paragraph(f"Monitor de Inflação — {rotulo}{sufixo_edicao}", titulo),
        Paragraph(f"{config.INSTITUICAO}  ·  referência: {MESES[ref.month]}/{ref.year}  ·  "
                  f"gerado em {datetime.now():%d/%m/%Y %H:%M}", subt),
        tabela,
        Spacer(1, 0.2 * cm),
        tabela2,
        Spacer(1, 0.3 * cm),
        Paragraph(_comentario(resultado), styles["Corpo"]),
        Spacer(1, 0.3 * cm),
        Image(str(grafico), width=12.6 * cm, height=9.45 * cm),
        Spacer(1, 0.3 * cm),
        Paragraph("Movimentos do mês", secao),
        Paragraph(_movimentos(resultado), styles["Corpo"]),
    ]
    if base == "ipca15":
        elems += [
            Spacer(1, 0.2 * cm),
            Paragraph(OBSERVACAO_IPCA15, styles["Corpo"]),
        ]
    elems += [
        Spacer(1, 0.2 * cm),
        Paragraph(
            f"Fontes: Banco Central do Brasil — SGS ({rotulo} e recortes) e Olinda/"
            "Expectativas de Mercado (mediana do Focus). Documento gerado "
            "automaticamente pelo Agente de Inflação. A projeção corresponde à "
            "mediana do Focus para o ano de referência indicado.",
            styles["Rodape"]),
    ]
    doc.build(elems)
    log.info("PDF gerado: %s", caminho)
    return caminho


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import modelagem
    r = modelagem.calcular_ipca()
    print(gerar_pdf(r))
