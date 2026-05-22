// StrategyORB.cs — estratégia Opening Range Breakout sobre MNQ (Spec 4 — Task 8).
//
// Subclasse de Strategy_CAOS (Spec 3) que delega TODA a regra de
// decisão para EstrategiaORBLogica.DecidirAcao (função pura espelhada
// em Python via caos.estrategias_modelo.orb).
//
// Procedimento operacional:
// 1. Copiar os 5 arquivos do núcleo (Strategy.cs, Cerberus.cs,
//    TrailingTresFases.cs, MfeMaeTracker.cs, Logger.cs) +
//    EstrategiaORBLogica.cs + StrategyORB.cs para
//    %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\
// 2. Abrir o NinjaScript Editor (Tools → Edit NinjaScript → Strategy).
// 3. Pressionar F5 para compilar.
// 4. No NT8: Strategies → New Strategy → "StrategyORB" → habilitar em chart MNQ.
//
// Os parâmetros [NinjaScriptProperty] aparecem no painel de Strategies
// para configuração sem recompilar.

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
    /// Opening Range Breakout sobre MNQ. Subclasse de
    /// <see cref="Strategy_CAOS"/>: roteamento de ordens via Cerberus,
    /// trailing 3-fases, MFE/MAE auto-instrumentado, logs em
    /// <c>05_BACKTEST/logs/</c>.
    /// </summary>
    public class StrategyORB : Strategy_CAOS
    {
        // ------------------------------------------------------------------
        // Parâmetros [NinjaScriptProperty] — paridade com ParametrosORB Python
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
        [Display(Name = "Sessão início UTC HH:mm", GroupName = "ORB", Order = 14)]
        public string SessaoInicioUtc { get; set; } = "13:30";

        [NinjaScriptProperty]
        [Display(Name = "Sessão fim UTC HH:mm", GroupName = "ORB", Order = 15)]
        public string SessaoFimUtc { get; set; } = "20:00";

        [NinjaScriptProperty]
        [Display(Name = "Hora corte entradas UTC HH:mm", GroupName = "ORB", Order = 16)]
        public string HoraCorteEntradasUtc { get; set; } = "19:00";

        [NinjaScriptProperty]
        [Range(0.01, 100.0)]
        [Display(Name = "Range mínimo (pontos)", GroupName = "ORB", Order = 17)]
        public double RangeMinimoPontos { get; set; } = 0.5;

        // ------------------------------------------------------------------
        // Estado interno
        // ------------------------------------------------------------------

        private EstadoORB _estado;
        private ParametrosORB _parametrosCache;

        // ------------------------------------------------------------------
        // Ciclo de vida
        // ------------------------------------------------------------------

        protected override void OnStateChange()
        {
            base.OnStateChange();

            if (State == State.SetDefaults)
            {
                Description = "Opening Range Breakout sobre MNQ — Spec 4 do CAOS.";
                Name = "StrategyORB";
            }
            else if (State == State.DataLoaded)
            {
                _estado = new EstadoORB();
                _parametrosCache = MontarParametros();
                _parametrosCache.Validar();
            }
        }

        protected override void OnNovaBarra()
        {
            // Constrói BarraORB a partir das séries do NT8.
            BarraORB barra = new BarraORB();
            barra.Timestamp = Time[0].ToUniversalTime();
            barra.Open = Open[0];
            barra.High = High[0];
            barra.Low = Low[0];
            barra.Close = Close[0];
            barra.Volume = Volume[0];

            DecisaoORB decisao = EstrategiaORBLogica.DecidirAcao(
                barra, _estado, _parametrosCache);

            switch (decisao.Acao)
            {
                case AcaoORB.LONG:
                    if (decisao.Stop.HasValue && decisao.Alvo.HasValue
                        && EntrarLong(MaxContratos, decisao.Stop.Value, decisao.Alvo.Value, "ORB_LONG"))
                    {
                        EstrategiaORBLogica.RegistrarAberturaDePosicao(_estado, decisao);
                    }
                    break;

                case AcaoORB.SHORT:
                    if (decisao.Stop.HasValue && decisao.Alvo.HasValue
                        && EntrarShort(MaxContratos, decisao.Stop.Value, decisao.Alvo.Value, "ORB_SHORT"))
                    {
                        EstrategiaORBLogica.RegistrarAberturaDePosicao(_estado, decisao);
                    }
                    break;

                case AcaoORB.FECHAR:
                    if (Position.MarketPosition == MarketPosition.Long)
                        SairLong("ORB_LONG");
                    else if (Position.MarketPosition == MarketPosition.Short)
                        SairShort("ORB_SHORT");
                    EstrategiaORBLogica.RegistrarFechamentoDePosicao(
                        _estado, barra.Timestamp, _parametrosCache);
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
            // Quando o NT8 fecha a posição (stop/alvo/saída discricionária),
            // sincronizamos o estado da ORB. A base (Strategy_CAOS) já
            // grava o trade no MfeMaeTracker; aqui apenas atualizamos o
            // Cerberus interno da ORB para liberar cooldown corretamente.
            base.OnExecutionUpdate(execution, executionId, price, quantity, marketPosition, orderId, time);
            if (Position.MarketPosition == MarketPosition.Flat
                && _estado != null
                && _estado.Posicao != PosicaoORB.NADA)
            {
                EstrategiaORBLogica.RegistrarFechamentoDePosicao(
                    _estado, time.ToUniversalTime(), _parametrosCache);
            }
        }

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------

        private ParametrosORB MontarParametros()
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
                throw new ArgumentException(
                    string.Format("formato HH:mm exigido; recebido {0}", hhmm));
            int h = int.Parse(partes[0]);
            int m = int.Parse(partes[1]);
            return new TimeSpan(h, m, 0);
        }
    }
}
