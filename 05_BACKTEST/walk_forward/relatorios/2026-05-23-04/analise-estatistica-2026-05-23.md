---
agente_autor: Athena
area: Decisoes_do_Conselho
data_criacao: '2026-05-23T05:00:00Z'
id: analise-estatistica-pre-fomc-2026-05-23
relacionado: Decisao_2026-05-23-03
tags:
- t-stat
- pre-fomc
- autocorrelacao-condicional
- mean-reversion
titulo: Análise estatística complementar — Pre-FOMC + autocorrelação condicional
---

# Análise estatística complementar — sessão 2026-05-23

> Esta nota cumpre 4 análises estatísticas adicionais usando apenas
> os dados MNQ existentes (decisão do usuário de não exportar SPY/ES).
> Cobre rigor que faltou no anexo de inspeção (commit `73d985a`) e
> identifica nova direção de investigação.

## 1. t-stat formal sobre os 10 trades Pre-FOMC

| Métrica | Valor |
|---|---|
| N | 10 |
| Soma PnL bruto | +373.00 pts |
| Soma PnL líquido (Topstep) | **+361.80 pts** = USD 723.60 |
| Média PnL líquido | +36.18 pts |
| Std (ddof=1) | 183.25 pts |
| Win rate | 70.0% |
| **t-stat (líquido)** | **+0.624** |
| df | 9 |
| p-valor (bilateral) | 0.5324 |

**Veredito**: |t| = 0.62 < 2.0. **NÃO rejeita H0** (média = 0).
PnL acumulado positivo é estatisticamente indistinguível de zero
ao nível 5% pelo critério institucional Mesfin 2026 (T-stat ≥ 2.0).

A causa principal é o std elevado (183 pts) inflado pelo trade
catastrófico de mar/2026 (-412 pts). Se removermos esse trade
(análise sensível, não é "limpar dado", é diagnóstico): N=9, soma
+774, std ~108, t ≈ 2.39, p ≈ 0.04 — passaria. Mas isso é
data-snooping.

Conclusão honesta: **amostra fraca, sinal indistinguível de
ruído**. Decisão `2026-05-23-03` (pausa investigativa) confirmada.

## 2. Sanity check em granularidade day/last

| | minute/last | day/last |
|---|---:|---:|
| N trades | 10 | 10 |
| PnL bruto | +373.00 pts | +367.25 pts |
| PnL líquido | +361.80 pts | +356.05 pts |
| t-stat | +0.624 | +0.685 |

Diferença marginal entre granularidades — implementação consistente.
Bug confirmadamente ausente.

## 3. Anatomia do trade catastrófico (17/mar/2026 → 18/mar/2026)

| Campo | Valor |
|---|---|
| Entrada | 2026-03-17 23:59 UTC (20:59 NY) |
| Saída | 2026-03-18 23:59 UTC (20:59 NY) |
| Lado | long |
| Preço entrada | 25026.25 |
| Preço saída | 24613.50 |
| **PnL bruto** | **-412.75 pts** (= -USD 825.50) |
| MFE | +184.50 pts (intra-trade) |
| MAE | -462.25 pts (pior intra-trade) |

Contexto diário (D-5 a D+1):

| Dia | Open | Close | Range | Retorno | Notas |
|---|---:|---:|---:|---:|---|
| 2026-03-13 | 24570 | 24341 | 466 | -0.93% | sexta |
| 2026-03-16 | 24493 | 24869 | 543 | +1.53% | seg, alta forte |
| 2026-03-17 | 24869 | 25026 | 385 | +0.63% | **ENTRADA** |
| 2026-03-18 | 25026 | 24613 | 647 | **-1.65%** | **FOMC, sell-the-news** |
| 2026-03-19 | 24614 | 24617 | 401 | +0.01% | continuação lateral |

Padrão claro: mercado **subiu 2.16% nos 2 dias antes do meeting**
(16-17/mar). A entrada do nosso plugin foi exatamente no PICO da
sequência. Quando o FOMC anunciou, ocorreu correção de **-1.65%**
em 1 dia. Esse é o cenário clássico de "pre-FOMC drift já consumido
antes do nosso ponto de entrada — só sobra a correção".

Implicação: o paper Lucca-Moench reporta drift na **janela de 24h
ANTES do meeting**. Se entramos quando o drift JÁ está em curso,
podemos pegar a parte ruim. Versão mais sofisticada exigiria
condicionar entrada ao retorno cumulativo dos N dias anteriores
(se já subiu demais, não entra).

Mas isso é parâmetro novo. **Não vamos otimizar com N=10.**

## 4. Autocorrelação condicional dos log-retornos 1m

Repetindo a análise de caracterização (commit `8754f70`) mas
condicionando em sub-conjuntos.

| Sub-conjunto | ρ(1) | N |
|---|---:|---:|
| Todos os dias | -0.0038 | 412.592 |
| Range diário ≥ P75 (≥ 468 pts) | +0.0011 | 137.436 |
| Gap % ≥ P75 (≥ 0.003%) | -0.0021 | 116.664 |
| **Range diário < P25** | **-0.0464** | **6.358** |

**Achado novo**: dias de **BAIXA volatilidade** (range < P25, ou
seja, < ~150 pts) têm autocorrelação ρ(1) = **-0.046**, com N
suficiente (6358 observações) para descartar acaso (heurística:
|ρ| > 0.02 com N > 10000 sugere sinal não-aleatório; N=6358 é
fronteira mas magnitude robusta).

Sinal interpretado: **mean-reversion em dias de baixa volatilidade**.
Se a barra de 1min subiu, próxima tende levemente a cair, e
vice-versa.

### Por que isso pode ser real

- Em dias choppy (faixa estreita), market-makers dominam o fluxo;
  spread/inventário força reversão de pequenos desvios.
- Em dias trending (range alto), inventário do MM é absorvido;
  reversão some.
- Consistente com Andersen et al. 2018 (invariância intraday por
  trade-size).

### Por que pode NÃO ser tradeável

- Magnitude ρ = -0.046 é fraca; após custos de execução
  (slippage + comissão) o edge esperado por trade é ~0.05% × 25000
  = 12.5 pts brutos × 0.046 = ~0.6 pts. **Custo Topstep round-trip
  é 1.12 pts.** Provavelmente abaixo do break-even.
- Identificar "dia de baixa vol" requer informação que só fica
  disponível no fim do dia. Aplicação operacional exigiria
  estimador realtime (ATR rolante, range parcial cumulativo).
- 6358 observações divididas em ~85 dias úteis = ~75 minutos por
  dia. Pode haver concentração temporal (todas em uma faixa
  específica do dia).

## Sumário das 4 análises

| Análise | Resultado | Implicação |
|---|---|---|
| t-stat Pre-FOMC | t = +0.62, p = 0.53 | Sinal estatisticamente neutro com N=10 |
| Sanity check day vs minute | PnL difere < 2% | Implementação correta confirmada |
| Trade catastrófico mar/2026 | Mercado +2.16% antes, -1.65% no FOMC | "Drift já consumido" — variação de regime |
| Autocorrelação condicional | ρ = -0.046 em dias < P25 vol | **Possível direção nova: mean-reversion condicional** |

## Direção mais promissora identificada nesta análise

**Mean-reversion intraday condicional a baixa volatilidade** é
candidata mais forte que sweeps na ORB ou variantes da Pre-FOMC
porque:

1. Tem **base estatística direta** (ρ = -0.046 com N significativo)
   medida na nossa série, não emprestada da literatura.
2. Não introduz parâmetro otimizável OBRIGATÓRIO (limiar P25 do
   range é definição estatística, não escolha discricionária).
3. Frequência operacional alta — em dias selecionados, há ~75
   minutos de operação possível. Amostra cresce rápido.
4. Edge esperado por trade pequeno mas:
   - Se 60% das barras têm sinal certo, custo 1.12 pts é absorvido
     em poucos trades.
   - Cálculo break-even: precisa edge bruto > 1.12 / size_posição
     em pontos.

## Próximas ações informais

Nenhuma destas é Decisão do Conselho — apenas registro:

1. **Continuar pausa do Pre-FOMC** conforme `2026-05-23-03`. Aguardar
   mais ~5-8 meetings antes de revisitar.
2. **Investigar mean-reversion condicional**:
   - Confirmar ρ = -0.046 com bootstrap de bloco (separar amostra
     em 2 partes, testar estabilidade).
   - Estimar distribuição empírica de PnL bruto por trade
     condicionando à barra anterior (sem otimização — só descritiva).
   - Se distribuição mostrar média positiva > 1.12 pts líquido
     com t-stat > 2 sobre bootstrap, abrir Debate sobre família.
3. Alternativa conservadora: **parar tudo até dados novos chegarem**
   conforme princípio anti-overfit.

A escolha entre (2) e (3) é tema de Debate quando o usuário decidir.


---

## 5. Investigação adicional do mean-reversion condicional

> Após o achado de ρ(1) = -0.046 em dias < P25 vol, executei análise
> de robustez antes de propor família estratégica. **Resultado: o
> sinal NÃO se sustenta sob escrutínio** — registro a não-descoberta.

### 5.1 Estabilidade por sub-amostra (5 contratos)

| Sub-amostra | N total | ρ geral | N baixa-vol | ρ baixa-vol |
|---:|---:|---:|---:|---:|
| 1 | 82.518 | +0.003 | 71 | NaN |
| 2 | 82.518 | -0.019 | 32 | NaN |
| 3 | 82.518 | -0.016 | 203 | +0.011 |
| 4 | 82.518 | -0.013 | 1.940 | **-0.050** |
| 5 | 82.520 | -0.000 | 5.372 | +0.008 |

Apenas **1/3 sub-amostras com N suficiente** apresenta ρ < -0.02
(a quarta, MNQ_03-26 dez/2025 → mar/2026). As demais sub-amostras
têm ρ próximo de zero ou positivo. **Achado original era artefato
de concentração em um contrato específico.**

### 5.2 Distribuição condicional do retorno

Em dias de baixa vol, dividindo barras pelo sinal da barra anterior:

| Bucket | N | Média log | t-stat |
|---|---:|---:|---:|
| Barra anterior + | 2.963 | -0.000002 (~-0.04 pts) | -0.71 |
| Barra anterior - | 3.020 | +0.000001 (~+0.02 pts) | +0.32 |
| Barra anterior 0 | 375 | -0.000003 (~-0.07 pts) | -0.72 |

Nenhum bucket tem |t| > 2. **Hipótese de mean-reversion
direcional NÃO é rejeitada nem confirmada — sinal indistinguível
de zero pelo teste t.**

### 5.3 Edge bruto por trade hipotético

Estratégia ideal: contrarian de 1m em dias de baixa vol
(compra se barra anterior caiu, vende se subiu).

| Métrica | Valor |
|---|---|
| N trades | 5.983 |
| Soma PnL bruto | +192.50 pts |
| Média por trade | +0.032 pts |
| Std por trade | 3.40 pts |
| Custo Topstep | 1.12 pts |
| **Edge líquido por trade** | **-1.09 pts** ❌ |
| Win rate | 48.7% |

**Edge negativo após custo. Estratégia é destrutiva.**

### 5.4 Conclusão da investigação adicional

O achado inicial de ρ = -0.046 era **falso positivo por
particionamento**. O sinal:

1. **Não é estável** entre contratos (vem essencialmente de 1).
2. **Não é direcional** quando testado pela média condicional.
3. **Não é rentável** mesmo na simulação ideal (edge bruto ~0.03
   pts vs custo 1.12 pts).

Mean-reversion condicional a baixa vol está **descartada como
direção operacional** com os dados disponíveis. É exatamente o
tipo de coisa que o split tripartite e o ceticismo do
Devils_Advocate previnem.

### Sumário atualizado das direções conhecidas

| Família | Status |
|---|---|
| ORB minute breakout | **Rejeitada** (Decisão `2026-05-23-02`) |
| Pre-FOMC drift | **Pausa** (Decisão `2026-05-23-03`); aguardar dados |
| Mean-reversion condicional baixa vol | **Descartada** (esta análise) |
| Famílias OHLCV intraday genéricas | **Rejeitadas externamente** (Mesfin 2026) |

**Nenhuma direção viável ativa com os dados atuais.** A regra
anti-overfit (parar e esperar) é a única recomendação honesta.
