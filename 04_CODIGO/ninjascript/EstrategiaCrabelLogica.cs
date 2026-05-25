// EstrategiaCrabelLogica.cs — overlay NR7 (Narrow Range 7) sobre ORB.
//
// Crabel (1990): "compressão precede expansão". Um dia é elegível para
// operar ORB SE o dia útil ANTERIOR teve range diário <= menor range
// dos últimos 7 dias úteis (incluindo o dia anterior).
//
// Lógica espelhada do plugin Python EstrategiaORBCrabel
// (caos/walk_forward/estrategias/orb_crabel.py). Aprovado para
// Walk-Forward via Decisão 2026-05-25-02.
//
// Esta classe é estática + pura: não depende do runtime do NinjaScript.
// Pode ser testada por unidade C# espelhando os testes Python.

using System;
using System.Collections.Generic;
using System.Linq;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>
    /// Estado do filtro NR7. Mantido pelo caller (Strategy) e passado a
    /// cada barra para <see cref="EstrategiaCrabelLogica.AtualizarFiltro"/>.
    /// </summary>
    public class EstadoCrabelNR7
    {
        /// <summary>Mapa data -> range diario (high - low) dos dias ja vistos.</summary>
        public Dictionary<DateTime, double> RangePorDia { get; set; } = new Dictionary<DateTime, double>();

        /// <summary>Conjunto de dias elegiveis (dia que vem APOS um dia NR7).</summary>
        public HashSet<DateTime> DiasElegiveis { get; set; } = new HashSet<DateTime>();

        /// <summary>Estado do dia corrente (atualizado bar-a-bar).</summary>
        public DateTime DiaCorrente { get; set; } = DateTime.MinValue;
        public double HighDiaCorrente { get; set; } = double.NegativeInfinity;
        public double LowDiaCorrente { get; set; } = double.PositiveInfinity;

        /// <summary>
        /// Flag: o ULTIMO dia ja registrado em RangePorDia e NR7. Significa
        /// que o proximo dia (ainda nao visto) sera elegivel quando chegar.
        /// </summary>
        public bool ProximoDiaElegivel { get; set; } = false;
    }

    public static class EstrategiaCrabelLogica
    {
        /// <summary>Janela default do paper Crabel (7 dias).</summary>
        public const int JanelaNR = 7;

        /// <summary>
        /// Atualiza o estado do filtro NR7 com a barra recem chegada.
        /// Chame antes de testar elegibilidade. Devolve a data da barra
        /// (truncada) para conveniencia.
        /// </summary>
        public static DateTime AtualizarFiltro(EstadoCrabelNR7 estado, DateTime timestampUtc, double high, double low)
        {
            DateTime dia = timestampUtc.Date;

            // Inicializacao do primeiro dia.
            if (estado.DiaCorrente == DateTime.MinValue)
            {
                estado.DiaCorrente = dia;
                estado.HighDiaCorrente = high;
                estado.LowDiaCorrente = low;
                return dia;
            }

            // Mudanca de dia: fecha range do dia anterior e atualiza filtro.
            if (dia != estado.DiaCorrente)
            {
                double rangeAnterior = estado.HighDiaCorrente - estado.LowDiaCorrente;
                estado.RangePorDia[estado.DiaCorrente] = rangeAnterior;

                // Recomputa filtro com o conjunto atualizado.
                bool eraNR7 = ChecarSeUltimoEhNR(estado.RangePorDia, JanelaNR);
                estado.DiasElegiveis = CalcularDiasElegiveis(estado.RangePorDia, JanelaNR);

                // Se o dia que recem foi fechado e NR7, o dia que esta entrando
                // (este dia) e elegivel.
                if (eraNR7)
                {
                    estado.DiasElegiveis.Add(dia);
                }

                // Reset para o dia novo.
                estado.DiaCorrente = dia;
                estado.HighDiaCorrente = high;
                estado.LowDiaCorrente = low;
            }
            else
            {
                // Acumula range no dia corrente.
                if (high > estado.HighDiaCorrente) estado.HighDiaCorrente = high;
                if (low < estado.LowDiaCorrente) estado.LowDiaCorrente = low;
            }

            return dia;
        }

        /// <summary>
        /// True se o dia esta elegivel para operar ORB (dia anterior foi NR7).
        /// </summary>
        public static bool DiaEhElegivel(EstadoCrabelNR7 estado, DateTime dia)
        {
            return estado.DiasElegiveis.Contains(dia);
        }

        /// <summary>
        /// Computa o conjunto de dias que vem APOS um NR-janela. Cada dia
        /// d e elegivel se o dia ANTERIOR a d teve range minimo entre os
        /// ultimos `janela` dias uteis.
        /// </summary>
        private static HashSet<DateTime> CalcularDiasElegiveis(
            Dictionary<DateTime, double> rangePorDia, int janela)
        {
            HashSet<DateTime> elegiveis = new HashSet<DateTime>();
            if (rangePorDia.Count < janela) return elegiveis;

            List<DateTime> dias = rangePorDia.Keys.OrderBy(d => d).ToList();
            for (int i = janela - 1; i < dias.Count; i++)
            {
                List<double> ranges = new List<double>();
                for (int j = i - janela + 1; j <= i; j++)
                    ranges.Add(rangePorDia[dias[j]]);
                bool ehNR = rangePorDia[dias[i]] == ranges.Min();
                if (ehNR && i + 1 < dias.Count)
                {
                    elegiveis.Add(dias[i + 1]);
                }
            }
            return elegiveis;
        }

        /// <summary>
        /// True se o ULTIMO dia em rangePorDia e NR-janela. Usado para
        /// marcar o proximo dia como elegivel quando ele chegar.
        /// </summary>
        private static bool ChecarSeUltimoEhNR(Dictionary<DateTime, double> rangePorDia, int janela)
        {
            if (rangePorDia.Count < janela) return false;
            List<DateTime> dias = rangePorDia.Keys.OrderBy(d => d).ToList();
            DateTime ultimo = dias[dias.Count - 1];
            List<double> ranges = new List<double>();
            for (int j = dias.Count - janela; j < dias.Count; j++)
                ranges.Add(rangePorDia[dias[j]]);
            return rangePorDia[ultimo] == ranges.Min();
        }
    }
}
