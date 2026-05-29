# State of Research — 2026-05-29

> Documento vivo. Substitui `STATE-OF-RESEARCH-2026-05-27.md` (mantido como histórico).
>
> **Marco da sessão**: re-replay 28/01-26/05/2026 do MNQ 06-26 pós-fix
> `BarsRequiredToTrade=19320` confirmou PnL **−USD 573,50** em 11 trades,
> cruzando o limiar **−USD 500** definido pelo Cerberus na
> `[[Decisao_2026-05-28-01]]`. Hold-out **suspenso definitivamente**.
> `[[Decisao_2026-05-29-01]]` aprovou caminho B (P2 / range_absoluto)
> com fallback automático para A. **Calibração da P2 falhou
> empiricamente** (`[[Refutacao_P2_Range_Absoluto_2026-05-29]]`).
> **Fallback A acionado**: estratégia da `[[Decisao_2026-05-25-02]]`
> está definitivamente arquivada. Tag `caos-frozen-2026-05-25-02`
> SUSPENSA permanentemente.

---

## 1. Estado atual do projeto

### Estratégia da `[[Decisao_2026-05-25-02]]` — ARQUIVADA

```
EstrategiaCircuitBreaker(
    EstrategiaSpreadFilter(
        EstrategiaORBCrabel(modo_nr="nr7"),
        modo="mediana_diaria",
        warmup=30 minutos,
        running_median=True
    ),
    diario=-250 pts, semanal=-750 pts, janela=-1000 pts
)
```

**Status**: ARQUIVADA em 2026-05-29 via fallback A da Decisão
`2026-05-29-01`. Tag `caos-frozen-2026-05-25-02` permanece SUSPENSA
permanentemente. Estratégia **não opera mais** em hold-out, replay
ou produção.

### Pipeline atual

**Vazio.** Aguarda paper R12-aprovado independente para nova
candidata. Critérios R12 mínimos:

- Sharpe ≥ 1.0 em out-of-sample ≥ 30 observações
- Survivorship bias tratado
- Instrumento batendo (MNQ ou equivalente)
- Sample ≥ 200

Lista de candidatos em `shopping-list-fontes-notebooklm-2026-05-25.md`
ainda não foi triada formalmente.

### Histórico de fixes aplicados

| Decisão / Commit | Bug | Fix |
|---|---|---|
| `[[Decisao_2026-05-26-01]]` | NR7 aceitava domingos do Globex | `MIN_BARRAS_DIA_VALIDO=300` + `DiaDaSemanaEhValido` |
| `[[Decisao_2026-05-28-01]]` (parte) | `BarsRequiredToTrade` defensivo | `=19320` (14 dias úteis) em `State.SetDefaults` |
| Commit `240c089` | `MfeMaeTracker` "ja tem trade aberto" | Force-close defensivo de MfeMae+Trailing antes de reabrir |
| Commit `17450e3` | Mesmo erro persistia em `State.Historical` | Guard `CurrentBar < BarsRequiredToTrade` em `EntrarInterno` |

**Fix técnico funcionou**: 0 ocorrências do erro `MfeMaeTracker ja tem
trade aberto` no replay novo. Mas resultado financeiro **idêntico**
ao replay pré-fix (−USD 573,50).

### Métricas WF longo pós-fix NR7 (validação 14 meses, 2026-05-27)

Mantidas como referência histórica, MAS **não refletem** comportamento
no MNQ 06-26 recente:

| Config WF | Sharpe mediana | PnL total | Trades |
|---|---|---|---|
| 60+10 | +9.07 | +1311 | 28 |
| 60+20 | +8.11 | +1287 | 26 |
| 80+20 | +8.11 | +1287 | 25 |
| 100+20 | +7.15 | +1019 | 22 |

### Re-replay NT8 28/01-26/05/2026 (MNQ 06-26)

| Métrica | Valor |
|---|---|
| Trades | 11 |
| Vitórias / Derrotas / BE | 4 / 6 / 1 |
| Win-rate | 36,4% |
| **PnL** | **−USD 573,50** |
| Maior win | +USD 537,50 (26/03 SHORT) |
| Maior perda | −USD 307,00 (11/03 LONG) |
| Long / Short | 4 / 7 |

PnL/dia útil ≈ **−USD 6,75**. Anualizado (252 dias) ≈ **−USD 1.700**.

### Divergência WF longo vs replay recente

WF longo prometia anualização de **+USD 1.100/ano** com 1 contrato.
Replay recente entrega **−USD 1.700/ano** extrapolado. Divergência
**USD 2.800/ano** — ordem de grandeza idêntica à descoberta na
auditoria `d8e34dc` antes do fix técnico. **Conclusão**: o fix do
warmup era necessário, mas **não suficiente** para salvar a
estratégia. O edge prometido pelo WF longo não se confirma fora da
amostra de calibração.

---

## 2. Debate `2026-05-29-01` — concluído com fallback A

Slug: `descarte-ou-reengenharia-crabel-nr7-orb-sf-cb`. Gatilho **G5**
(contradiz `[[Decisao_2026-05-25-02]]`) + flag `--csharp`. Commit
da Decisão: `5426113`.

### Propostas

| ID | Autor | Ação | Conf |
|---|---|---|---|
| P1 | Explorador | Descarte + nova candidata vinda de paper R12-aprovado | 55 |
| P2 | Manolo | Re-engenharia mínima: substituir NR7 por filtro de range absoluto K=80 ticks | 68 |
| P3 | Mister_M | Refazer hold-out com 252 dias úteis (N=11 é estatisticamente irrelevante) | 72 |
| P4 (implícita) | Devils_Advocate | Descarte puro, sem coupling com nova candidata, sem re-engenharia | 85 (na crítica) |

### Resultado: P2 com fallback A consumado

Usuário escolheu **caminho B (P2)** com fallback automático para A
caso a calibração falhasse. Implementação Python da P2 foi feita
(`orb_crabel.py` ganhou modo `range_absoluto` com 10 testes novos),
**mas a calibração refutou a P2 antes de gerar código C# ou WF longo**.

Detalhes em `[[Refutacao_P2_Range_Absoluto_2026-05-29]]`:

1. K=80 ticks proposto pelo Manolo era cego ao dataset (ranges
   reais ~540 pts, K=20 pts gera 0 dias elegíveis).
2. Volatilidade do MNQ varia ~37% no P17 entre 2025-03/04 e
   2025-05/06 — qualquer K fixo é não-estacionário.
3. Filtro absoluto K seleciona regime macro de volatilidade,
   não compressão local — falha conceitual da P2.

**Fallback A acionado**: estratégia arquivada permanentemente.

---

## 3. Lições aprendidas

### WF longo sozinho NÃO valida estratégia

A `[[Decisao_2026-05-25-02]]` aprovou a estratégia com Sharpe mediana
+2.91 sobre 5 cortes anchored 60+10/60+20/80+20/100+20, todos com
PnL > +USD 1000. Apesar disso, em janela completamente fora do WF
(28/01 → 26/05/2026, MNQ 06-26 contrato corrente), a estratégia
entrega PnL **−USD 573,50** em 11 trades. **WF longo não é
hold-out genuíno**: as janelas de teste do WF estão dentro do
mesmo regime de mercado da janela de calibração.

### Critério quantitativo deve ser definido ANTES da observação

`[[Decisao_2026-05-28-01]]` definiu o limiar Cerberus com base em
"quantos USD a estratégia pode perder em 105 dias e ainda valer a
pena". O critério foi pré-registrado, então a observação
−USD 573,50 dispara descarte automaticamente — **isso é correto e
defendido por Devils_Advocate**.

Mas **o N=11 é genuinamente pequeno**. Mister_M (P3) tem ponto:
IC95% sobre PnL com N=11 cruza zero. Em outras palavras: o critério
−USD 500 era razoável **apenas se** assumirmos que o fix do warmup
restauraria paridade Python↔C# nessa janela específica — o que não
aconteceu, pois o Days to load do chart nunca foi suficiente para
o `BarsRequiredToTrade=19320` mudar comportamento.

### Próximo pipeline precisa de hold-out **temporal** real

Qualquer próxima estratégia (seja P1, P2 ou nova ideia) deve ter:

1. **Hold-out temporal antes do treino** (forward-walk-anchored com
   datas separadas).
2. **Multiple-comparisons correction** sobre parâmetros do WF.
3. **Critério de descarte pré-registrado** com IC95% que NÃO
   atravesse zero para o N esperado.

Sem isso, o pipeline de Decisões do Conselho continua emitindo
estratégias que vão para hold-out e descartam-se por estatística
de N pequeno.

### Threshold absoluto não funciona em série não-estacionária

`[[Refutacao_P2_Range_Absoluto_2026-05-29]]` documenta a falha da
P2 antes mesmo da implementação C#. Crabel usou janela móvel (NR7)
precisamente porque o MNQ muda de regime — substituir uma especificação
**relativa** por uma **absoluta** (K fixo) ganha simplicidade
Python↔C# mas perde robustez ao regime. Se uma próxima estratégia
quiser eliminar dependência de janela em C# (motivado pelo bug
de paridade da `[[Decisao_2026-05-28-01]]`), considerar:

- **Filtro percentil rolante** (mantém invariância a regime, mas
  precisa de janela como NR7 → volta à estaca zero).
- **Filtro ATR-normalizado** (range[D-1] / ATR(20)[D-1] ≤ 0.5).
- **Filtro de regime macro externo** (VIX equivalente).

---

## 4. Arquivos relacionados

- `e:\CAOS\CAOS_Council\debates\2026-05-29-01-descarte-ou-reengenharia-crabel-nr7-orb-sf-cb.md` (Debate fechado, P2 com fallback A)
- `e:\CAOS\CAOS_Council\decisions\2026-05-29-01-descarte-ou-reengenharia-crabel-nr7-orb-sf-cb.md` (Decisão formal, commit `5426113`)
- `e:\CAOS\CAOS_Zettelkasten\Decisoes_do_Conselho\Refutacao_P2_Range_Absoluto_2026-05-29.md` (refutação empírica da P2 + acionamento do fallback A)
- `e:\CAOS\CAOS_Zettelkasten\Decisoes_do_Conselho\Re_Replay_Pos_Fix_Warmup_2026-05-29.md` (replay −USD 573,50 que disparou Debate)
- `e:\CAOS\CAOS_Council\decisions\2026-05-28-01-bug-paridade-warmup-nr7-csharp.md` (Veto Cerberus original)
- `e:\CAOS\CAOS_Orchestrator\caos\walk_forward\estrategias\orb_crabel.py` (modo `range_absoluto` adicionado, mas inativo em qualquer estratégia)
- `e:\CAOS\CAOS_Orchestrator\tests\unit\test_orb_crabel.py` (10 testes novos validam lógica do filtro absoluto)
- `e:\CAOS\scripts\calibrar_range_absoluto_2026-05-29.py` (script que refutou empiricamente a P2)
- `e:\CAOS\04_CODIGO\ninjascript\Strategy.cs` (commits `a281e47` + `240c089` + `17450e3` — defesa de warmup, mantida para qualquer próxima estratégia C#)

---

## 5. Próxima ação esperada do usuário

Pipeline ocioso. Não há ação imediata.

Quando surgir paper R12-aprovado da `shopping-list-fontes-notebooklm-2026-05-25.md`
(triagem ainda não feita formalmente), abrir novo Spec/Debate para
nova candidata.

### Notas para o próximo Spec

A `[[Refutacao_P2_Range_Absoluto_2026-05-29]]` deixou três caminhos
para eliminar dependência de janela em C# sem cair na mesma
armadilha de não-estacionariedade da P2:

1. **Filtro percentil rolante** (volta a precisar de janela)
2. **Filtro ATR-normalizado** (range[D-1] / ATR(20)[D-1] <= 0.5)
3. **Filtro de regime macro externo** (VIX equivalente)

Nenhum está no escopo desta Decisão; são notas para planejamento.

