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
        /// Contador de barras de minuto consumidas no dia corrente
        /// (Decisao 2026-05-26-01). Usado para filtrar dias parciais
        /// que nao constituem pregao regular (Globex domingo, feriado
        /// com fechamento muito antecipado).
        /// </summary>
        public int BarrasDiaCorrente { get; set; } = 0;

        /// <summary>
        /// Flag: o ULTIMO dia ja registrado em RangePorDia e NR7. Significa
        /// que o proximo dia (ainda nao visto) sera elegivel quando chegar
        /// — desde que esse proximo dia tambem seja valido.
        /// </summary>
        public bool ProximoDiaElegivel { get; set; } = false;
    }

    public static class EstrategiaCrabelLogica
    {
        /// <summary>Janela default do paper Crabel (7 dias).</summary>
        public const int JanelaNR = 7;

        /// <summary>
        /// Numero minimo de barras de minuto que um dia precisa ter para
        /// ser contado como dia util valido pelo filtro NR
        /// (Decisao 2026-05-26-01). Pregao regular MNQ = 1380 barras
        /// (23h * 60min); domingo Globex tem ~120-300 barras; feriado
        /// parcial tem ~430-720. Limiar 300 descarta especificamente
        /// abertura noturna de fim de semana.
        /// </summary>
        public const int MinBarrasDiaValido = 300;

        /// <summary>
        /// True se o dia da semana e segunda a sexta. Decisao 2026-05-26-01:
        /// sabado e domingo sao descartados pois representam abertura
        /// noturna do Globex com sessao truncada (~3-5h), nao pregao regular.
        /// </summary>
        public static bool DiaDaSemanaEhValido(DateTime dia)
        {
            DayOfWeek dow = dia.DayOfWeek;
            return dow != DayOfWeek.Saturday && dow != DayOfWeek.Sunday;
        }

        /// <summary>
        /// Atualiza o estado do filtro NR7 com a barra recem chegada.
        /// Chame antes de testar elegibilidade. Devolve a data da barra
        /// (truncada) para conveniencia.
        ///
        /// Decisao 2026-05-26-01: dias com sabado/domingo OU com menos
        /// de <see cref="MinBarrasDiaValido"/> barras sao DESCARTADOS
        /// — nao entram em RangePorDia nem podem virar dias elegiveis.
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
                estado.BarrasDiaCorrente = 1;
                return dia;
            }

            // Mudanca de dia: fecha range do dia anterior e atualiza filtro.
            if (dia != estado.DiaCorrente)
            {
                bool diaAnteriorValido =
                    DiaDaSemanaEhValido(estado.DiaCorrente)
                    && estado.BarrasDiaCorrente >= MinBarrasDiaValido;

                if (diaAnteriorValido)
                {
                    double rangeAnterior = estado.HighDiaCorrente - estado.LowDiaCorrente;
                    estado.RangePorDia[estado.DiaCorrente] = rangeAnterior;

                    // Recomputa filtro com o conjunto atualizado.
                    bool eraNR7 = ChecarSeUltimoEhNR(estado.RangePorDia, JanelaNR);
                    estado.DiasElegiveis = CalcularDiasElegiveis(estado.RangePorDia, JanelaNR);

                    // Se o dia que recem foi fechado e NR7, o dia que esta
                    // entrando (este dia) e elegivel — desde que tambem
                    // seja valido (sabado/domingo nao operam mesmo elegiveis).
                    if (eraNR7 && DiaDaSemanaEhValido(dia))
                    {
                        estado.DiasElegiveis.Add(dia);
                        estado.ProximoDiaElegivel = false;
                    }
                    else if (eraNR7 && !DiaDaSemanaEhValido(dia))
                    {
                        // Dia atual e invalido. Mantem flag ativa para o
                        // proximo dia util valido.
                        estado.ProximoDiaElegivel = true;
                    }
                }
                else
                {
                    // Dia anterior invalido — descarta. ProximoDiaElegivel
                    // pode ainda estar setado por dia anterior valido.
                    if (estado.ProximoDiaElegivel && DiaDaSemanaEhValido(dia))
                    {
                        estado.DiasElegiveis.Add(dia);
                        estado.ProximoDiaElegivel = false;
                    }
                }

                // Reset para o dia novo.
                estado.DiaCorrente = dia;
                estado.HighDiaCorrente = high;
                estado.LowDiaCorrente = low;
                estado.BarrasDiaCorrente = 1;
            }
            else
            {
                // Acumula range no dia corrente.
                if (high > estado.HighDiaCorrente) estado.HighDiaCorrente = high;
                if (low < estado.LowDiaCorrente) estado.LowDiaCorrente = low;
                estado.BarrasDiaCorrente++;
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
