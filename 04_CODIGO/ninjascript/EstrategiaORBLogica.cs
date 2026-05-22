// EstrategiaORBLogica.cs — função pura DecidirAcao da estratégia ORB (Spec 4 — Task 4).
//
// Porta C# direta de
// CAOS_Orchestrator/caos/walk_forward/estrategias/orb_logica.py.
// Cobre R1, R2, R3, R4, R5 do requirements.md do Spec 4.
//
// Decisão arquitetural-chave: classe pura, sem dependências do runtime
// do NinjaScript. Permite reimplementação byte-a-byte em
// caos.estrategias_modelo.orb (Spec 4 — Task 3) para validação
// automatizada via Property 19 (paridade Python ↔ C#).
//
// O caller (StrategyORB.cs, subclasse de Strategy_CAOS) é responsável
// por traduzir as barras do NT8 (Time[0], Open[0], ..., Close[0]) em
// BarraORB e despachar a AcaoORB devolvida via EntrarLong/EntrarShort/
// SairLong/SairShort.

using System;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>Ações canônicas devolvidas por <see cref="EstrategiaORBLogica.DecidirAcao"/>.</summary>
    public enum AcaoORB
    {
        NADA,
        LONG,
        SHORT,
        FECHAR
    }

    /// <summary>Posição corrente rastreada por <see cref="EstadoORB"/>.</summary>
    public enum PosicaoORB
    {
        NADA,
        LONG,
        SHORT
    }

    /// <summary>Barra OHLCV minimalista (input da função pura).</summary>
    public class BarraORB
    {
        public DateTime Timestamp;   // UTC
        public double Open;
        public double High;
        public double Low;
        public double Close;
        public double Volume;
    }

    /// <summary>Parâmetros configuráveis (R5 — defaults canônicos).</summary>
    public class ParametrosORB
    {
        public int MinutosOR = 30;
        public double RiscoMultiplicador = 1.0;
        public double AlvoMultiplicador = 2.0;
        public int CooldownMinutos = 15;
        // Horários como TimeSpan a partir da meia-noite UTC.
        public TimeSpan HoraCorteEntradasUtc = new TimeSpan(19, 0, 0);
        public TimeSpan SessaoInicioUtc = new TimeSpan(13, 30, 0);
        public TimeSpan SessaoFimUtc = new TimeSpan(20, 0, 0);
        public double RangeMinimoPontos = 0.5;

        /// <summary>Valida ranges de R5; lança <see cref="ArgumentOutOfRangeException"/> em violação.</summary>
        public void Validar()
        {
            if (MinutosOR < 5 || MinutosOR > 60)
                throw new ArgumentOutOfRangeException("MinutosOR", "deve estar em [5, 60]");
            if (RiscoMultiplicador < 0.5 || RiscoMultiplicador > 2.0)
                throw new ArgumentOutOfRangeException("RiscoMultiplicador", "deve estar em [0.5, 2.0]");
            if (AlvoMultiplicador < 0.5 || AlvoMultiplicador > 5.0)
                throw new ArgumentOutOfRangeException("AlvoMultiplicador", "deve estar em [0.5, 5.0]");
            if (CooldownMinutos < 0 || CooldownMinutos > 120)
                throw new ArgumentOutOfRangeException("CooldownMinutos", "deve estar em [0, 120]");
            if (RangeMinimoPontos <= 0)
                throw new ArgumentOutOfRangeException("RangeMinimoPontos", "deve ser > 0");
            if (SessaoInicioUtc >= SessaoFimUtc)
                throw new ArgumentException("SessaoInicioUtc deve ser anterior a SessaoFimUtc");
            if (HoraCorteEntradasUtc < SessaoInicioUtc || HoraCorteEntradasUtc > SessaoFimUtc)
                throw new ArgumentException("HoraCorteEntradasUtc deve estar dentro da janela de sessão");
        }
    }

    /// <summary>Estado mutável da ORB ao longo da sessão.</summary>
    public class EstadoORB
    {
        public DateTime SessaoCorrente = DateTime.MinValue;
        public double HighOR = double.NegativeInfinity;
        public double LowOR = double.PositiveInfinity;
        public bool OrFormado = false;
        public PosicaoORB Posicao = PosicaoORB.NADA;
        public DateTime? CooldownAte = null;
        public bool EntrouNestaSessao = false;
    }

    /// <summary>Decisão devolvida por <see cref="EstrategiaORBLogica.DecidirAcao"/>.</summary>
    public class DecisaoORB
    {
        public AcaoORB Acao;
        public double? Stop;
        public double? Alvo;
        public string Motivo = string.Empty;
    }

    /// <summary>
    /// Função pura canônica da estratégia ORB. Espelho fiel de
    /// <c>caos.walk_forward.estrategias.orb_logica.decidir_acao</c>.
    /// Qualquer divergência futura entre Python e C# DEVE ser revertida
    /// no mesmo commit ou registrada como veto técnico — Property 19 do
    /// Spec 4 falha imediatamente em qualquer divergência de
    /// comportamento.
    /// </summary>
    public static class EstrategiaORBLogica
    {
        public static DecisaoORB DecidirAcao(
            BarraORB barra,
            EstadoORB estado,
            ParametrosORB parametros)
        {
            ValidarBarra(barra);
            ResetarSeNovaSessao(estado, barra);

            // Passo 2: barra fora da Janela_Sessao_RTH.
            if (!EstaDentroDaSessao(barra, parametros))
                return Resultado(AcaoORB.NADA, "fora-da-sessao");

            // Passo 3: fim de sessão com posição aberta → fechar.
            DateTime sessaoFimDt = new DateTime(
                barra.Timestamp.Year, barra.Timestamp.Month, barra.Timestamp.Day,
                parametros.SessaoFimUtc.Hours,
                parametros.SessaoFimUtc.Minutes,
                parametros.SessaoFimUtc.Seconds,
                DateTimeKind.Utc);
            if (estado.Posicao != PosicaoORB.NADA &&
                barra.Timestamp >= sessaoFimDt - TimeSpan.FromMinutes(1))
                return Resultado(AcaoORB.FECHAR, "fim-de-sessao");

            // Passo 4: barra dentro do Periodo_OR → atualiza range.
            if (EstaNoPeriodoOR(barra, parametros))
            {
                if (barra.High > estado.HighOR) estado.HighOR = barra.High;
                if (barra.Low < estado.LowOR) estado.LowOR = barra.Low;
                return Resultado(AcaoORB.NADA, "acumulando-or");
            }

            // Marca o OR como formado na primeira barra após o Periodo_OR.
            if (!estado.OrFormado)
            {
                if (double.IsNegativeInfinity(estado.HighOR) ||
                    double.IsPositiveInfinity(estado.LowOR))
                {
                    estado.OrFormado = true;
                    return Resultado(AcaoORB.NADA, "or-vazio");
                }
                estado.OrFormado = true;
            }

            // Passo 5: posição aberta → ORB não decide saídas além do fim de sessão.
            if (estado.Posicao != PosicaoORB.NADA)
                return Resultado(AcaoORB.NADA, "posicao-aberta");

            // Passo 6: cooldown ativo.
            if (estado.CooldownAte != null && barra.Timestamp < estado.CooldownAte.Value)
                return Resultado(AcaoORB.NADA, "cooldown");

            // Passo 7: já entrou nesta sessão (R2.3).
            if (estado.EntrouNestaSessao)
                return Resultado(AcaoORB.NADA, "ja-entrou-nesta-sessao");

            // Passo 8: hora de corte ultrapassada.
            if (barra.Timestamp.TimeOfDay > parametros.HoraCorteEntradasUtc)
                return Resultado(AcaoORB.NADA, "apos-hora-de-corte");

            // Passo 9: range degenerado.
            double rangePontos = estado.HighOR - estado.LowOR;
            if (rangePontos <= parametros.RangeMinimoPontos)
                return Resultado(AcaoORB.NADA, "range-degenerado");

            // Passos 10/11: rompimento.
            bool rompeuLong = barra.Close > estado.HighOR;
            bool rompeuShort = barra.Close < estado.LowOR;
            if (rompeuLong && rompeuShort)
            {
                if ((barra.Close - estado.HighOR) > (estado.LowOR - barra.Close))
                    rompeuShort = false;
                else
                    rompeuLong = false;
            }

            double riscoPontos = rangePontos * parametros.RiscoMultiplicador;
            if (rompeuLong)
            {
                double stop = estado.LowOR;
                double alvo = barra.Close + riscoPontos * parametros.AlvoMultiplicador;
                return Resultado(AcaoORB.LONG, "rompimento-long", stop, alvo);
            }
            if (rompeuShort)
            {
                double stop = estado.HighOR;
                double alvo = barra.Close - riscoPontos * parametros.AlvoMultiplicador;
                return Resultado(AcaoORB.SHORT, "rompimento-short", stop, alvo);
            }
            return Resultado(AcaoORB.NADA, "sem-rompimento");
        }

        // ------------------------------------------------------------------
        // Helpers de transição de posição (caller registra após despachar)
        // ------------------------------------------------------------------

        public static void RegistrarAberturaDePosicao(EstadoORB estado, DecisaoORB decisao)
        {
            if (decisao.Acao == AcaoORB.LONG)
            {
                estado.Posicao = PosicaoORB.LONG;
                estado.EntrouNestaSessao = true;
            }
            else if (decisao.Acao == AcaoORB.SHORT)
            {
                estado.Posicao = PosicaoORB.SHORT;
                estado.EntrouNestaSessao = true;
            }
        }

        public static void RegistrarFechamentoDePosicao(
            EstadoORB estado,
            DateTime timestampSaida,
            ParametrosORB parametros)
        {
            estado.Posicao = PosicaoORB.NADA;
            estado.CooldownAte = timestampSaida + TimeSpan.FromMinutes(parametros.CooldownMinutos);
        }

        // ------------------------------------------------------------------
        // Helpers internos
        // ------------------------------------------------------------------

        private static void ValidarBarra(BarraORB barra)
        {
            if (barra.Timestamp.Kind != DateTimeKind.Utc)
                throw new ArgumentException("barra.Timestamp deve estar em UTC (DateTimeKind.Utc)");
            if (double.IsNaN(barra.Open) || double.IsInfinity(barra.Open))
                throw new ArgumentException("barra.Open inválido");
            if (double.IsNaN(barra.High) || double.IsInfinity(barra.High))
                throw new ArgumentException("barra.High inválido");
            if (double.IsNaN(barra.Low) || double.IsInfinity(barra.Low))
                throw new ArgumentException("barra.Low inválido");
            if (double.IsNaN(barra.Close) || double.IsInfinity(barra.Close))
                throw new ArgumentException("barra.Close inválido");
            if (double.IsNaN(barra.Volume) || double.IsInfinity(barra.Volume))
                throw new ArgumentException("barra.Volume inválido");
        }

        private static bool EstaDentroDaSessao(BarraORB barra, ParametrosORB parametros)
        {
            TimeSpan hora = barra.Timestamp.TimeOfDay;
            return hora >= parametros.SessaoInicioUtc && hora < parametros.SessaoFimUtc;
        }

        private static bool EstaNoPeriodoOR(BarraORB barra, ParametrosORB parametros)
        {
            TimeSpan hora = barra.Timestamp.TimeOfDay;
            if (hora < parametros.SessaoInicioUtc) return false;
            DateTime inicio = new DateTime(
                barra.Timestamp.Year, barra.Timestamp.Month, barra.Timestamp.Day,
                parametros.SessaoInicioUtc.Hours,
                parametros.SessaoInicioUtc.Minutes,
                parametros.SessaoInicioUtc.Seconds,
                DateTimeKind.Utc);
            DateTime fimOR = inicio + TimeSpan.FromMinutes(parametros.MinutosOR);
            return barra.Timestamp < fimOR;
        }

        private static void ResetarSeNovaSessao(EstadoORB estado, BarraORB barra)
        {
            DateTime sessaoDaBarra = barra.Timestamp.Date;
            if (estado.SessaoCorrente != sessaoDaBarra)
            {
                estado.SessaoCorrente = sessaoDaBarra;
                estado.HighOR = double.NegativeInfinity;
                estado.LowOR = double.PositiveInfinity;
                estado.OrFormado = false;
                estado.EntrouNestaSessao = false;
                estado.CooldownAte = null;
            }
        }

        private static DecisaoORB Resultado(
            AcaoORB acao,
            string motivo,
            double? stop = null,
            double? alvo = null)
        {
            DecisaoORB d = new DecisaoORB();
            d.Acao = acao;
            d.Motivo = motivo;
            d.Stop = stop;
            d.Alvo = alvo;
            return d;
        }
    }
}
