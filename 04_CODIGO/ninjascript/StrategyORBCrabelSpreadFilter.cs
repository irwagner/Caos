// StrategyORBCrabelSpreadFilter.cs — estratégia APROVADA do CAOS.
//
// Equivalente NinjaScript de:
//   EstrategiaCircuitBreaker(
//     EstrategiaSpreadFilter(
//       EstrategiaORBCrabel(modo_nr="nr7"),
//       modo="mediana_diaria", warmup=30, running median
//     ),
//     diario=-250 pts, semanal=-750 pts, janela=-1000 pts
//   )
//
// Aprovado para Walk-Forward observacional via Decisao 2026-05-25-02
// (commit 7eddd30, tag caos-frozen-2026-05-25-02).
//
// PRE-CONDICOES OPERACIONAIS (Decisao 2026-05-25-02):
//   1. Hold-out cego de 60 dias uteis prospectivos antes de USD real.
//   2. MaxContratos=1 nos primeiros 30 dias de operacao.
//   3. Liberacao para MaxContratos=2 exige 30 dias uteis sem trigger
//      de CB de janela ou semanal.
//   4. Debate de seguimento obrigatorio em 30 dias para re-avaliar
//      limites do CB com dados reais.
//
// Procedimento de instalacao (manual — freio humano #1):
//   1. Copiar TODOS os arquivos .cs deste diretorio para
//      %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\
//      (Strategy.cs, Cerberus.cs, TrailingTresFases.cs, MfeMaeTracker.cs,
//       Logger.cs, EstrategiaORBLogica.cs, EstrategiaCrabelLogica.cs,
//       SpreadFilterLogica.cs, CircuitBreakerEstendido.cs, ESTE arquivo).
//   2. Abrir NinjaScript Editor (Tools -> Edit NinjaScript -> Strategy).
//   3. F5 para compilar. Resolver erros se aparecerem.
//   4. NT8: New Strategy -> "StrategyORBCrabelSpreadFilter" -> em chart MNQ 1m.
//   5. Habilitar em conta Sim101 paper trading.

#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies.CAOS;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    /// <summary>
    /// Estrategia aprovada do CAOS — ORB filtrado por NR7 (Crabel) +
    /// SpreadFilter (running median) + CircuitBreaker (diario/semanal/janela).
    ///
    /// Subclasse de Strategy_CAOS: roteamento de ordens via Cerberus,
    /// trailing 3-fases, MFE/MAE auto-instrumentado, logs em
    /// 05_BACKTEST/logs/.
    /// </summary>
    public class StrategyORBCrabelSpreadFilter : Strategy_CAOS
    {
        // ------------------------------------------------------------------
        // Parametros [NinjaScriptProperty] — paridade com YAML de WF
        // ------------------------------------------------------------------

        [NinjaScriptProperty]
        [Range(5, 60)]
        [Display(Name = "Minutos do OR", GroupName = "ORB", Order = 10)]
        public int MinutosOR { get; set; } = 30;

        [NinjaScriptProperty]
        [Range(0.5, 2.0)]
        [Display(Name = "Risco multiplicador (R)", GroupName = "ORB", Order = 11)]
        public double RiscoMultiplicador { get; set; } = 1.0;

        [NinjaScriptProperty]
        [Range(0.5, 5.0)]
        [Display(Name = "Alvo multiplicador (R)", GroupName = "ORB", Order = 12)]
        public double AlvoMultiplicador { get; set; } = 2.0;

        [NinjaScriptProperty]
        [Range(0, 120)]
        [Display(Name = "Cooldown (min)", GroupName = "ORB", Order = 13)]
        public int CooldownMinutos { get; set; } = 15;

        [NinjaScriptProperty]
        [Display(Name = "Sessao inicio UTC HH:mm", GroupName = "ORB", Order = 14)]
        public string SessaoInicioUtc { get; set; } = "13:30";

        [NinjaScriptProperty]
        [Display(Name = "Sessao fim UTC HH:mm", GroupName = "ORB", Order = 15)]
        public string SessaoFimUtc { get; set; } = "20:00";

        [NinjaScriptProperty]
        [Display(Name = "Hora corte entradas UTC HH:mm", GroupName = "ORB", Order = 16)]
        public string HoraCorteEntradasUtc { get; set; } = "19:00";

        [NinjaScriptProperty]
        [Range(0.01, 100.0)]
        [Display(Name = "Range minimo (pontos)", GroupName = "ORB", Order = 17)]
        public double RangeMinimoPontos { get; set; } = 0.5;

        [NinjaScriptProperty]
        [Range(5, 240)]
        [Display(Name = "Spread filter warmup (min)", GroupName = "Spread Filter", Order = 20)]
        public int SpreadFilterWarmup { get; set; } = 30;

        [NinjaScriptProperty]
        [Range(50, 5000)]
        [Display(Name = "CB semanal (USD)", GroupName = "Risco CAOS", Order = 21)]
        public double CircuitBreakerSemanalUSD { get; set; } = 1500;

        [NinjaScriptProperty]
        [Range(50, 5000)]
        [Display(Name = "CB janela (USD)", GroupName = "Risco CAOS", Order = 22)]
        public double CircuitBreakerJanelaUSD { get; set; } = 2000;

        // ------------------------------------------------------------------
        // Estado interno
        // ------------------------------------------------------------------

        private EstadoORB _estadoORB;
        private ParametrosORB _parametrosORB;
        private EstadoCrabelNR7 _estadoCrabel;
        private EstadoSpreadFilter _estadoSpread;
        private CircuitBreakerEstendido _cbExtendido;

        private double _entradaPrecoUltimoTrade;
        private string _sinalUltimoTrade;
        private bool _temPosicaoAberta;

        // ------------------------------------------------------------------
        // Ciclo de vida
        // ------------------------------------------------------------------

        protected override void OnStateChange()
        {
            base.OnStateChange();

            if (State == State.SetDefaults)
            {
                Description = "ORB + Crabel NR7 + Spread Filter + Circuit Breaker (Decisao 2026-05-25-02).";
                Name = "StrategyORBCrabelSpreadFilter";
            }
            else if (State == State.DataLoaded)
            {
                _estadoORB = new EstadoORB();
                _parametrosORB = MontarParametrosORB();
                _parametrosORB.Validar();
                _estadoCrabel = new EstadoCrabelNR7();
                _estadoSpread = new EstadoSpreadFilter();
                _cbExtendido = new CircuitBreakerEstendido(
                    limiteDiarioUSD: CircuitBreakerDiarioUSD,
                    limiteSemanalUSD: CircuitBreakerSemanalUSD,
                    limiteJanelaUSD: CircuitBreakerJanelaUSD);
                _temPosicaoAberta = false;
            }
        }

        protected override void OnNovaBarra()
        {
            // 1. Atualiza filtro NR7 com a barra recebida.
            DateTime tsUtc = Time[0].ToUniversalTime();
            EstrategiaCrabelLogica.AtualizarFiltro(_estadoCrabel, tsUtc, High[0], Low[0]);

            // 2. Atualiza spread filter — em tempo real, calcula spread
            //    da cotacao atual via APIs autorizadas (whitelist).
            //    Observacao: GetCurrentAsk/Bid retornam o ask/bid mais
            //    recente; em Historical, podem nao estar disponiveis.
            //    Se forem zero/NaN, pulamos.
            double ask = GetCurrentAsk();
            double bid = GetCurrentBid();
            double spread = (ask > 0 && bid > 0) ? (ask - bid) : -1.0;
            if (spread > 0)
            {
                SpreadFilterLogica.AdicionarObservacao(_estadoSpread, tsUtc, spread);
            }

            // 3. Camadas de filtro ANTES de delegar a ORBLogica.

            // 3a. Circuit breaker (multi-periodo).
            if (_cbExtendido.BloqueadoAgora)
            {
                // Bloqueado — nao opera.
                return;
            }

            // 3b. Crabel: dia atual deve ser elegivel.
            DateTime diaAtual = tsUtc.Date;
            if (!EstrategiaCrabelLogica.DiaEhElegivel(_estadoCrabel, diaAtual))
            {
                // Dia nao apos NR7 — pula.
                return;
            }

            // 3c. Spread Filter: minuto atual deve passar a running median.
            if (spread > 0 && !SpreadFilterLogica.MinutoPermitido(_estadoSpread, spread, SpreadFilterWarmup))
            {
                return;
            }

            // 4. Delegando para a logica ORB pura.
            BarraORB barra = new BarraORB();
            barra.Timestamp = tsUtc;
            barra.Open = Open[0];
            barra.High = High[0];
            barra.Low = Low[0];
            barra.Close = Close[0];
            barra.Volume = Volume[0];

            DecisaoORB decisao = EstrategiaORBLogica.DecidirAcao(
                barra, _estadoORB, _parametrosORB);

            switch (decisao.Acao)
            {
                case AcaoORB.LONG:
                    if (decisao.Stop.HasValue && decisao.Alvo.HasValue
                        && EntrarLong(MaxContratos, decisao.Stop.Value, decisao.Alvo.Value, "ORBCSF_LONG"))
                    {
                        _entradaPrecoUltimoTrade = barra.Close;
                        _sinalUltimoTrade = "ORBCSF_LONG";
                        _temPosicaoAberta = true;
                        EstrategiaORBLogica.RegistrarAberturaDePosicao(_estadoORB, decisao);
                    }
                    break;

                case AcaoORB.SHORT:
                    if (decisao.Stop.HasValue && decisao.Alvo.HasValue
                        && EntrarShort(MaxContratos, decisao.Stop.Value, decisao.Alvo.Value, "ORBCSF_SHORT"))
                    {
                        _entradaPrecoUltimoTrade = barra.Close;
                        _sinalUltimoTrade = "ORBCSF_SHORT";
                        _temPosicaoAberta = true;
                        EstrategiaORBLogica.RegistrarAberturaDePosicao(_estadoORB, decisao);
                    }
                    break;

                case AcaoORB.FECHAR:
                    if (Position.MarketPosition == MarketPosition.Long)
                        SairLong("ORBCSF_LONG");
                    else if (Position.MarketPosition == MarketPosition.Short)
                        SairShort("ORBCSF_SHORT");
                    EstrategiaORBLogica.RegistrarFechamentoDePosicao(
                        _estadoORB, barra.Timestamp, _parametrosORB);
                    break;

                case AcaoORB.NADA:
                default:
                    break;
            }
        }

        protected override void OnExecutionUpdate(
            Execution execution,
            string executionId,
            double price,
            int quantity,
            MarketPosition marketPosition,
            string orderId,
            DateTime time)
        {
            base.OnExecutionUpdate(execution, executionId, price, quantity, marketPosition, orderId, time);

            // Quando posicao volta a Flat, calcula PnL realizado e registra
            // no Circuit Breaker estendido.
            if (Position.MarketPosition == MarketPosition.Flat && _temPosicaoAberta)
            {
                double pnlPontos = (price - _entradaPrecoUltimoTrade);
                if (_sinalUltimoTrade != null && _sinalUltimoTrade.Contains("SHORT"))
                    pnlPontos = -pnlPontos;
                // MNQ: USD 2 por ponto.
                double pnlUSD = pnlPontos * quantity * 2.0;
                _cbExtendido.RegistrarPnlRealizado(pnlUSD);
                _temPosicaoAberta = false;

                if (_estadoORB != null && _estadoORB.Posicao != PosicaoORB.NADA)
                    EstrategiaORBLogica.RegistrarFechamentoDePosicao(
                        _estadoORB, time.ToUniversalTime(), _parametrosORB);

                Print(string.Format(
                    "[CAOS] Trade fechado: PnL={0:F2} USD | CB diario={1:F2} | semanal={2:F2} | janela={3:F2} | bloq={4}",
                    pnlUSD,
                    _cbExtendido.PnlDiarioUSD,
                    _cbExtendido.PnlSemanalUSD,
                    _cbExtendido.PnlJanelaUSD,
                    _cbExtendido.BloqueadoAgora ? _cbExtendido.MotivoBloqueio() : "no"));
            }
        }

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------

        private ParametrosORB MontarParametrosORB()
        {
            ParametrosORB p = new ParametrosORB();
            p.MinutosOR = MinutosOR;
            p.RiscoMultiplicador = RiscoMultiplicador;
            p.AlvoMultiplicador = AlvoMultiplicador;
            p.CooldownMinutos = CooldownMinutos;
            p.SessaoInicioUtc = ParseHora(SessaoInicioUtc);
            p.SessaoFimUtc = ParseHora(SessaoFimUtc);
            p.HoraCorteEntradasUtc = ParseHora(HoraCorteEntradasUtc);
            p.RangeMinimoPontos = RangeMinimoPontos;
            return p;
        }

        private static TimeSpan ParseHora(string hhmm)
        {
            if (string.IsNullOrWhiteSpace(hhmm))
                throw new ArgumentException("formato HH:mm exigido");
            string[] partes = hhmm.Trim().Split(':');
            if (partes.Length != 2)
                throw new ArgumentException("formato HH:mm exigido (ex: 13:30)");
            return new TimeSpan(int.Parse(partes[0]), int.Parse(partes[1]), 0);
        }
    }
}
