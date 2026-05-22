// TrailingTresFases.cs — máquina de 3 fases de trailing stop (Spec 3 — Task 3).
//
// Cobre R4 do requirements.md:
// - R4.1: ao atingir entrada+0.5R, move stop para entrada (breakeven).
// - R4.2: ao atingir entrada+1R, move stop para entrada+0.3R.
// - R4.3: ao atingir entrada+2R, ativa trailing dinâmico a 0.5R do preço.
// - R4.5: stop nunca move contra a direção do trade (Property 17 — monotonia).
//
// Classe pura — sem dependência do runtime do NinjaScript. Permite
// reimplementação byte-a-byte em caos.ninjascript_modelo.trailing.
//
// As constantes 0.3R e 0.5R são fixadas pelo design 3 (Trailing_3_Fases).
// Os multiplicadores 0.5R/1.0R/2.0R que disparam as transições vêm do
// caller (parâmetros [NinjaScriptProperty] da Strategy_CAOS) — o construtor
// permite override para teste.

using System;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>Direção da posição rastreada pelo trailing.</summary>
    public enum DirecaoTrade
    {
        Long,
        Short
    }

    /// <summary>Estado da máquina de trailing.</summary>
    public enum FaseTrailing
    {
        SemPosicao,
        Entrada,
        Fase1Breakeven,
        Fase2Lock,
        Fase3Dinamico
    }

    /// <summary>
    /// Trailing stop em 3 fases. Mantém o stop monotonicamente a favor do
    /// trade (R4.5): para LONG, o stop só sobe; para SHORT, só desce.
    /// </summary>
    public class Trailing_3_Fases
    {
        // Multiplicadores de R que disparam as transições de fase.
        private readonly double fase1Mult;  // default 0.5 (R)
        private readonly double fase2Mult;  // default 1.0 (R)
        private readonly double fase3Mult;  // default 2.0 (R)

        // Constantes do design 3 (não configuráveis por enquanto).
        private const double Fase2StopOffsetR = 0.3;   // entrada + 0.3R em LONG
        private const double Fase3DistanciaR = 0.5;    // 0.5R atrás do preço

        private DirecaoTrade direcao;
        private double entradaPreco;
        private double stopInicial;
        private double riscoR;          // |entrada - stopInicial|, sempre positivo
        private double stopAtual;
        private FaseTrailing fase;

        public Trailing_3_Fases(double fase1Mult = 0.5, double fase2Mult = 1.0, double fase3Mult = 2.0)
        {
            if (fase1Mult < 0.0 || fase1Mult > 2.0)
                throw new ArgumentOutOfRangeException("fase1Mult", "fase1Mult deve estar em [0, 2]");
            if (fase2Mult < 0.0 || fase2Mult > 2.0)
                throw new ArgumentOutOfRangeException("fase2Mult", "fase2Mult deve estar em [0, 2]");
            if (fase3Mult < 0.0 || fase3Mult > 2.0)
                throw new ArgumentOutOfRangeException("fase3Mult", "fase3Mult deve estar em [0, 2]");
            // Os multiplicadores devem formar uma sequência crescente para a
            // máquina de 3 fases ter sentido (caso contrário fase2 e fase3
            // colapsariam em fase1).
            if (!(fase1Mult <= fase2Mult && fase2Mult <= fase3Mult))
                throw new ArgumentException(
                    "multiplicadores devem ser crescentes: fase1 <= fase2 <= fase3; recebidos "
                    + fase1Mult + ", " + fase2Mult + ", " + fase3Mult);

            this.fase1Mult = fase1Mult;
            this.fase2Mult = fase2Mult;
            this.fase3Mult = fase3Mult;
            this.fase = FaseTrailing.SemPosicao;
        }

        /// <summary>Fase corrente da máquina.</summary>
        public FaseTrailing Fase { get { return fase; } }

        /// <summary>Stop atual (válido apenas quando <see cref="Fase"/> != SemPosicao).</summary>
        public double StopAtual { get { return stopAtual; } }

        /// <summary>Risco inicial em pontos do índice (R = |entrada - stopInicial|).</summary>
        public double RiscoR { get { return riscoR; } }

        /// <summary>
        /// Abre uma posição LONG. <paramref name="stopInicial"/> deve ser
        /// estritamente menor que <paramref name="entrada"/> (caso contrário
        /// o risco seria zero ou negativo, o que não faz sentido).
        /// </summary>
        public void AbrirLong(double entrada, double stopInicial)
        {
            ValidarEntrada(entrada, stopInicial);
            if (!(stopInicial < entrada))
                throw new ArgumentException(
                    "stopInicial deve ser estritamente menor que entrada para LONG; recebidos "
                    + entrada + " / " + stopInicial);
            this.direcao = DirecaoTrade.Long;
            this.entradaPreco = entrada;
            this.stopInicial = stopInicial;
            this.riscoR = entrada - stopInicial;
            this.stopAtual = stopInicial;
            this.fase = FaseTrailing.Entrada;
        }

        /// <summary>
        /// Abre uma posição SHORT. <paramref name="stopInicial"/> deve ser
        /// estritamente maior que <paramref name="entrada"/>.
        /// </summary>
        public void AbrirShort(double entrada, double stopInicial)
        {
            ValidarEntrada(entrada, stopInicial);
            if (!(stopInicial > entrada))
                throw new ArgumentException(
                    "stopInicial deve ser estritamente maior que entrada para SHORT; recebidos "
                    + entrada + " / " + stopInicial);
            this.direcao = DirecaoTrade.Short;
            this.entradaPreco = entrada;
            this.stopInicial = stopInicial;
            this.riscoR = stopInicial - entrada;
            this.stopAtual = stopInicial;
            this.fase = FaseTrailing.Entrada;
        }

        /// <summary>
        /// Atualiza a máquina dado <paramref name="precoAtual"/> e devolve
        /// o stop a aplicar (R4.1–R4.3, R4.5). Quando não há posição,
        /// devolve <see cref="double.NaN"/>.
        /// </summary>
        public double Atualizar(double precoAtual)
        {
            if (fase == FaseTrailing.SemPosicao) return double.NaN;
            if (double.IsNaN(precoAtual) || double.IsInfinity(precoAtual))
                return stopAtual;

            // Lucro corrente em unidades de R, sempre não-negativo quando
            // o trade está a favor.
            double lucroR = direcao == DirecaoTrade.Long
                ? (precoAtual - entradaPreco) / riscoR
                : (entradaPreco - precoAtual) / riscoR;

            // Transições de fase (irreversíveis: fase só avança, nunca volta).
            if (fase == FaseTrailing.Entrada && lucroR >= fase1Mult)
                fase = FaseTrailing.Fase1Breakeven;
            if (fase == FaseTrailing.Fase1Breakeven && lucroR >= fase2Mult)
                fase = FaseTrailing.Fase2Lock;
            if (fase == FaseTrailing.Fase2Lock && lucroR >= fase3Mult)
                fase = FaseTrailing.Fase3Dinamico;

            // Stop alvo proposto pela fase corrente.
            double stopProposto;
            switch (fase)
            {
                case FaseTrailing.Entrada:
                    stopProposto = stopInicial;
                    break;
                case FaseTrailing.Fase1Breakeven:
                    stopProposto = entradaPreco;  // breakeven (R4.1)
                    break;
                case FaseTrailing.Fase2Lock:
                    // entrada + 0.3R em LONG; entrada - 0.3R em SHORT (R4.2).
                    stopProposto = direcao == DirecaoTrade.Long
                        ? entradaPreco + Fase2StopOffsetR * riscoR
                        : entradaPreco - Fase2StopOffsetR * riscoR;
                    break;
                case FaseTrailing.Fase3Dinamico:
                    // 0.5R atrás do preço corrente, sempre a favor (R4.3).
                    stopProposto = direcao == DirecaoTrade.Long
                        ? precoAtual - Fase3DistanciaR * riscoR
                        : precoAtual + Fase3DistanciaR * riscoR;
                    break;
                default:
                    stopProposto = stopAtual;
                    break;
            }

            // R4.5 — monotonia: stop nunca move contra o trade.
            if (direcao == DirecaoTrade.Long)
                stopAtual = Math.Max(stopAtual, stopProposto);
            else
                stopAtual = Math.Min(stopAtual, stopProposto);

            return stopAtual;
        }

        /// <summary>Fecha a posição corrente e reseta para SemPosicao.</summary>
        public void Fechar()
        {
            this.fase = FaseTrailing.SemPosicao;
            this.entradaPreco = 0.0;
            this.stopInicial = 0.0;
            this.riscoR = 0.0;
            this.stopAtual = 0.0;
        }

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------
        private static void ValidarEntrada(double entrada, double stopInicial)
        {
            if (double.IsNaN(entrada) || double.IsInfinity(entrada))
                throw new ArgumentException("entrada não pode ser NaN/Infinity");
            if (double.IsNaN(stopInicial) || double.IsInfinity(stopInicial))
                throw new ArgumentException("stopInicial não pode ser NaN/Infinity");
        }
    }
}
