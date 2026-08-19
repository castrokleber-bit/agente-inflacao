# Agente de Inflação — template macroeconômico

Pipeline autônomo de ponta a ponta: coleta dados do Banco Central, trata,
calcula e gera relatório em PDF. Pensado para ser **adaptado** às variáveis
da sua área — troque as séries em `config.py` e o resto acompanha.

```
coleta.py  →  tratamento.py  →  modelagem.py  →  relatorio.py
   (SGS)        (limpeza)         (cálculo)         (PDF)
        ↘___________ SQLite (dados/macro.db) ___________↗
                     ↑ lido pelo Claude via MCP
```

## Instalar e rodar

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python orquestrador.py            # produção (bate na API do BC)
python orquestrador.py --offline  # demonstração, sem internet
```

Saídas: `saidas/relatorio_ipca_AAAA_MM.pdf` e `dados/macro.db`.

## Adaptar a outras variáveis
Edite o dicionário `SERIES` em `config.py`. Cada linha é
`"nome_interno": (codigo_sgs, "descrição")`. Os códigos estão no
[SGS do Banco Central](https://www3.bcb.gov.br/sgspub/). Para indicadores
do IBGE, dá para plugar a API SIDRA de forma análoga em `coleta.py`.

## Colocar em produção (tirar do notebook)
Três níveis, do mais simples ao mais robusto:
1. **Agendador local** — `cron` (Linux/Mac) ou Agendador de Tarefas (Windows)
   chamando `python orquestrador.py`.
2. **GitHub Actions** — já incluso em `.github/workflows/pipeline.yml`: roda
   na nuvem todo dia entre os dias 5 e 13 de cada mês (janela em que o IBGE
   costuma divulgar o IPCA), mas só executa o pipeline de fato e commita o
   PDF em `saidas/` no dia real de divulgação — confirmado a cada execução
   contra o calendário oficial do IBGE (`verificar_divulgacao_ipca.py`), já
   que a data varia mês a mês e não segue um padrão fixo de cron.
3. **Contêiner** — empacote com Docker e rode em qualquer VM/serviço.

## Conectar o Claude ao banco (MCP)
Veja `mcp_config.example.json`. Depois de conectado, você pergunta em
português e o Claude escreve o SQL, consulta o SQLite e responde.

## Scripts que se autocorrigem
Todo erro é registrado em `execucao.log` **com contexto** (série, URL, status).
Quando algo quebra — a API muda um campo, uma série sai do ar — você tem duas
opções:
- cola o traceback do `execucao.log` no Claude e pede a correção; ou
- roda o Claude Code dentro desta pasta e diz *"o pipeline falhou, leia o
  execucao.log e conserte"* — ele lê o erro, edita o arquivo certo e testa.

O que torna isso possível não é mágica: são os erros descritivos + a
responsabilidade única de cada módulo (o agente sabe exatamente onde mexer).

## Aviso
A projeção de curtíssimo prazo em `modelagem.py` é um *placeholder* ingênuo.
Substitua pela expectativa do Focus ou por um modelo próprio antes de usar
para decisão. Os dados sintéticos do modo `--offline` não têm valor analítico.
