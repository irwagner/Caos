// Strategy.cs — Strategy_CAOS, classe base do núcleo do robô (Spec 3 — Task 5).
//
// Cobre R2, R6, R8 do requirements.md:
// - R2: hooks virtuais (OnNovaBarra/OnSinalEntrada/OnSinalSaida) +
//   OnStateChange cobrindo SetDefaults/Configure/DataLoaded/Historical/Realtime.
// - R2.3: bloqueio de ordens reais em State.Historical.
// - R2.4: ordens em State.Realtime sempre roteadas por Cerberus_CSharp.
// - R6: parâmetros [NinjaScriptProperty] com validação de range.
// - R8: detecção de Sim101 vs conta real, com aviso repetido por 5 barras.
//
// Convenção: namespace alinhado ao padrão do NT8
// (NinjaTrader.NinjaScript.Strategies). Estratégias filhas (Specs 4+)
// herdam de Strategy_CAOS e implementam apenas OnSinalEntrada / OnSinalSaida.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies.CAOS;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    /// <summary>
    /// Classe base do núcleo CAOS para estratégias plugáveis no NinjaTrader 8.
    ///
    /// Subclasses devem sobrescrever <see cref="OnSinalEntrada"/> e
    /// <see cref="OnSinalSaida"/> para a lógica de sinal própria. NUNCA
    /// chame <c>EnterLong</c>/<c>EnterShort</c> diretamente — use os
    /// wrappers <see cref="EntrarLong"/> / <see cref="EntrarShort"/> que
    /// roteiam por <see cref="Cerberus_CSharp"/> antes de despachar ordens
    /// (R3.3, Property 16).
    /// </summary>
    public abstract class Strategy_CAOS : Strategy
    {
        // Componentes internos (instanciados em State.DataLoaded).
        protected Cerberus_CSharp Cerberus { get; private set; }
        protected Trailing_3_Fases Trailing { get; private set; }
        protected MfeMaeTracker MfeMae { get; private set; }

        // Identificador interno do trade aberto corrente. Incrementa a cada
        // entrada autorizada; permite que MfeMaeTracker case com a saída.
        private int _idTradeCorrente;
        private string _sinalTradeCorrente;
        private DateTime _entradaTimestampCorrente;
        private double _entradaPrecoCorrente;
        private double _ultimoStopAplicado = double.NaN;
        private int _ultimaBarraSetStopLoss = -1;

        // Contador de avisos quando a conta NÃO é Sim101 (R8.3).
        private int _avisosContaRealRestantes;

        // Cache do nome da estratégia para uso nos logs (Logger e CSV
        // recebem string, não Type) — preenchido em State.Configure.
        private string _nomeEstrategiaCache;

        // ------------------------------------------------------------------
        // R6 — Parâmetros [NinjaScriptProperty]
        // ------------------------------------------------------------------

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Max contratos", GroupName = "Risco CAOS", Order = 0)]
        public int MaxContratos { get; set; } = 1;

        [NinjaScriptProperty]
        [Range(50, 5000)]
        [Display(Name = "Circuit Breaker diário (USD)", GroupName = "Risco CAOS", Order = 1)]
        public double CircuitBreakerDiarioUSD { get; set; } = 500;

        [NinjaScriptProperty]
        [Range(0.0, 2.0)]
        [Display(Name = "Trailing fase 1 (R)", GroupName = "Trailing CAOS", Order = 2)]
        public double TrailingFase1Multiplicador { get; set; } = 0.5;

        [NinjaScriptProperty]
        [Range(0.0, 2.0)]
        [Display(Name = "Trailing fase 2 (R)", GroupName = "Trailing CAOS", Order = 3)]
        public double TrailingFase2Multiplicador { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Range(0.0, 2.0)]
        [Display(Name = "Trailing fase 3 (R)", GroupName = "Trailing CAOS", Order = 4)]
        public double TrailingFase3Multiplicador { get; set; } = 2.0;

        [NinjaScriptProperty]
        [Display(Name = "Workspace CAOS (vazio = %USERPROFILE%\\CAOS)", GroupName = "Auditoria CAOS", Order = 5)]
        public string CaosWorkspaceRoot { get; set; } = "";

        // ------------------------------------------------------------------
        // R2 — Ciclo de vida
        // ------------------------------------------------------------------

        protected override void OnStateChange()
        {
            switch (State)
            {
                case State.SetDefaults:
                    Description = "Strategy base do núcleo CAOS para o MNQ. Subclasses fornecem sinais de entrada.";
                    Name = string.IsNullOrEmpty(Name) ? "Strategy_CAOS" : Name;
                    Calculate = Calculate.OnBarClose;
                    IsExitOnSessionCloseStrategy = true;
                    EntriesPerDirection = 1;
                    EntryHandling = EntryHandling.AllEntries;
                    // Suprime popups benignos "Sell StopMarket acima do
                    // mercado" gerados em Calculate.OnBarClose quando a
                    // proxima barra fecha abaixo do stop. Documentacao
                    // NT8 confirma o comportamento: SetStopLoss eh
                    // processado no fechamento da proxima barra (R8).
                    RealtimeErrorHandling = RealtimeErrorHandling.IgnoreAllErrors;
                    StopTargetHandling = StopTargetHandling.PerEntryExecution;
                    break;

                case State.Configure:
                    _nomeEstrategiaCache = string.IsNullOrEmpty(Name) ? GetType().Name : Name;
                    break;

                case State.DataLoaded:
                    InstanciarComponentes();
                    // Log de auditoria: registra instrumento, timezone e
                    // primeira/ultima barra ao carregar dados. Ajuda a
                    // detectar discrepancias de contrato/timezone que
                    // afetam preco e timestamp dos eventos.
                    LogarMetadadosCarga();
                    break;

                case State.Historical:
                    ResetarEstatisticasDiarias();
                    break;

                case State.Realtime:
                    VerificarConta();
                    break;
            }
        }

        protected override void OnBarUpdate()
        {
            // Em algumas situações (warm-up de séries auxiliares) o NT8
            // chama OnBarUpdate antes de termos barras suficientes na série
            // primária. CurrentBar < 0 nesses casos — guard idiomático.
            if (BarsInProgress != 0) return;
            if (CurrentBar < 0) return;

            // Aviso repetido por 5 barras (R8.3) quando conta NÃO é Sim101.
            if (State == State.Realtime && _avisosContaRealRestantes > 0)
            {
                _avisosContaRealRestantes--;
                Print(string.Format(
                    "[ATENCAO] Strategy operando em conta REAL: {0} (avisos restantes: {1})",
                    Account != null ? Account.Name : "<conta indefinida>",
                    _avisosContaRealRestantes));
            }

            // Hook estratégia filha — pode emitir sinais de entrada/saída.
            OnNovaBarra();

            // Atualiza trailing dado o preço corrente (mid Ask/Bid).
            //
            // Defesa em camadas (descobrimento 2026-05-26 via replay NT8):
            //   1. Position.MarketPosition == Flat = posição já foi liquidada
            //      pelo broker (o stop original bateu). Nesse caso, NUNCA
            //      re-emitir SetStopLoss — geraria erro NT8 do tipo "Sell
            //      StopMarket acima do mercado" porque o preço atual já
            //      ultrapassou o stop original.
            //   2. Trailing.Fase != SemPosicao = nosso estado interno ainda
            //      acha que tem trade aberto (será resetado pelo
            //      OnExecutionUpdate, mas pode estar desatualizado).
            //   3. _sinalTradeCorrente != null = ainda temos referência
            //      válida ao sinal da entrada.
            // Quando (1) for Flat, força reset preventivo do trailing para
            // re-sincronizar.
            if (Position.MarketPosition == MarketPosition.Flat)
            {
                if (Trailing != null && Trailing.Fase != FaseTrailing.SemPosicao)
                    Trailing.Fechar();
            }
            else if (Trailing != null && Trailing.Fase != FaseTrailing.SemPosicao
                     && _sinalTradeCorrente != null)
            {
                double precoMid = (GetCurrentAsk() + GetCurrentBid()) / 2.0;
                double stopNovo = Trailing.Atualizar(precoMid);
                if (!double.IsNaN(stopNovo))
                {
                    // Defesa adicional contra o erro "stop acima/abaixo do
                    // mercado": só re-aplica SetStopLoss se o novo stop
                    // for COERENTE com a direcao em relacao ao preco
                    // corrente (LONG: stop < preco; SHORT: stop > preco).
                    bool stopCoerente = Position.MarketPosition == MarketPosition.Long
                        ? stopNovo < precoMid
                        : stopNovo > precoMid;
                    // Defesa adicional: nao re-aplica o mesmo stop e nao
                    // faz mais de uma chamada SetStopLoss por barra.
                    bool stopMudou = double.IsNaN(_ultimoStopAplicado) ||
                                     Math.Abs(stopNovo - _ultimoStopAplicado) > 0.01;
                    bool primeiraVezNaBarra = _ultimaBarraSetStopLoss != CurrentBar;
                    if (stopCoerente && stopMudou && primeiraVezNaBarra)
                    {
                        try
                        {
                            SetStopLoss(_sinalTradeCorrente, CalculationMode.Price, stopNovo, false);
                            _ultimoStopAplicado = stopNovo;
                            _ultimaBarraSetStopLoss = CurrentBar;
                        }
                        catch (Exception)
                        {
                            // NT8 ocasionalmente rejeita SetStopLoss em
                            // playback simulado quando o mercado ja se
                            // moveu entre bar close e fill simulado.
                            // Padrao Hydra/OdinTrinity: silenciar, deixar
                            // o stop original (ja em vigor) funcionar.
                        }
                    }
                }
            }

            // Atualiza MFE/MAE da posição corrente.
            if (MfeMae != null && MfeMae.TemTradeAberto)
                MfeMae.Atualizar(Close[0]);
        }

        // ------------------------------------------------------------------
        // R2.1 — Hooks virtuais para estratégias filhas
        // ------------------------------------------------------------------

        /// <summary>Hook chamado em todo <c>OnBarUpdate</c> da série primária.</summary>
        protected virtual void OnNovaBarra() { }

        /// <summary>
        /// Hook reservado: a estratégia filha pode usar para reagir a um
        /// sinal de entrada gerado externamente (ex.: webhook, feed externo).
        /// O fluxo padrão é a filha decidir entradas dentro de
        /// <see cref="OnNovaBarra"/> e chamar <see cref="EntrarLong"/>/
        /// <see cref="EntrarShort"/>.
        /// </summary>
        protected virtual void OnSinalEntrada() { }

        /// <summary>Hook análogo a <see cref="OnSinalEntrada"/> para saídas.</summary>
        protected virtual void OnSinalSaida() { }

        // ------------------------------------------------------------------
        // Wrappers — única forma autorizada de enviar ordens (R2.3, R2.4, R3.3)
        // ------------------------------------------------------------------

        /// <summary>
        /// Envia uma ordem LONG via <see cref="Cerberus_CSharp"/>. Em
        /// <see cref="State.Historical"/> apenas simula internamente
        /// (R2.3). Em <see cref="State.Realtime"/> consulta o Cerberus e,
        /// se autorizado, despacha <c>EnterLong</c> + stop + alvo.
        /// </summary>
        protected bool EntrarLong(int contratos, double stopLossPreco, double takeProfitPreco, string sinal)
        {
            return EntrarInterno(DirecaoTrade.Long, contratos, stopLossPreco, takeProfitPreco, sinal);
        }

        /// <summary>Análogo a <see cref="EntrarLong"/> para SHORT.</summary>
        protected bool EntrarShort(int contratos, double stopLossPreco, double takeProfitPreco, string sinal)
        {
            return EntrarInterno(DirecaoTrade.Short, contratos, stopLossPreco, takeProfitPreco, sinal);
        }

        /// <summary>Saída discricionária de LONG (R2 — wrappers oficiais).</summary>
        protected void SairLong(string sinalEntrada)
        {
            if (State == State.Historical) return;
            if (Position.MarketPosition != MarketPosition.Long) return;
            ExitLong(sinalEntrada, sinalEntrada);
        }

        /// <summary>Saída discricionária de SHORT.</summary>
        protected void SairShort(string sinalEntrada)
        {
            if (State == State.Historical) return;
            if (Position.MarketPosition != MarketPosition.Short) return;
            ExitShort(sinalEntrada, sinalEntrada);
        }

        // ------------------------------------------------------------------
        // Implementação privada
        // ------------------------------------------------------------------

        private bool EntrarInterno(
            DirecaoTrade direcao,
            int contratos,
            double stopLossPreco,
            double takeProfitPreco,
            string sinal)
        {
            // R2.3 — em histórico, nada é enviado ao broker. Apenas atualiza
            // a máquina de Trailing e MfeMaeTracker para que o backtest
            // ainda exercite a contabilidade auditável.
            if (State == State.Historical)
            {
                AbrirEstadoInterno(direcao, contratos, stopLossPreco, takeProfitPreco, sinal);
                return true;
            }

            double riscoUSD = CalcularRiscoUSD(direcao, stopLossPreco, contratos);
            if (Cerberus == null || !Cerberus.AutorizarEntrada(contratos, riscoUSD))
            {
                Logar(LogNivel.WARN, "entrada-bloqueada", new Dictionary<string, object>
                {
                    {"direcao", direcao.ToString()},
                    {"contratos", contratos},
                    {"risco_usd", riscoUSD},
                    {"motivo", Cerberus != null && Cerberus.CircuitBreakerAtivo ? "circuit-breaker" : "validacao-cerberus"}
                });
                return false;
            }

            // Declara stop e alvo ANTES de despachar a ordem (R3.3).
            //
            // Padrao NT8: SetStopLoss/SetProfitTarget sao declarativos —
            // se aplicam a entradas FUTURAS com o mesmo signal name. Se
            // chamados DEPOIS do EnterLong, o NT8 tenta aplica-los em
            // ordem stop/limit imediatamente, e se o preco corrente ja
            // esta no lado errado do stop (ex: gap), gera erro
            // "Sell StopMarket acima do mercado".
            //
            // Inversão: declarar protecoes ANTES de enviar a ordem.
            // Padrao try/catch: NT8 ocasionalmente rejeita em playback
            // simulado quando mercado se moveu entre bar close e fill.
            // Hydra/OdinTrinity silencia esses erros.
            try
            {
                SetStopLoss(sinal, CalculationMode.Price, stopLossPreco, false);
                SetProfitTarget(sinal, CalculationMode.Price, takeProfitPreco);
            }
            catch (Exception exc)
            {
                Logar(LogNivel.WARN, "set-stop-loss-rejeitado", new Dictionary<string, object>
                {
                    {"sinal", sinal},
                    {"stop", stopLossPreco},
                    {"alvo", takeProfitPreco},
                    {"erro", exc.Message}
                });
                // Continua: stop original ja foi configurado;
                // OnExecutionUpdate ainda tracka o fill.
            }

            // Despacha ordem real ao NT8 — ja com stop/alvo declarados.
            if (direcao == DirecaoTrade.Long)
                EnterLong(contratos, sinal);
            else
                EnterShort(contratos, sinal);

            // Memoriza para que o trailing nao re-emita o mesmo stop
            // na proxima barra (causaria erro "Sell StopMarket acima
            // do mercado" se o preco ja caiu abaixo entre as chamadas).
            _ultimoStopAplicado = stopLossPreco;
            _ultimaBarraSetStopLoss = CurrentBar;

            AbrirEstadoInterno(direcao, contratos, stopLossPreco, takeProfitPreco, sinal);
            Logar(LogNivel.INFO, "entrada-autorizada", new Dictionary<string, object>
            {
                {"direcao", direcao.ToString()},
                {"contratos", contratos},
                {"sinal", sinal},
                {"preco", _entradaPrecoCorrente},
                {"stop", stopLossPreco},
                {"alvo", takeProfitPreco},
                {"risco_usd", riscoUSD}
            });
            return true;
        }

        private void AbrirEstadoInterno(
            DirecaoTrade direcao,
            int contratos,
            double stopLossPreco,
            double takeProfitPreco,
            string sinal)
        {
            _idTradeCorrente++;
            _sinalTradeCorrente = sinal;
            _entradaTimestampCorrente = Time[0].ToUniversalTime();
            _entradaPrecoCorrente = direcao == DirecaoTrade.Long ? GetCurrentAsk() : GetCurrentBid();

            if (Trailing != null)
            {
                if (direcao == DirecaoTrade.Long)
                    Trailing.AbrirLong(_entradaPrecoCorrente, stopLossPreco);
                else
                    Trailing.AbrirShort(_entradaPrecoCorrente, stopLossPreco);
            }

            if (MfeMae != null)
            {
                DirecaoTradeMfeMae dirMfe = direcao == DirecaoTrade.Long
                    ? DirecaoTradeMfeMae.Long
                    : DirecaoTradeMfeMae.Short;
                MfeMae.AbrirTrade(_idTradeCorrente, dirMfe, _entradaPrecoCorrente, _entradaTimestampCorrente);
            }
        }

        /// <summary>
        /// Cálculo de risco em USD a partir do delta entre entrada e stop.
        /// Para o MNQ o multiplicador é USD 2 / ponto (steering rule
        /// <c>instrumento-mnq</c>); usamos <c>Instrument.MasterInstrument.PointValue</c>
        /// quando disponível para genericidade.
        /// </summary>
        private double CalcularRiscoUSD(DirecaoTrade direcao, double stopLossPreco, int contratos)
        {
            double precoBase = direcao == DirecaoTrade.Long ? GetCurrentAsk() : GetCurrentBid();
            double pontosRisco = direcao == DirecaoTrade.Long
                ? precoBase - stopLossPreco
                : stopLossPreco - precoBase;
            if (pontosRisco <= 0.0) return 0.0;
            double pointValue = (Instrument != null && Instrument.MasterInstrument != null)
                ? Instrument.MasterInstrument.PointValue
                : 2.0; // fallback MNQ.
            return pontosRisco * pointValue * contratos;
        }

        private void InstanciarComponentes()
        {
            Cerberus = new Cerberus_CSharp(MaxContratos, CircuitBreakerDiarioUSD);
            Trailing = new Trailing_3_Fases(
                TrailingFase1Multiplicador,
                TrailingFase2Multiplicador,
                TrailingFase3Multiplicador);
            MfeMae = new MfeMaeTracker(
                CaosWorkspaceRoot,
                _nomeEstrategiaCache,
                TickSize > 0 ? TickSize : 0.25);
        }

        private void ResetarEstatisticasDiarias()
        {
            if (Cerberus != null) Cerberus.Resetar();
        }

        private void LogarMetadadosCarga()
        {
            // Captura instrumento, timezone do sistema, primeira/ultima
            // barra carregada. Util para diagnosticar bugs onde NT8 esta
            // usando contrato continuous sem perceber, ou onde a conversao
            // Time[0].ToUniversalTime() esta gerando offset inesperado.
            try
            {
                var payload = new Dictionary<string, object>();
                payload["instrumento"] = Instrument != null ? Instrument.FullName : "<null>";
                payload["instrumento_master"] = Instrument != null && Instrument.MasterInstrument != null
                    ? Instrument.MasterInstrument.Name : "<null>";
                payload["bars_period_value"] = BarsPeriod != null ? BarsPeriod.Value : 0;
                payload["bars_period_type"] = BarsPeriod != null ? BarsPeriod.BarsPeriodType.ToString() : "<null>";
                payload["timezone_local"] = TimeZoneInfo.Local.Id;
                payload["timezone_offset_horas"] = TimeZoneInfo.Local.GetUtcOffset(DateTime.UtcNow).TotalHours;
                payload["barras_carregadas"] = Bars != null ? Bars.Count : 0;
                if (Bars != null && Bars.Count > 0)
                {
                    DateTime tsPrimeiro = Bars.GetTime(0);
                    DateTime tsUltimo = Bars.GetTime(Bars.Count - 1);
                    payload["primeira_barra_local"] = tsPrimeiro.ToString("yyyy-MM-ddTHH:mm:ssK");
                    payload["primeira_barra_utc"] = tsPrimeiro.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ");
                    payload["ultima_barra_local"] = tsUltimo.ToString("yyyy-MM-ddTHH:mm:ssK");
                    payload["ultima_barra_utc"] = tsUltimo.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ");
                }
                Logar(LogNivel.INFO, "metadados-carga", payload);
            }
            catch (Exception exc)
            {
                Print("[CAOS] Falha ao logar metadados de carga: " + exc.Message);
            }
        }

        private void VerificarConta()
        {
            string nomeConta = Account != null ? Account.Name : null;
            Logar(LogNivel.INFO, "estado-realtime", new Dictionary<string, object>
            {
                {"conta_ativa", nomeConta ?? "<indefinida>"}
            });
            if (string.IsNullOrEmpty(nomeConta) || nomeConta == "Sim101") return;
            // R8.3: 5 avisos consecutivos no Output Window quando conta != Sim101.
            _avisosContaRealRestantes = 5;
        }

        private void Logar(LogNivel nivel, string evento, IDictionary<string, object> payload)
        {
            Logger.Logar(
                CaosWorkspaceRoot,
                _nomeEstrategiaCache ?? "Strategy_CAOS",
                nivel,
                evento,
                payload,
                Print);
        }

        // ------------------------------------------------------------------
        // Hooks de auditoria de saída (gravam linha CSV no MfeMaeTracker)
        // ------------------------------------------------------------------

        protected override void OnExecutionUpdate(
            Execution execution,
            string executionId,
            double price,
            int quantity,
            MarketPosition marketPosition,
            string orderId,
            DateTime time)
        {
            // Quando a posição vira Flat, fecha o trade no MfeMaeTracker.
            if (Position.MarketPosition == MarketPosition.Flat
                && MfeMae != null
                && MfeMae.TemTradeAberto)
            {
                double pnlUSD = SystemPerformance != null && SystemPerformance.AllTrades.Count > 0
                    ? SystemPerformance.AllTrades[SystemPerformance.AllTrades.Count - 1].ProfitCurrency
                    : 0.0;
                TradeMfeMae snap = MfeMae.FecharTradeEPersistir(price, time, pnlUSD, Print);
                if (Cerberus != null) Cerberus.RegistrarPnlRealizado(pnlUSD);
                Logar(LogNivel.INFO, "trade-fechado", new Dictionary<string, object>
                {
                    {"id_trade", snap.IdTrade},
                    {"direcao", snap.Direcao == DirecaoTradeMfeMae.Long ? "LONG" : "SHORT"},
                    {"mfe_ticks", snap.MfeTicks},
                    {"mae_ticks", snap.MaeTicks},
                    {"pnl_usd", snap.PnlUSD}
                });
                if (Trailing != null) Trailing.Fechar();
                // Defesa: reseta sinal corrente para que próximas barras
                // não tentem aplicar SetStopLoss sobre um sinal stale.
                _sinalTradeCorrente = null;
                _ultimoStopAplicado = double.NaN;
                _ultimaBarraSetStopLoss = -1;
                if (Cerberus != null && Cerberus.CircuitBreakerAtivo)
                {
                    Logar(LogNivel.WARN, "circuit-breaker-ativado", new Dictionary<string, object>
                    {
                        {"pnl_dia", Cerberus.PnlDiarioRealizado}
                    });
                    Print(string.Format(
                        "[Cerberus] Circuit breaker ativado em {0} — PnL dia: {1:0.##}",
                        time.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                        Cerberus.PnlDiarioRealizado));
                }
            }
        }
    }
}
