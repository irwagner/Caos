// SpreadFilterLogica.cs — overlay running median de spread bid/ask.
//
// Espelhamento do EstrategiaSpreadFilter Python (modo mediana_diaria,
// running median, warmup configuravel). Aprovado para Walk-Forward
// via Decisao 2026-05-25-02.
//
// Em runtime no NinjaTrader 8:
// - A cada barra (1m), a Strategy_CAOS chama AdicionarObservacao com o
//   spread atual (GetCurrentAsk - GetCurrentBid).
// - Apos warmup_minutos do dia corrente, MinutoPermitido devolve
//   true SE o spread atual esta <= mediana running dos minutos
//   passados do mesmo dia.
// - Reset automatico no rollover de dia UTC.
//
// Classe pura — testavel via espelhamento Python (Property 16).

using System;
using System.Collections.Generic;
using System.Linq;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>
    /// Estado do filtro de spread running median. Mantido pelo caller.
    /// </summary>
    public class EstadoSpreadFilter
    {
        public DateTime DiaCorrente { get; set; } = DateTime.MinValue;
        public List<double> SpreadsObservadosNoDia { get; set; } = new List<double>();
    }

    public static class SpreadFilterLogica
    {
        /// <summary>Default conservador: precisa 30 minutos de dados antes de filtrar.</summary>
        public const int MinutosWarmupDefault = 30;

        /// <summary>
        /// Adiciona uma observacao de spread (em pontos) ao buffer do dia.
        /// Detecta rollover de dia automaticamente e reseta o buffer.
        /// </summary>
        public static void AdicionarObservacao(
            EstadoSpreadFilter estado, DateTime timestampUtc, double spread)
        {
            DateTime dia = timestampUtc.Date;
            if (dia != estado.DiaCorrente)
            {
                estado.DiaCorrente = dia;
                estado.SpreadsObservadosNoDia = new List<double>();
            }
            // Sanity: nunca aceita spread negativo (bug de cotacao).
            if (spread < 0 || double.IsNaN(spread) || double.IsInfinity(spread))
                return;
            estado.SpreadsObservadosNoDia.Add(spread);
        }

        /// <summary>
        /// Devolve true se o minuto atual e elegivel (spread <= mediana
        /// running). Antes do warmup, devolve true (politica
        /// permissiva, alinhada com Python).
        /// </summary>
        public static bool MinutoPermitido(
            EstadoSpreadFilter estado, double spreadAtual, int warmupMinutos)
        {
            // Antes do warmup: permite tudo.
            if (estado.SpreadsObservadosNoDia.Count < warmupMinutos)
                return true;

            // Calcula mediana corrente (sobre minutos PASSADOS — o spread
            // atual ja foi adicionado mas estamos comparando o spread mais
            // recente contra o historico anterior. Em pratica, o caller
            // deve chamar AdicionarObservacao APOS chamar MinutoPermitido
            // para preservar isso, mas como o spread atual ja faz parte
            // do buffer, aceitamos a margem de 1-tick que isso introduz).
            double mediana = MedianaPura(estado.SpreadsObservadosNoDia);
            if (mediana <= 0) return true;
            return spreadAtual <= mediana;
        }

        /// <summary>
        /// Mediana de uma lista de doubles. Implementacao pura, sem alocacao
        /// extra desnecessaria — copia interna ordenada e devolve elemento
        /// central (ou media dos dois centrais).
        /// </summary>
        public static double MedianaPura(List<double> valores)
        {
            int n = valores.Count;
            if (n == 0) return 0.0;
            double[] ord = valores.ToArray();
            Array.Sort(ord);
            if (n % 2 == 1) return ord[n / 2];
            return (ord[n / 2 - 1] + ord[n / 2]) / 2.0;
        }
    }
}
