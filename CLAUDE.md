# Contexto do projeto — Agente de Inflação (GPE)

> Este arquivo é lido automaticamente pelo Claude Code / Claude Desktop toda
> vez que ele abre este diretório. É a "memória permanente" do agente: em vez
> de você reexplicar o projeto a cada sessão, as regras ficam aqui. **Mantenha
> curto e factual.**

## O que este projeto faz
Pipeline autônomo que coleta indicadores de inflação do Banco Central — séries
realizadas do SGS e a mediana do Focus (API Olinda) — mais peso e variação por
grupo/subgrupo do IPCA no IBGE/SIDRA, armazena em SQLite, calcula variações,
recortes (serviços, núcleos, difusão) e contribuição ponderada por grupo, e
gera relatório em PDF. Módulos de responsabilidade única, encadeados pelo
`orquestrador.py`: `coleta.py` (SGS) → `tratamento.py` (limpeza) →
`modelagem.py` (cálculo) → `relatorio.py` (PDF), com `focus.py` (projeção) e
`ibge.py` (peso por grupo) alimentando a coleta. Tudo passa pelo SQLite
(`dados/macro.db`), que também é lido pelo Claude via MCP.
Recortes acompanhados: IPCA geral, serviços, quebra por durabilidade,
monitorados, núcleos (MS/EX0/DP/EX3/P55) e difusão. Projeção = mediana do
Focus. O relatório também traz "Movimentos do mês": os grupos do IPCA (IBGE)
que mais empurraram o índice para cima/baixo, por contribuição em pontos
percentuais (peso × variação) — não a variação bruta — com o subgrupo mais
relevante dentro de cada um.

Dois boletins com o mesmo molde, selecionados por `orquestrador.py --indice=`:
**IPCA** (`ipca`, padrão) e **IPCA-15** (`ipca15`, prévia da inflação). O
IPCA-15 **não tem** núcleos, quebra por durabilidade, monitorados nem
difusão — o BC só calcula essas aberturas para o índice cheio (ver
"Pendência conhecida" abaixo) — então o boletim do IPCA-15 omite essas
seções e destaca a ausência explicitamente no texto. Os dois boletins saem
em **edição única** por divulgação. O do IPCA roda ao meio-dia (não às 9h,
quando o índice sai) porque os núcleos costumam ser publicados pelo BC um
pouco depois do índice cheio. Até 2026-09 havia duas edições do IPCA (9h10 e
12h, `--edicao=1/2`); a 1ª foi abandonada em 2026-09-15 — não reintroduza.

## Regras de trabalho (obedeça sempre)
- **Fonte primária é o SGS do Banco Central.** Nunca invente números; se um
  dado não está no `dados/macro.db`, rode a coleta antes de responder.
- Código e comentários em **português (pt-BR)**.
- Séries e códigos SGS vivem em `config.py`. Para adicionar um indicador,
  edite só o dicionário `SERIES` — não espalhe códigos pelo código.
- Datas internas sempre em ISO (`AAAA-MM-DD`). O SGS entrega em pt-BR; a
  conversão é feita na coleta.
- Toda projeção deve vir rotulada como estimativa e com a metodologia. Nunca
  apresente a projeção ingênua como "previsão do agente".
- Ao mexer em qualquer robô, mantenha a **responsabilidade única** de cada
  arquivo (coleta não calcula; modelagem não formata PDF).

## Como calcular (definições canônicas)
- **Acumulado no ano / 12 meses:** composição de variações mensais
  `((1 + v/100).prod() - 1) * 100` — nunca soma simples.
- **Média dos núcleos:** média em 12m dos núcleos em `config.NUCLEOS` — conjunto
  oficial do BC: MS (4466), EX0 (11427), DP (16122), EX3 (27839) e P55 (28750).
- **Difusão:** nível (0–100%), não se acumula; é % de subitens em alta.
- **Projeção do IPCA geral:** mediana do Focus (`focus.py`), recurso Olinda
  `ExpectativasMercadoAnuais`, `baseCalculo=0`. Nunca substitua por chute.
- **Meta vigente:** ver `META_INFLACAO`/`META_TOLERANCIA` em `config.py`.
  Regime de meta contínua (3,0% ± 1,5 p.p.); confirme antes de afirmar.
- **Contribuição por grupo (IBGE/SIDRA):** peso/100 × variação do mês, nunca
  a variação bruta — grupos pesados (ex.: Habitação) podem "puxar" mais o
  índice que grupos leves com variação % maior. Fonte: `ibge.py`, tabela 7060
  do SIDRA, níveis grupo (9) e subgrupo (18) em `config.IBGE_GRUPOS`/
  `IBGE_SUBGRUPOS`. O SGS do BC **não** tem peso por grupo — só o IBGE.

## Pendência conhecida
- **Bens industriais (livres):** investigado em 2026-08-19 — **não existe**
  como série própria no SGS do Banco Central (busca exaustiva no catálogo do
  Portal de Dados Abertos, que espelha o localizador do SGS). O SGS só tem o
  agregado de "livres" (11428) e a quebra por durabilidade (10841-10844,
  já em `SERIES`). A tríade alimentação no domicílio/industriais/serviços é
  classificação do IBGE (SIDRA), não do BC. Não invente um código SGS para
  isso — se o recorte for necessário, colete via API SIDRA do IBGE. Ver
  comentário detalhado em `config.py` acima de `SERIES_A_CONFIRMAR`.

## IPCA-15 (investigação, 2026-08-19)
O IPCA-15 **não é indexado por nome** no catálogo do SGS/Portal de Dados
Abertos do BC — busca exaustiva ("IPCA-15", "IPCA15", "amplo 15" etc.)
retornou zero resultados. Mesmo assim o código numérico existe e responde
na API bruta do SGS:
- **7478** = IPCA-15 geral, variação mensal — validado cruzando 3 meses
  contra a variável 355 (tabela 7062 do SIDRA/IBGE, código c315=7169 =
  índice geral): os valores batem exatamente.
- O BC **não publica** núcleos, quebra por durabilidade, monitorados nem
  difusão para o IPCA-15 — confirmado por duas vias: nenhum desses cortes
  aparece no catálogo do SGS com "15" no nome, e a classificação c315 da
  tabela 7062 do SIDRA (única fonte de peso/contribuição por grupo do
  IPCA-15) só abre por grupo/subgrupo/item de despesa, igual à 7060 —
  sem categorias de núcleo/monitorados/difusão. São cálculos que o BC faz
  só para o índice cheio a partir de microdados do IBGE.
- **Focus/Olinda tracks "IPCA-15" como indicador próprio** — confirmado
  consultando `ExpectativasMercadoAnuais` com `Indicador eq 'IPCA-15'`
  (mesma estrutura usada para "IPCA").
- **Calendário do IBGE:** produto_id **9260** ("Índice Nacional de Preços
  ao Consumidor Amplo 15"), janela de divulgação **dias ~19-28** do mês —
  bem diferente da janela do IPCA cheio (produto_id 9256, dias ~5-13).
  Confirmado consultando `https://servicodados.ibge.gov.br/api/v3/calendario`
  e filtrando por `nome_produto` (o campo NÃO contém a sigla "IPCA" — é o
  nome por extenso).
Não invente nenhum código/série do IPCA-15 além do que está documentado
aqui e em `config.py` — se precisar de um recorte que o BC não publica,
a única fonte real é a tabela 7062 do SIDRA (grupo/subgrupo), não o SGS.

## Comandos úteis
- `python orquestrador.py` — pipeline completo (produção), IPCA.
- `python orquestrador.py --offline` — demonstração sem internet.
- `python orquestrador.py --indice=ipca15` — boletim do IPCA-15 (sem núcleo).
- `python modelagem.py` — recalcula e imprime os números-chave (IPCA).
- Cada robô roda isolado (não há suíte de testes; o bloco `if __name__` de
  cada arquivo é o smoke test): `python coleta.py --offline`,
  `python focus.py --offline`, `python ibge.py --offline`,
  `python tratamento.py`, `python relatorio.py`.
- `python verificar_divulgacao_ipca.py` — sai com código 0 se hoje é dia
  oficial de divulgação do IPCA (consulta o calendário do IBGE), senão 1.
  `--indice=ipca15` checa a janela/produto do IPCA-15.

## Banco de dados (para consultas via MCP)
Arquivo: `dados/macro.db`
- `observacoes(serie, data, valor)` — dados brutos, formato longo. IPCA-15
  usa nomes de série próprios (`ipca15_geral`), sem colidir com o IPCA cheio.
- `indicadores(nome, data, valor)` — indicadores já calculados, prefixados
  por índice (`ipca_no_mes`, `ipca15_no_mes` etc. — ver `modelagem.persistir`).
- `series_meta(serie, codigo_sgs, descricao, atualizado_em)` — catálogo.
- `focus_ipca(indicador, data_coleta, ano_referencia, mediana, media, minimo,
  maximo)` — expectativas do Focus por indicador ("IPCA"/"IPCA-15"), ano de
  referência e data de divulgação. PK inclui `indicador` — os dois índices
  coexistem sem se sobrescrever.
- `ipca_grupos(indice, mes, nivel, codigo_sidra, grupo_numero, nome,
  variacao_mensal, peso_mensal, variacao_12m)` — peso e variação por
  grupo/subgrupo, só o mês mais recente coletado por índice (fotografia, não
  série). `indice` ('ipca'/'ipca15') é necessário porque as tabelas SIDRA
  7060 e 7062 reaproveitam os MESMOS códigos de classificação — sem essa
  coluna uma coleta sobrescreveria a outra.

Bancos criados antes dessa distinção IPCA/IPCA-15 são migrados
automaticamente em `db.inicializar()` (recria `focus_ipca`/`ipca_grupos` com
as colunas novas, preservando os dados como 'IPCA'/'ipca').

Ao responder perguntas sobre os dados, **escreva SQL contra estas tabelas**
em vez de recalcular na memória.

## Automação (agendamento + envio por e-mail)
Desde 2026-08-19 o projeto vive em
[github.com/castrokleber-bit/agente-inflacao](https://github.com/castrokleber-bit/agente-inflacao)
(branch `main`, repositório público) — necessário porque o agendamento roda
na nuvem, sem acesso a este PC. Dois workflows do GitHub Actions geram e
commitam os relatórios; UMA rotina do Claude envia o e-mail, disparada pela
**publicação do relatório** (release no GitHub), não por horário.

**`.github/workflows/pipeline.yml`** (IPCA cheio) — todo dia entre os dias 5
e 13 do mês, uma vez, às **12h07 BRT (15:07 UTC)** (a data de divulgação não
segue um cron fixo; `verificar_divulgacao_ipca.py` confere o calendário
oficial do IBGE e só segue adiante nos dias reais). Edição única, ao
meio-dia para já pegar o núcleo do mês. Grava `relatorio_ipca_AAAA_MM.*`,
commita e, se houve commit, publica o release **`ipca-AAAA-MM-DD`**.

**`.github/workflows/pipeline_ipca15.yml`** (IPCA-15) — mesma lógica, janela
e produto do calendário DIFERENTES (dias 19-28, produto_id 9260 — ver seção
"IPCA-15" acima), às 12h10 BRT (15:10 UTC) → `python orquestrador.py
--indice=ipca15`. Arquivos com prefixo `ipca15` (`relatorio_ipca15_*`,
`grafico_ipca15_*`), sem colidir com os do IPCA cheio. Publica o release
**`ipca15-AAAA-MM-DD`**.

Em ambos, o release **não é recriado** se a tag do dia já existir (rodar o
workflow de novo no mesmo dia não reenvia e-mail).

### Por que o e-mail é disparado por release (incidente de 2026-09-11)
O GitHub **não garante o horário do cron**: em 2026-09-10/11/12 os disparos
chegaram com 3-4h de atraso (12:10 UTC → 16:22; 15:00 UTC → 18:11). As
rotinas de e-mail, agendadas para 15-20 min depois do horário nominal,
rodaram antes do commit, viram "nenhum relatório hoje" e pararam — o
relatório de 11/09 foi gerado mas nenhum e-mail saiu. **Não volte a agendar
o envio por horário.** Rotinas do Claude só aceitam gatilho do GitHub em
*pull request* ou *release* (não em push) — daí o release. O aviso "Node.js
20 is deprecated" que aparecia no Actions era só alerta, sem relação.

**Rotina de envio do Claude** (claude.ai/code/routines), lendo o `.html`
já commitado pelo GitHub Actions e enviando por `mcp__Gmail__send_message`
(`htmlBody`, com fallback para `.txt`) — 
**sem** rodar `orquestrador.py` nem chamar SGS/Olinda/SIDRA diretamente (o
sandbox dessas rotinas tem egress de rede bloqueado para essas APIs; elas
só leem o que o GitHub Actions já commitou):

Desde 2026-08-19, os destinatários fixos (todos em `to`)
são: fernando.almeida@cni.com.br, mamorim@senaicni.com.br,
virginia.colusso@cni.com.br e kleber.castro@cni.com.br. E-mails de falha
(quando o commit de hoje existe mas o envio dá erro) vão só para
kleber.castro@cni.com.br. Antes dessa mudança de lista, os testes usaram
kleberpcastro@gmail.com — histórico irrelevante agora.
- `trig_01GtLbFED522hoz12jfdUeXn` — **"envio por publicação"**, atende os
  DOIS índices. Gatilho principal: evento GitHub `release.published` neste
  repositório (exige o app Claude do GitHub instalado no repo). Descobre o
  índice pela mensagem do último commit em `saidas/` ("(IPCA)" ou
  "(IPCA-15)") e lê `relatorio_ipca_AAAA_MM.html` ou
  `relatorio_ipca15_AAAA_MM.html`. Gatilho reserva: agendamento às 21:00 UTC
  (18h BRT) nos dias 5-13 e 19-28, caso o evento do GitHub seja descartado
  (há limite por hora na prévia). Antes de enviar, procura no Gmail
  (enviados, hoje) um e-mail com o mesmo assunto — se já existe, não
  reenvia; é isso que impede duplicata entre o release e o reserva.
- `trig_01CKj4ztEkkZ9Tbp71xGqDQ1` (antiga "1ª edição") e
  `trig_01XZzPFeLPERg84KuCouoci7` (antiga "IPCA-15" por horário) —
  **desativadas** em 2026-09-15.
O **assunto do e-mail é derivado do `<h1>` literal do arquivo** (nunca
hardcoded na rotina) — é o `<h1>` de `relatorio.py` que carrega o rótulo do
índice.

### Por que o e-mail NÃO tem o gráfico embutido (decisão deliberada)
Três mecanismos foram testados na prática, nesta ordem, todos malsucedidos —
**não tente de novo sem reler isto primeiro**:
1. **`<img src="URL">`** (mesmo com URL pública, raw.githubusercontent.com) —
   a ferramenta de e-mail (`mcp__Gmail__send_message`) remove qualquer tag
   `<img>` com `src` externo antes de enviar. Confirmado lendo o e-mail
   enviado direto pela API do Gmail: a tag simplesmente não estava no
   `htmlBody` armazenado. Provável proteção contra pixel de rastreamento.
2. **Data URI base64 solto dentro do texto do `htmlBody`** (~59KB →
   ~80K caracteres) — não travou, mas confundiu a rotina o suficiente para
   ela abandonar o HTML formatado e mandar um e-mail em texto puro resumido
   em vez do relatório completo.
3. **Anexo inline via Content-ID** (campo estruturado `attachments` da
   ferramenta, com `inline: true` e `filename` casando com um `cid:` no
   HTML — o jeito "correto"/padrão MIME para imagem embutida em e-mail) —
   travou de verdade: a rotina fica presa indefinidamente (`worker_status`
   continua "running" sem nenhum evento novo por 10-20+ minutos) tentando
   gerar os ~80K caracteres de base64 como argumento de uma única chamada de
   ferramenta. Mesmo split em pedaços de 20KB lidos um a um (que funciona
   bem para *ler*), o agente trava tentando *reproduzir* esse volume de
   texto na chamada final — é um limite de geração de output do modelo, não
   de leitura, e por isso não tem workaround de chunking.
Conclusão: **qualquer mecanismo que exija ~80KB+ de texto num único
argumento de tool call trava ou corrompe o comportamento da rotina neste
ambiente**, independente do campo (`htmlBody`, `attachments[].content`) ou
de como o conteúdo foi construído do lado do sandbox. `gerar_html()` em
`relatorio.py` não inclui `<img>` nenhuma; o link "Baixar o PDF completo" no
rodapé é o caminho para ver o gráfico.
