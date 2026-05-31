// StrategyVvgLateSessionReversal.cs — estratégia VVG Late-Session Reversal
// sobre MNQ (Spec — VVG Late-Session Reversal MNQ, Tarefa 10).
//
// Subclasse de Strategy_CAOS (Spec 3) que delega TODA a regra de decisão
// para a função pura EstrategiaVvgLateSessionLogica.DecidirAcao (Tarefa 6)
// e a classificação de regime para EstrategiaVvgClassifierLogica (Tarefa 7).
// Ambas as portas C# são traduções literais das portas Python de referência
// (vvg_logica.py / vvg_classifier.py via caos.estrategias_modelo.vvg) e NÃO
// dependem de nenhum símbolo NT8 — vivem no namespace
// NinjaTrader.NinjaScript.Strategies.CAOS. Esta classe é o ÚNICO adaptador
// fino que conecta as barras OHLCV do runtime NT8 a essas portas puras.
//
// Procedimento operacional (idêntico ao da StrategyORB):
// 1. Copiar os arquivos do núcleo (Strategy.cs, Cerberus.cs,
//    TrailingTresFases.cs, MfeMaeTracker.cs, Logger.cs) +
//    EstrategiaVvgLateSessionLogica.cs + EstrategiaVvgClassifierLogica.cs +
//    StrategyVvgLateSessionReversal.cs para
//    %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\caos\
//    (sincronização tratada pela Tarefa 12 — NÃO faz parte deste arquivo).
// 2. Abrir o NinjaScript Editor (Tools → Edit NinjaScript → Strategy).
// 3. Pressionar F5 para compilar.
// 4. No NT8: Strategies → New Strategy → "StrategyVvgLateSessionReversal" →
//    habilitar em chart MNQ (Days to load >= 44 — warmup do
//    BarsRequiredToTrade=19320 herdado da base).
//
// Defesas reutilizadas SEM modificação (R5.3): toda a maquinaria de warmup,
// roteamento Cerberus, trailing 3-fases, MFE/MAE e supressão de popups
// "Sell StopMarket acima do mercado" já vive em Strategy_CAOS. Esta classe
// NÃO re-declara BarsRequiredToTrade, NÃO chama EnterLong/EnterShort direto
// e usa SOMENTE os wrappers EntrarLong/EntrarShort/SairLong/SairShort.

#region Using declarations
using System;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies.CAOS;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    /// <summary>
    /// VVG Late-Session Reversal sobre MNQ (Decisão 2026-05-29-03).
    /// Subclasse de <see cref="Strategy_CAOS"/>: roteamento de ordens via
    /// Cerberus, trailing 3-fases, MFE/MAE auto-instrumentado e logs em
    /// <c>05_BACKTEST/logs/</c> são herdados sem alteração.
    ///
    /// A estratégia opera UM único trade contra o drift direcional do dia
    /// em dias VVG-positivos, entrando às 14:30 NY e encerrando às 15:50 NY
    /// (EOD seguro da Topstep). Todos os parâmetros são CONGELADOS em
    /// <see cref="ParametrosVvg.PadraoConfigurado"/> (R10 — anti-overfit);
    /// esta classe não expõe nenhum <c>[NinjaScriptProperty]</c> próprio.
    /// </summary>
    public class StrategyVvgLateSessionReversal : Strategy_CAOS
    {
        // ------------------------------------------------------------------
        // Estado interno (instanciado em State.DataLoaded)
        // ------------------------------------------------------------------

        // Classificador VVG stateful (Tarefa 7). Consome barras de minuto e
        // devolve um ResultadoClassificacao quando a janela morning fecha.
        private EstrategiaVvgClassifierLogica _classifier;

        // Estado mutável da decisão ao longo da sessão (Tarefa 6). Passado
        // por ref a DecidirAcao, que o muta in-place. EstadoVvg é struct —
        // o default (new EstadoVvg()) reproduz os defaults da porta Python.
        private EstadoVvg _estado;

        // Parâmetros congelados da calibração (Tarefa 1). Cacheados uma vez
        // para evitar reconstruir a struct a cada barra e manter a origem
        // dos literais auditável num único ponto (PadraoConfigurado()).
        private ParametrosVvg _params;

        // ------------------------------------------------------------------
        // Ciclo de vida
        // ------------------------------------------------------------------

        protected override void OnStateChange()
        {
            // base SEMPRE primeiro: a base configura BarsRequiredToTrade,
            // Calculate, RealtimeErrorHandling, StopTargetHandling e demais
            // defesas de warmup. NÃO mexer nelas aqui (R5.3).
            base.OnStateChange();

            if (State == State.SetDefaults)
            {
                Name = "StrategyVvgLateSessionReversal";
                Description = "VVG Late-Session Reversal sobre MNQ (Decisao 2026-05-29-03).";
                // R4.1 — fixo permanente. Reusa o [NinjaScriptProperty]
                // MaxContratos já declarado na base Strategy_CAOS; apenas
                // ajusta o default desta estratégia para 1 contrato.
                MaxContratos = 1;
            }
            else if (State == State.DataLoaded)
            {
                _params = ParametrosVvg.PadraoConfigurado();
                _classifier = new EstrategiaVvgClassifierLogica(_params);
                _estado = new EstadoVvg();
            }
        }

        // ------------------------------------------------------------------
        // Hook da base — chamado em toda barra da série primária
        // ------------------------------------------------------------------

        protected override void OnNovaBarra()
        {
            // Converte a barra atual do NT8 para o contrato OHLCV puro das
            // portas. Time[0].ToUniversalTime() devolve DateTime com
            // Kind=Utc, exigido por DecidirAcao (ValidarBarra) e tratado de
            // forma leniente pelo classificador.
            DateTime tsUtc = Time[0].ToUniversalTime();

            // 1. Atualiza o classificador VVG. Devolve não-null apenas na
            //    barra em que a janela morning fecha (~10:00 NY); nas demais
            //    devolve null. Quando vier resultado, alimenta a flag que
            //    DecidirAcao consome às 14:30 NY.
            ResultadoClassificacao resultado = _classifier.OnBarra(
                tsUtc, Open[0], High[0], Low[0], Close[0], Volume[0]);
            if (resultado != null)
            {
                _estado.VvgPositivo = resultado.VvgPositivo;
            }

            // 2. Decide a ação via função pura portada (muta _estado por ref).
            AcaoVvg acao = EstrategiaVvgLateSessionLogica.DecidirAcao(
                tsUtc, Open[0], High[0], Low[0], Close[0], ref _estado, _params);

            // 3. Despacha SOMENTE via wrappers de Strategy_CAOS (nunca
            //    EnterLong/EnterShort direto). Stop/target são declarados
            //    pela base ANTES da ordem (R5.3), a partir dos pontos
            //    congelados em _params.
            switch (acao)
            {
                case AcaoVvg.Long:
                    EntrarLong(
                        MaxContratos,
                        Close[0] - _params.StopPontos,
                        Close[0] + _params.TargetPontos,
                        "vvg-rev-long");
                    break;

                case AcaoVvg.Short:
                    EntrarShort(
                        MaxContratos,
                        Close[0] + _params.StopPontos,
                        Close[0] - _params.TargetPontos,
                        "vvg-rev-short");
                    break;

                case AcaoVvg.Fechar:
                    // Force-close de fim de sessão (15:50 NY). Os wrappers
                    // já são no-op se a posição NT8 não estiver na direção
                    // esperada (ex.: stop/target já fechou intrabar).
                    if (Position.MarketPosition == MarketPosition.Long)
                        SairLong("vvg-rev-long");
                    else if (Position.MarketPosition == MarketPosition.Short)
                        SairShort("vvg-rev-short");
                    break;

                case AcaoVvg.Nada:
                default:
                    break;
            }
        }
    }
}
