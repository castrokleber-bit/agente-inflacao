"""
relatorio.py — ROBÔ 4: APRESENTAÇÃO.

Responsabilidade única: transformar números em um PDF apresentável — o
produto que sai da sua mão para o diretor. Gera um gráfico (matplotlib) e
monta o documento (reportlab), com um parágrafo de leitura automática dos
números. É o "analista júnior" que redige o primeiro rascunho.

Só usa bibliotecas pip-instaláveis (matplotlib, reportlab) — nada preso a
um ambiente específico, então roda igual no seu notebook e no servidor.
"""

import logging
from datetime import datetime

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


def _data_br(iso):
    """Converte 'aaaa-mm-dd' -> 'dd/mm/aaaa'; devolve como veio se não parsear."""
    if not iso:
        return "data não informada"
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _grafico(resultado):
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    caminho = config.OUTPUT_DIR / "grafico_ipca.png"

    mensal = resultado["serie_mensal"].tail(24)
    doze = resultado["serie_12m"].tail(24)
    nucleos = resultado["serie_nucleos_12m"].tail(24)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 5.4), sharex=True)

    ax1.bar(mensal.index, mensal.values, width=20, color="#1f4e79")
    ax1.set_title("IPCA — variação mensal (%)", fontsize=11, loc="left")
    ax1.axhline(0, color="#888", lw=0.6)
    ax1.grid(axis="y", alpha=0.25)

    ax2.plot(doze.index, doze.values, color="#c00000", lw=1.8, label="IPCA cheio")
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
    ax2.set_title("IPCA e média dos núcleos — acumulado em 12 meses (%)",
                  fontsize=11, loc="left")
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
    sinal = "acima" if r["desvio_meta"] > 0 else "abaixo"
    status = "dentro" if r["dentro_banda"] else "fora"
    # Leitura difusão + núcleos: espraiamento vs. choque pontual.
    if r["difusao"] == r["difusao"] and r["nucleos_12m"] == r["nucleos_12m"]:
        leitura = (
            f"A média dos núcleos em 12 meses está em {r['nucleos_12m']:.2f}% e o índice "
            f"de difusão em {r['difusao']:.1f}% dos subitens, o que ajuda a distinguir "
            f"pressão disseminada de choque localizado. "
        )
    else:
        leitura = ""
    focus_txt = (
        f"Para {r['focus_ano']}, a mediana das expectativas do Focus divulgada em "
        f"{_data_br(r['focus_data'])} aponta IPCA de {r['focus_mediana']:.2f}%."
        if r["focus_mediana"] == r["focus_mediana"] else
        "A projeção do Focus não pôde ser carregada nesta execução."
    )
    peso_grupo_txt = (
        f"{r['peso_grupo_nome']}, o grupo de maior peso na cesta do IPCA, acumula "
        f"{r['peso_grupo_12m']:.2f}% em 12 meses. "
        if r.get("peso_grupo_nome") and r.get("peso_grupo_12m") == r.get("peso_grupo_12m")
        else ""
    )
    return (
        f"Em {MESES[ref.month]} de {ref.year}, o IPCA geral variou {r['no_mes']:.2f}% no mês, "
        f"acumulando {r['no_ano']:.2f}% no ano e {r['em_12m']:.2f}% em doze meses. "
        f"O índice em 12 meses está {abs(r['desvio_meta']):.2f} p.p. {sinal} do centro "
        f"da meta ({r['meta']:.1f}%), portanto {status} da banda de tolerância "
        f"(±{r['banda']:.1f} p.p.). Serviços acumulam {r['servicos_12m']:.2f}% em 12 meses. "
        f"{peso_grupo_txt}"
        f"{leitura}{focus_txt}"
    )


def _movimentos(r):
    """
    Leitura dos grupos do IPCA (IBGE/SIDRA) que mais contribuíram para o
    resultado do mês — contribuição em pontos percentuais (peso/100 *
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
            "As maiores contribuições positivas para o IPCA no mês vieram de "
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


def gerar_pdf(resultado):
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    grafico = _grafico(resultado)
    ref = resultado["referencia"]
    caminho = config.OUTPUT_DIR / f"relatorio_ipca_{ref:%Y_%m}.pdf"

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
        title=f"Monitor de Inflação — {ref:%b/%Y}",
    )

    kpis = [
        ["No mês", "No ano", "12 meses", "Desvio da meta"],
        [f"{resultado['no_mes']:.2f}%", f"{resultado['no_ano']:.2f}%",
         f"{resultado['em_12m']:.2f}%", f"{resultado['desvio_meta']:+.2f} p.p."],
    ]
    def _fmt(v, suf="%"):
        return f"{v:.2f}{suf}" if v == v else "s/d"

    kpis2 = [
        ["Serviços 12m", "Média núcleos 12m", "Difusão", f"Focus {resultado['focus_ano']}"],
        [_fmt(resultado["servicos_12m"]), _fmt(resultado["nucleos_12m"]),
         _fmt(resultado["difusao"]), _fmt(resultado["focus_mediana"])],
    ]

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

    tabela = _estilo(Table(kpis, colWidths=[4.1 * cm] * 4))
    tabela2 = _estilo(Table(kpis2, colWidths=[4.1 * cm] * 4), destaque="#2e5a2e", fundo="#eef4ee")

    elems = [
        Paragraph("Monitor de Inflação — IPCA", titulo),
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
        Spacer(1, 0.2 * cm),
        Paragraph(
            "Fontes: Banco Central do Brasil — SGS (IPCA e recortes) e Olinda/"
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
