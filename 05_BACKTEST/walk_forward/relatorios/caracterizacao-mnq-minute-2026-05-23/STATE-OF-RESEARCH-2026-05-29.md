# State of Research — 2026-05-29

> Documento vivo. Substitui `STATE-OF-RESEARCH-2026-05-27.md` (mantido como histórico).
>
> **Marco da sessão**: re-replay 28/01-26/05/2026 do MNQ 06-26 pós-fix
> `BarsRequiredToTrade=19320` confirmou PnL **−USD 573,50** em 11 trades,
> cruzando o limiar **−USD 500** definido pelo Cerberus na
> `[[Decisao_2026-05-28-01]]`. Hold-out **suspenso definitivamente**.
> Aberto Debate `2026-05-29-01` para decidir entre **descarte puro**
> ou **re-engenharia mínima** — status `pendente-de-usuario`.

---

## 1. Estado atual do projeto

### Estratégia aprovada em `[[Decisao_2026-05-25-02]]` — agora SUSPENSA

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

**Status**: tag `caos-frozen-2026-05-25-02` **suspensa** desde
`[[Decisao_2026-05-28-01]]` (Veto_De_Risco condicional do Cerberus).
Re-replay 28/01-26/05/2026 falhou no critério quantitativo (PnL
−USD 573,50 ≤ limiar −USD 500). Tag permanece suspensa
**incondicionalmente** até nova Decisão com
`aprovado_walk_forward=true`.

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

## 2. Debate aberto: `2026-05-29-01`

Slug: `descarte-ou-reengenharia-crabel-nr7-orb-sf-cb`. Gatilho **G5**
(contradiz `[[Decisao_2026-05-25-02]]`) + flag `--csharp` (qualquer
re-engenharia mexe em `*Logica.cs`).

### Propostas

| ID | Autor | Acao | Conf |
|---|---|---|---|
| P1 | Explorador | Descarte + nova candidata vinda de paper R12-aprovado | 55 |
| P2 | Manolo | Re-engenharia mínima: substituir NR7 por filtro de range absoluto K=80 ticks | 68 |
| P3 | Mister_M | Refazer hold-out com 252 dias úteis (N=11 é estatisticamente irrelevante) | 72 |
| P4 (implícita) | Devils_Advocate | Descarte puro, sem coupling com nova candidata, sem re-engenharia | 85 (na crítica) |

### Status: `pendente-de-usuario`

Conselho ficou em empate (P1+P4 = descarte vs P2+P3 = manter).
Athena delegou ao usuário a escolha entre:

- **(A) Descarte puro** (P4 do Devils_Advocate): arquivar em
  `02_ESTRATEGIAS/mortas/`, manter pipeline ocioso até paper
  R12-aprovado independente.
- **(B) Re-engenharia mínima** (P2 do Manolo, com K calibrado em
  janela 2025-01 a 2025-06 separada do WF original).

Independentemente de A ou B, tag `caos-frozen-2026-05-25-02`
permanece SUSPENSA até nova Decisão com `aprovado_walk_forward=true`.

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

---

## 4. Arquivos relacionados

- `e:\CAOS\CAOS_Council\debates\2026-05-29-01-descarte-ou-reengenharia-crabel-nr7-orb-sf-cb.md` (Debate aberto)
- `e:\CAOS\CAOS_Council\decisions\2026-05-28-01-bug-paridade-warmup-nr7-csharp.md` (Veto Cerberus em vigor)
- `e:\CAOS\CAOS_Zettelkasten\Decisoes_do_Conselho\Re_Replay_Pos_Fix_Warmup_2026-05-29.md` (registro do replay)
- `e:\CAOS\04_CODIGO\ninjascript\Strategy.cs` (commits `a281e47` + `240c089` + `17450e3`)
- `e:\CAOS\04_CODIGO\ninjascript\README_INSTALACAO_HOLDOUT.md` (Passo 3.5: Days to load >= 44)
- `e:\CAOS\.kiro\steering\ninjascript-api.md` (whitelist com `BarsRequiredToTrade`, `RealtimeErrorHandling`, `StopTargetHandling`)

---

## 5. Próxima ação esperada do usuário

1. Decidir entre **A** (descarte puro) ou **B** (re-engenharia mínima
   P2 com K=80 ticks calibrado em janela separada).
2. Comunicar a escolha no chat.
3. Kiro_Brain então:
   - Edita o bloco `sintese` do Debate `2026-05-29-01` para refletir
     a escolha vencedora (`proposta_aceita: P1` para A ou
     `proposta_aceita: P2` para B; ou mantém `null` se quiser
     fechar como pendente-de-usuario consolidado).
   - Roda `caos debate fechar 2026-05-29-01` para gerar Decisão
     formal com commit dedicado.
   - Para A: arquiva código em `02_ESTRATEGIAS/mortas/` (nota Zettel
     + `_index.md` atualizado).
   - Para B: implementa P2 em `EstrategiaCrabelLogica.cs` + porta
     Python espelho + abre novo WF longo de validação.

