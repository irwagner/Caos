# Dados do MNQ — estrutura e exportação do NinjaTrader 8

Esta pasta acolhe os dados históricos do **MNQ** (Micro E-mini Nasdaq-100 Futures) que alimentam o pipeline de Walk-Forward (Spec 2) e os testes de paridade (Specs 4+).

## Estrutura

```
dados/MNQ/
├── MNQ_03-26/                # Contrato com vencimento mar/2026
│   ├── minute/
│   │   ├── MNQ 03-26.Ask.txt    (export bruto do NT8 — auditoria)
│   │   ├── MNQ 03-26.Bid.txt
│   │   ├── MNQ 03-26.Last.txt
│   │   ├── ask.csv              (gerados por 'caos dados normalizar')
│   │   ├── bid.csv
│   │   └── last.csv
│   └── day/
│       ├── MNQ 03-26.Ask.txt
│       ├── MNQ 03-26.Bid.txt
│       ├── MNQ 03-26.Last.txt
│       ├── ask.csv
│       ├── bid.csv
│       └── last.csv
├── MNQ_06-25/  ... (mesma estrutura)
├── MNQ_06-26/  ...
├── MNQ_09-25/  ...
└── MNQ_12-25/  ...
```

Convenções:

- **Naming dos contratos:** `MNQ_<MM>-<YY>` (underscore depois de `MNQ`, hífen entre mês e ano de 2 dígitos). Vencimentos canônicos do MNQ no CME: março (03), junho (06), setembro (09), dezembro (12).
- **Granularidade:** apenas `minute/` e `day/` por enquanto. `tick/` será adicionada quando o usuário exportar os dados de tape (subdiretório próximo da estrutura existente, irmão de `minute/` e `day/`).
- **Séries:** `ask.csv` (ofertas de venda), `bid.csv` (ofertas de compra), `last.csv` (último preço negociado). O Spec 2 usa `last.csv` como fonte primária para Walk-Forward; `ask.csv`/`bid.csv` ficam disponíveis para futuros estudos de spread, slippage e order flow.

## Cobertura por contrato (estado atual em ~mai/2026)

| Contrato | Vencimento | Range disponível no NT8 | Dias úteis aprox. |
|---|---|---|---|
| MNQ_06-25 | 20/jun/2025 | 17/mar/2025 → 13/jun/2025 | 79 |
| MNQ_09-25 | 19/set/2025 | 16/jun/2025 → 12/set/2025 | 79 |
| MNQ_12-25 | 19/dez/2025 | 15/set/2025 → 14/dez/2025 | 80 |
| MNQ_03-26 | 20/mar/2026 | 14/dez/2025 → 20/mar/2026 | 82 |
| MNQ_06-26 | 19/jun/2026 (em curso) | 12/mar/2026 → 17/mai/2026 | 51 |

Total: ~371 dias úteis (~17 meses) de cobertura contínua, com pequena sobreposição entre contratos sucessivos durante o período de roll.

## Procedimento de exportação no NT8 (manual, 1 contrato + 1 série + 1 granularidade por vez)

O NT8 armazena dados em formato `.ncd` (NinjaTrader Compressed Data) — proprietário, binário, ilegível por Python. Para usar no pipeline CAOS é preciso exportar para arquivo texto via UI do NinjaTrader.

1. Abra o NinjaTrader 8.
2. Menu **Tools → Historical Data**.
3. Aba **Export**.
4. Configure:
   - **Instrument:** ex. `MNQ 03-26` (com espaço — formato nativo do NT8).
   - **Type:** `Minute` ou `Day` conforme a granularidade pretendida.
   - **Trade Type:** uma de `Ask`, `Bid`, `Last`. **Faça uma exportação por trade type** (3 arquivos por contrato/granularidade).
   - **From / To:** intervalo cobrindo todo o histórico do contrato (use as datas da tabela acima).
5. Clique **Export** e salve o arquivo gerado pelo NT8 em:
   ```
   e:\CAOS\dados\MNQ\<MNQ_MM-YY>\<minute|day>\MNQ <MM>-<YY>.<Serie>.txt
   ```
   Exemplo: para Last/minute do MNQ 03-26 → `e:\CAOS\dados\MNQ\MNQ_03-26\minute\MNQ 03-26.Last.txt`.

> O NT8 exporta como arquivo texto com extensão `.txt`, separador `;`, sem cabeçalho e timestamp em horário local da máquina. Esse arquivo é o **input** do passo de normalização descrito a seguir — não tente alimentar o `Skill_Data_Reader` diretamente com ele.

## Schema esperado pelo `Skill_Data_Reader` (Spec 2)

Cada CSV exportado pelo NT8 tem o cabeçalho default do NinjaTrader (sem nomes de coluna em CSV simples). O `Skill_Data_Reader` (refatorado no Spec 5+) detecta o formato e normaliza para o schema canônico:

```csv
timestamp,open,high,low,close,volume
2026-01-02T13:30:00Z,21500.25,21501.50,21499.75,21500.75,1234
...
```

Particularmente:

- `timestamp` em UTC (NT8 exporta em fuso local do PC; o normalizador converte).
- Linhas em ordem cronológica estritamente crescente (sem duplicatas e sem retorno no tempo).
- Sem linhas em branco entre barras.

## Pós-exportação: normalizar arquivos `.txt` do NT8 → `.csv` canônico

O NT8 exporta arquivos com extensão `.txt` (não `.csv`), nome com espaço (`MNQ 03-26.Last.txt`), separador `;`, sem cabeçalho e timestamp em horário local da máquina (`AAAAMMDD HHMMSS` para minute, `AAAAMMDD` para day). Antes de gerar o manifesto, traduza para o schema canônico:

```cmd
caos dados normalizar --root e:\CAOS
```

Por padrão assume fuso `America/Sao_Paulo` (UTC-3 fixo desde fim do horário de verão brasileiro em 2019). Se a máquina onde o NT8 exporta usa outro fuso:

```cmd
caos dados normalizar --root e:\CAOS --fuso UTC
caos dados normalizar --root e:\CAOS --fuso America/New_York
```

Características:

- Os arquivos `.txt` originais ficam intactos (auditoria).
- Cada `.txt` gera `<serie>.csv` no mesmo diretório (`Last.txt → last.csv`, `Ask.txt → ask.csv`, `Bid.txt → bid.csv`).
- Idempotente: se o `.csv` já existe e é mais novo que o `.txt`, é pulado. Use `--forcar` para reprocessar.
- Validações automáticas: schema correto (6 campos por linha), timestamps parseáveis e estritamente crescentes, valores numéricos.
- Em caso de erro o `.csv` parcial é descartado (escrita atômica via `.csv.tmp`).

## Pós-exportação: gerar manifesto

Após exportar pelo menos os arquivos `last.csv` que vão ser usados pelo Walk-Forward, rode:

```cmd
caos manifesto build --root e:\CAOS
```

Isso percorre `dados/MNQ/` recursivamente, computa SHA-256 de cada CSV e grava `dados/MNQ/manifesto.json`. Sem este passo, `caos walk-forward run` aborta com `manifesto-invalido`.

Para reverificar a integridade quando suspeitar de modificação:

```cmd
caos manifesto verify --root e:\CAOS
```

## Ordem de prioridade recomendada

Para validar o pipeline ponta-a-ponta antes de exportar tudo:

1. **MNQ_03-26 / minute / last.csv** — primeiro arquivo a exportar; suficiente para um Walk-Forward de smoke da `EstrategiaORB`.
2. Demais `last.csv` em ordem cronológica reversa (06-26, 12-25, 09-25, 06-25) — fornece base mais ampla para janelas de Walk-Forward.
3. `day/last.csv` de todos — útil para análises de regime e filtros macro.
4. `ask.csv` / `bid.csv` (todas as granularidades) — apenas quando estratégias futuras precisarem de spread/microestrutura.
5. `tick/` (futuro) — apenas para estratégias de order flow (Rodrigo) ou validação tick-a-tick.

## Política de versionamento

- A pasta `dados/MNQ/` está em `.gitignore` para os arquivos `.csv` e `.json` não inflarem o repo (são gigabytes).
- Apenas a estrutura de diretórios (via `.gitkeep`) e este `README.md` são versionados.
- O `manifesto.json` SHA-256 funciona como prova de integridade auditável — quando a Decisão do Conselho referenciar um Walk-Forward, o `manifesto_hash` correspondente é gravado na Decisão (R8 do Spec 1).
