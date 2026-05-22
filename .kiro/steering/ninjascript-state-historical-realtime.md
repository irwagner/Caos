---
data: 2026-05-14
autor: Athena
justificativa: Documenta a distinção entre State.Historical e State.Realtime no NinjaScript 8 para evitar bugs de inicialização e de envio de ordens recorrentes em estratégias do projeto CAOS.
---

# Distinção entre `State.Historical` e `State.Realtime` no NinjaScript 8

Esta regra é referência obrigatória para qualquer agente do Conselho que
propor código C# em `04_CODIGO/ninjascript/`. Cobre R3.1 do `requirements.md`.

## Definições

### `State.Historical`

`State.Historical` indica que `OnBarUpdate` está sendo invocado durante o
processamento das barras carregadas no histórico, antes da estratégia se
conectar ao feed de dados em tempo real. Nesse estado, o NinjaTrader replica
o passado, barra a barra, para popular indicadores e simular as condições
em que a estratégia teria operado.

### `State.Realtime`

`State.Realtime` indica que a estratégia já consumiu todo o histórico e que
`OnBarUpdate` agora reflete cotações ao vivo do feed do broker. Este é o
único estado em que ordens são realmente enviadas ao mercado.

## Exemplos de código C#

### Exemplo `State.Historical`

```csharp
protected override void OnBarUpdate()
{
    if (State == State.Historical)
    {
        // Apenas atualiza indicadores e estatísticas locais.
        // Não envia ordens reais.
        if (Close[0] > Open[0])
            barrasDeAlta++;
        return;
    }
}
```

### Exemplo `State.Realtime`

```csharp
protected override void OnBarUpdate()
{
    if (State != State.Realtime) return;

    // Só aqui é seguro disparar EnterLong/EnterShort de verdade.
    if (Close[0] > High[1])
        EnterLong(1, "BreakoutLong");
}
```

## Gotchas conhecidos

### `State.Historical`

- Variáveis de instância são re-inicializadas a cada `Configure`/`Historical`
  cycle quando a estratégia é reinstalada via `Strategy Builder`. Inicializar
  estado em `OnStateChange(State.Historical)` é diferente de `State.SetDefaults`
  e pode reiniciar contadores inesperadamente.
- `Print(...)` floods o output window quando chamado dentro do laço histórico
  para 250 mil barras de 1 minuto. Use guarda `if (CurrentBar % 1000 == 0)`
  para amostrar.
- Indicadores que dependem de `Times[0][0]` para janela de horário devem
  considerar fuso de exchange, não fuso da máquina, para que o backtest
  bata com o realtime.

### `State.Realtime`

- Ordens só são realmente enviadas em `State.Realtime`. Submetê-las em
  `State.Historical` afeta apenas a simulação interna, mas não a corretora.
- `OnBarUpdate` em `CalculateOnBarClose = false` dispara N vezes por barra
  (uma por tick). Sem proteção, `EnterLong` é chamado dezenas de vezes
  até a posição encher; use `Position.MarketPosition == MarketPosition.Flat`
  como guarda.
- A primeira barra de `Realtime` reusa `BarsArray[0]` parcialmente formado.
  Cuidados com `IsFirstTickOfBar` para acumular volume tick-a-tick.
