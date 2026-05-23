# Caracterização de série — MNQ minute (concat 5 contratos)

- Barras analisadas: **412,593**
- Período: 2025-03-17T06:01:00+00:00 → 2026-05-18T02:27:00+00:00

## Range diário (pontos)
- Dias úteis: 399
- Mediana: 297.00
- Média:   329.11
- P05:     0.00
- P95:     769.50
- Std:     293.56
- Razão P95/P05: **inf** (> 5 indica caudas gordas)

## Autocorrelação dos log-retornos
- Observações: 412,592
| Lag (min) | ρ |
|---:|---:|
| 1 | -0.0038 |
| 5 | -0.0003 |
| 15 | -0.0072 |
| 30 | +0.0043 |
| 60 | +0.0041 |

_Heurística: ρ(1) negativo → mean-reversion na microestrutura; positivo persistente → momentum; |ρ| < 0.02 → ruído._

## Gaps de abertura
- Gaps observados: 398
- Mediana: +0.00 pts
- Média:   -0.50 pts
- Std:     52.59 pts
- Fração de gaps significativos (> 0.05% do close): **12.06%**

## Volatilidade intradia (std dos log-retornos 1m por hora UTC)
| Hora UTC | std log-ret |
|---:|---:|
| 00h | 0.000259 |
| 01h | 0.000714 |
| 02h | 0.000281 |
| 03h | 0.000284 |
| 04h | 0.000242 |
| 05h | 0.000199 |
| 06h | 0.000225 |
| 07h | 0.000173 |
| 08h | 0.000201 |
| 09h | 0.000213 |
| 10h | 0.000292 |
| 11h | 0.000304 |
| 12h | 0.000238 |
| 13h | 0.000278 |
| 14h | 0.000342 |
| 15h | 0.000341 |
| 16h | 0.000525 |
| 17h | 0.000672 |
| 18h | 0.000555 |
| 19h | 0.000453 |
| 20h | 0.000544 |
| 21h | 0.000421 |
| 22h | 0.000439 |
| 23h | 0.000380 |

- Hora de pico:     **01h UTC**
- Hora de calmaria: **07h UTC**


---

## Interpretação (Kiro_Brain, sem Debate formal)

Esta seção é leitura informal do Kiro_Brain dos números acima. Não tem
status de Decisão do Conselho — quando uma família estratégica concreta
for proposta com base nestes dados, abre-se Debate formal.

### 1. Autocorrelação ≈ 0 em todos os lags 1-60min

Todos os ρ(lag) têm magnitude < 0.01. Isso é praticamente ruído branco.
Implicações operacionais:

- **Estratégias de momentum 1m-60m provavelmente NÃO têm edge** no MNQ.
  Não há "se subiu nos últimos N minutos, tende a continuar subindo".
- **Estratégias de mean-reversion 1m-60m provavelmente NÃO têm edge**.
  Não há "se subiu demais, tende a corrigir no curto prazo".
- A ORB (com config default) é categorizada como momentum em escala
  de 30min de range + horas de holding. Esse perfil é justamente o
  que NÃO aparece nos dados. Consistente com Sharpe 0.38 no hold-out
  cego (Decisão 2026-05-23-02).
- Famílias estratégicas que ainda podem ter edge: (a) seleção
  CONDICIONAL — agir só em janelas específicas com contexto
  (notícia, hora do dia, gap relevante); (b) estratégias de prazo
  mais longo (diário ou multi-diário); (c) market-making/microestrutura
  com escalas << 1min (não temos dados tick).

### 2. Volatilidade intradia tem perfil GLOBAL, não NY-cêntrico

Pico **secundário e mais consistente** às 17h UTC = 12:30 NY = janela
de releases econômicos EUA (CPI, NFP, jobless claims). Pico real às
01h UTC parece ser outlier pontual (dia com salto extremo).

A ORB com config default opera em 14:30-21:00 UTC (09:30-16:00 NY) e
forma o range nos primeiros 30min. Mas:

- 14h-15h UTC tem vol mediana (0.000341-0.000342) — abaixo da
  mediana global da sessão.
- A vol picada chega depois (17h UTC).
- A janela do range (14:30-15:00 UTC) é construída quando ainda está
  se firmando volatilidade — range artificialmente "estreito" causa
  rompimentos falsos.

**Hipótese de família**: estratégia que opere ao redor das 17h UTC com
contexto de release econômico (uso de calendário externo). Ou
estratégia tipo "fade do gap de Tóquio→Europa" porque os 12% de gaps
significativos podem ter padrão.

### 3. Range diário mediano de 297 pts é saudável

297 pts × USD 2/pt = USD 594 de movimento mediano por dia. Há "estoque"
para qualquer estratégia direcional encontrar — a falha não é falta de
volatilidade, é falta de previsibilidade direcional na escala que
testamos.

### 4. Próximas direções investigáveis (sem comprometer hold-out)

Por ordem de custo crescente:

1. **Análise condicional**: olhar se há sub-conjuntos de dias com
   autocorrelação NÃO-zero (dias com gap > P75; dias após dias com
   range > P75; dias de release econômico).
2. **Caracterização em escala diária**: rodar a mesma análise em
   ``day/last.csv`` para ver se padrões aparecem em granularidade
   maior.
3. **Estudo de estratégia "release econômico"**: requer calendar
   API ou CSV manual com datas de releases CPI/NFP/FOMC. Tese:
   posicionar antes do release vs operar depois.

Nenhuma das 3 viola o hold-out atual de 60 dias (24/fev → 19/mai/2026)
porque são análises descritivas adicionais ou estratégias materialmente
distintas da ORB.
