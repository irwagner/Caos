// EstrategiaVvgLateSessionLogica.cs — função pura DecidirAcao da estratégia
// VVG Late-Session Reversal (Spec — VVG Late-Session Reversal MNQ, Tarefa 6).
//
// Porta C# LITERAL de:
//   - caos/walk_forward/estrategias/vvg_logica.py (Tarefa 2 — função pura
//     canônica decidir_acao).
//   - caos/estrategias_modelo/vvg.py (Tarefa 5 — VvgModeloCSharpPort, o
//     "ground truth" da porta). O método _decidir_acao de vvg.py é a
//     referência reproduzida aqui LINHA A LINHA em DecidirAcao.
//
// A Property 11 (Tarefa 9) compara a porta Python de produção com a porta
// de referência vvg.py. Como o C# DEVE ser idêntico a vvg.py, qualquer
// divergência nesta DecidirAcao quebra a paridade Python↔C#.
//
// Decisão arquitetural-chave (mesmo padrão de EstrategiaORBLogica.cs):
// estruturas e método PUROS, sem dependência do runtime do NinjaTrader 8.
// Usa apenas tipos .NET (DateTime, TimeZoneInfo, TimeSpan, struct, enum) —
// nenhuma API NT8 (EnterLong, Bars, Close[], ...) é referenciada, logo a
// whitelist ninjascript-api.md NÃO precisa de novas entradas.
//
// O motor de execução stop/target (intrabar) NÃO vive aqui: no NT8 ele é o
// próprio runtime (SetStopLoss/SetProfitTarget + EnterLong/EnterShort),
// acionado por StrategyVvgLateSessionReversal (Tarefa 10) a partir dos
// valores congelados ParametrosVvg.StopPontos / ParametrosVvg.TargetPontos
// declarados neste arquivo. A simulação stop/target de vvg.py existe só
// para o property test reproduzir o que o NT8 faz em runtime.
//
// O caller (StrategyVvgLateSessionReversal.cs, subclasse de Strategy_CAOS)
// traduz as barras do NT8 (Time[0].ToUniversalTime(), Open[0], ..., Close[0])
// e despacha a AcaoVvg devolvida via EntrarLong/EntrarShort/SairLong/SairShort.

using System;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>
    /// Ações canônicas devolvidas por
    /// <see cref="EstrategiaVvgLateSessionLogica.DecidirAcao"/>. Espelha
    /// <c>AcaoVvg</c> (vvg_logica.py) / <c>AcaoVvgModelo</c> (vvg.py).
    /// </summary>
    public enum AcaoVvg
    {
        Long,
        Short,
        Fechar,
        Nada
    }

    /// <summary>
    /// Parâmetros congelados da estratégia (R10 — regra anti-overfit).
    /// Espelha <c>ParametrosVvgModelo</c> de vvg.py e <c>ParametrosVvg</c> de
    /// vvg_logica.py. Os 5 valores numéricos foram CONGELADOS pela calibração
    /// da Tarefa 1 (Calibracao_VVG_2026-05-29.md) — alterá-los exige Decisão
    /// formal, nunca recalibração silenciosa.
    ///
    /// Horas de sessão em horário de Nova York (sufixo Est); a conversão
    /// UTC→NY é feita dentro de DecidirAcao.
    ///
    /// Observação sobre struct: como structs C# não admitem inicializadores
    /// de campo, os valores são definidos em <see cref="PadraoConfigurado"/>.
    /// O valor default <c>new ParametrosVvg()</c> (tudo zerado) NÃO é válido
    /// para operação — sempre construa via PadraoConfigurado().
    /// </summary>
    public struct ParametrosVvg
    {
        // --- Classificador VVG (consumidos pelo classificador; aqui só portados) ---
        public double MultiplicadorVolume;
        public double ThresholdGapPct;
        public int NDiasBaseline;

        // --- Stop / target congelados (ATR(14) 24h mediano × 1.0 e × 2.0) ---
        public double StopPontos;
        public double TargetPontos;

        // --- Janela morning (baseline E volume na MESMA janela de 30 min, NY) ---
        public TimeSpan JanelaMorningInicioEst;
        public TimeSpan JanelaMorningFimEst;

        // --- Horários da estratégia (NY) ---
        public TimeSpan HoraEntradaEst;       // mede o drift e entra
        public TimeSpan HoraEncerramentoEst;  // force-close (EOD Topstep)

        // --- Sessão RTH (NY) ---
        public TimeSpan SessaoInicioEst;
        public TimeSpan SessaoFimEst;

        /// <summary>
        /// Devolve a instância com os valores CONGELADOS da calibração
        /// (espelho de ParametrosVvg.PadraoConfigurado() do Python). Os
        /// valores são atribuídos explicitamente para deixar a origem de
        /// cada constante auditável neste único ponto.
        /// Origem: Calibracao_VVG_2026-05-29.md (Tarefa 1).
        /// </summary>
        public static ParametrosVvg PadraoConfigurado()
        {
            ParametrosVvg p = new ParametrosVvg();
            p.MultiplicadorVolume = 1.5;     // calibração 2026-05-29 (sweep 16.7%)
            p.ThresholdGapPct = 0.0015;      // calibração 2026-05-29 (sweep 16.7%)
            p.NDiasBaseline = 10;            // prescrito (design.md / R1.1)
            p.StopPontos = 472.25;           // 472.18 × 1.0, arred. tick MNQ (0.25)
            p.TargetPontos = 944.25;         // 472.18 × 2.0, arred. tick MNQ (0.25)
            p.JanelaMorningInicioEst = new TimeSpan(9, 30, 0);
            p.JanelaMorningFimEst = new TimeSpan(10, 0, 0);
            p.HoraEntradaEst = new TimeSpan(14, 30, 0);
            p.HoraEncerramentoEst = new TimeSpan(15, 50, 0);
            p.SessaoInicioEst = new TimeSpan(9, 30, 0);
            p.SessaoFimEst = new TimeSpan(16, 0, 0);
            return p;
        }
    }

    /// <summary>
    /// Estado mutável da decisão ao longo da sessão. Espelha
    /// <c>_EstadoVvgModelo</c> de vvg.py e <c>EstadoVvg</c> de vvg_logica.py.
    /// Passado por <c>ref</c> a DecidirAcao, que o muta in-place (estilo C#) —
    /// equivalente à mutação in-place de self._estado em vvg.py.
    ///
    /// O valor default <c>new EstadoVvg()</c> reproduz exatamente os defaults
    /// do Python: campos anuláveis (DateTime?/double?/string) começam nulos e
    /// os bool começam false.
    /// </summary>
    public struct EstadoVvg
    {
        // --- Estado de classificação (diário) ---
        public DateTime? DiaCorrente;          // data NY; mudança dispara o reset diário
        public double? OpenDiaAtual;           // open do RTH (~09:30 NY); base do drift
        public double? DriftCloseReferencia;   // close registrado na HoraEntradaEst
        public bool VvgPositivo;               // setado EXTERNAMENTE pelo classificador (Tarefa 7)

        // --- Estado da posição ---
        public bool PosicaoAberta;
        public string DirecaoAtual;            // "LONG" | "SHORT" | null
        public double? PrecoEntrada;
        public string SinalAtual;              // "vvg-rev-long" | "vvg-rev-short" | null
        public bool TradeFechadoHoje;          // R2.6 — garante no máximo 1 trade por dia
    }

    /// <summary>
    /// Função pura canônica da estratégia VVG Late-Session Reversal. Espelho
    /// fiel de <c>vvg.py._decidir_acao</c> (VvgModeloCSharpPort) e de
    /// <c>vvg_logica.decidir_acao</c>. Qualquer divergência futura entre
    /// Python e C# DEVE ser revertida no mesmo commit — a Property 11
    /// (paridade Python↔C#, Tarefa 9) falha imediatamente em qualquer
    /// divergência de comportamento.
    /// </summary>
    public static class EstrategiaVvgLateSessionLogica
    {
        // Fuso do RTH do MNQ. No Windows, "Eastern Standard Time" resolve
        // EST/EDT (horário de verão) automaticamente — equivalente ao
        // zoneinfo.ZoneInfo("America/New_York") usado no Python. Único ponto
        // de conversão UTC→NY.
        private static readonly TimeZoneInfo FusoNovaYork =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        /// <summary>
        /// Decide a ação VVG para a barra, mutando <paramref name="estado"/>
        /// in-place. Porta LINHA A LINHA de _decidir_acao (vvg.py).
        ///
        /// Fluxo (precedência cronológica dentro da barra):
        /// 1. Valida a barra e converte timestamp UTC → horário de Nova York.
        /// 2. Reset de estado diário quando muda a data NY.
        /// 3. Captura o OpenDiaAtual (open do RTH ~09:30 NY).
        /// 4. Posição aberta: hora >= HoraEncerramentoEst → Fechar; senão Nada.
        /// 5. Sem posição, exatamente em HoraEntradaEst, com VvgPositivo e sem
        ///    trade fechado hoje → drift = close − open; entrada OPOSTA ao
        ///    drift (drift > 0 → Short; senão Long).
        /// 6. Caso contrário → Nada.
        ///
        /// A flag VvgPositivo é CONSUMIDA (setada externamente pelo
        /// classificador às ~10:00 NY), nunca calculada aqui.
        /// </summary>
        public static AcaoVvg DecidirAcao(
            DateTime timestampUtc,
            double open,
            double high,
            double low,
            double close,
            ref EstadoVvg estado,
            ParametrosVvg p)
        {
            ValidarBarra(timestampUtc, open, high, low, close);

            // Conversão UTC→NY (DST automático), equivalente a _para_ny.
            DateTime tsNy = TimeZoneInfo.ConvertTimeFromUtc(timestampUtc, FusoNovaYork);
            DateTime dia = tsNy.Date;
            TimeSpan hora = tsNy.TimeOfDay;

            // Passo 2: reset de estado diário ao mudar a data NY.
            if (estado.DiaCorrente != dia)
            {
                estado.DiaCorrente = dia;
                estado.OpenDiaAtual = null;
                estado.DriftCloseReferencia = null;
                estado.TradeFechadoHoje = false;
                // Zera a flag: nunca operar sob valor obsoleto de D-1. O
                // classificador reescreve o valor correto às 10:00 NY, antes
                // da entrada (14:30 NY).
                estado.VvgPositivo = false;
            }

            // Passo 3: captura do open de referência do RTH (~09:30 NY).
            // Robusto a barras de Globex (pré-mercado): só capturamos quando a
            // barra já está dentro da sessão RTH.
            if (estado.OpenDiaAtual == null
                && p.SessaoInicioEst <= hora && hora < p.SessaoFimEst)
            {
                estado.OpenDiaAtual = open;
            }

            // Passo 4: posição aberta → só decidimos o force-close de fim de sessão.
            if (estado.PosicaoAberta)
            {
                if (hora >= p.HoraEncerramentoEst)
                {
                    estado.PosicaoAberta = false;
                    estado.DirecaoAtual = null;
                    estado.PrecoEntrada = null;
                    estado.SinalAtual = null;
                    estado.TradeFechadoHoje = true;
                    return AcaoVvg.Fechar;
                }
                return AcaoVvg.Nada;
            }

            // Passo 5: avaliação de entrada — somente na barra exata de HoraEntradaEst.
            if (hora == p.HoraEntradaEst
                && estado.VvgPositivo
                && !estado.TradeFechadoHoje
                && estado.OpenDiaAtual != null)
            {
                // Drift = close(HoraEntrada) - open(09:30). Entrada OPOSTA ao drift.
                estado.DriftCloseReferencia = close;
                double drift = estado.DriftCloseReferencia.Value - estado.OpenDiaAtual.Value;
                string direcao = drift > 0 ? "SHORT" : "LONG";

                estado.PosicaoAberta = true;
                estado.DirecaoAtual = direcao;
                estado.PrecoEntrada = close;
                estado.SinalAtual = SinalDe(direcao);
                return direcao == "SHORT" ? AcaoVvg.Short : AcaoVvg.Long;
            }

            // Passo 6: nada a fazer.
            return AcaoVvg.Nada;
        }

        /// <summary>
        /// Registra fechamento por stop/target detectado pelo motor de
        /// execução do NT8. DecidirAcao só emite Fechar no fim de sessão;
        /// quando o stop ou o target é atingido intrabar, quem observa o fill
        /// é o runtime. Espelha _registrar_saida_externa (vvg.py) /
        /// registrar_saida_externa (vvg_logica.py): zera a posição e marca
        /// TradeFechadoHoje (R2.6 — 1 trade/dia), mantendo a coerência sem
        /// violar a pureza de DecidirAcao.
        /// </summary>
        public static void RegistrarSaidaExterna(ref EstadoVvg estado)
        {
            estado.PosicaoAberta = false;
            estado.DirecaoAtual = null;
            estado.PrecoEntrada = null;
            estado.SinalAtual = null;
            estado.TradeFechadoHoje = true;
        }

        // ------------------------------------------------------------------
        // Helpers internos
        // ------------------------------------------------------------------

        /// <summary>Mapeia direção → tag de sinal canônica (espelho de _sinal_de).</summary>
        private static string SinalDe(string direcao)
        {
            return direcao == "LONG" ? "vvg-rev-long" : "vvg-rev-short";
        }

        /// <summary>
        /// Validação estrita da barra (espelha _validar_barra_decisao). Exige
        /// timestamp em UTC e OHLC finitos. O volume não participa da decisão,
        /// logo não é recebido nem validado aqui.
        /// </summary>
        private static void ValidarBarra(
            DateTime timestampUtc, double open, double high, double low, double close)
        {
            if (timestampUtc.Kind != DateTimeKind.Utc)
                throw new ArgumentException("timestampUtc deve estar em UTC (DateTimeKind.Utc)");
            if (double.IsNaN(open) || double.IsInfinity(open))
                throw new ArgumentException("open deve ser float finito");
            if (double.IsNaN(high) || double.IsInfinity(high))
                throw new ArgumentException("high deve ser float finito");
            if (double.IsNaN(low) || double.IsInfinity(low))
                throw new ArgumentException("low deve ser float finito");
            if (double.IsNaN(close) || double.IsInfinity(close))
                throw new ArgumentException("close deve ser float finito");
        }
    }
}
