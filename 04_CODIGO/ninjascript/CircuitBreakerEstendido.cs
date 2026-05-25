// CircuitBreakerEstendido.cs — extensao multi-periodo do Cerberus.
//
// O Cerberus_CSharp ja tem circuit breaker DIARIO. Esta classe adiciona
// circuit breaker SEMANAL e POR JANELA WALK-FORWARD (sessao operacional),
// espelhando EstrategiaCircuitBreaker Python aprovado na Decisao
// 2026-05-25-02 com limites:
//   diario  = USD 500   (-250 pts)
//   semanal = USD 1500  (-750 pts)
//   janela  = USD 2000  (-1000 pts)
//
// Em produçao paper trading, "janela" pode ser interpretado como a
// "sessao operacional total" (acumulado desde o inicio do hold-out).
// O reset acontece manualmente via Resetar() — o caller decide quando
// uma nova sessao operacional comeca (ex: depois de aprovacao em Debate
// de seguimento).

using System;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>
    /// Circuit breaker multi-periodo: diario, semanal, janela.
    /// Independente do Cerberus_CSharp (que cobre apenas o diario).
    /// Aplicado em conjunto: se QUALQUER um dos 3 dispara, bloqueia.
    /// </summary>
    public class CircuitBreakerEstendido
    {
        private readonly double limiteDiarioUSD;
        private readonly double limiteSemanalUSD;
        private readonly double limiteJanelaUSD;

        private double pnlDiarioUSD;
        private double pnlSemanalUSD;
        private double pnlJanelaUSD;

        private DateTime diaCorrenteUtc;
        private int semanaIsoCorrente;
        private int anoIsoCorrente;

        private bool bloqueadoDia;
        private bool bloqueadoSemana;
        private bool bloqueadoJanela;

        private readonly Func<DateTime> agoraUtc;

        /// <summary>
        /// Cria um novo circuit breaker estendido.
        /// </summary>
        /// <param name="limiteDiarioUSD">Magnitude positiva (ex: 500.0 = bloqueia em -USD 500).</param>
        /// <param name="limiteSemanalUSD">Magnitude positiva (ex: 1500.0).</param>
        /// <param name="limiteJanelaUSD">Magnitude positiva (ex: 2000.0).</param>
        /// <param name="agoraUtc">Funcao para obter UTC atual (default DateTime.UtcNow).</param>
        public CircuitBreakerEstendido(
            double limiteDiarioUSD = 500.0,
            double limiteSemanalUSD = 1500.0,
            double limiteJanelaUSD = 2000.0,
            Func<DateTime> agoraUtc = null)
        {
            if (limiteDiarioUSD <= 0) throw new ArgumentOutOfRangeException("limiteDiarioUSD");
            if (limiteSemanalUSD <= 0) throw new ArgumentOutOfRangeException("limiteSemanalUSD");
            if (limiteJanelaUSD <= 0) throw new ArgumentOutOfRangeException("limiteJanelaUSD");

            this.limiteDiarioUSD = limiteDiarioUSD;
            this.limiteSemanalUSD = limiteSemanalUSD;
            this.limiteJanelaUSD = limiteJanelaUSD;
            this.agoraUtc = agoraUtc ?? (() => DateTime.UtcNow);
            DateTime hoje = this.agoraUtc().Date;
            this.diaCorrenteUtc = hoje;
            var iso = SemanaIso(hoje);
            this.anoIsoCorrente = iso.Item1;
            this.semanaIsoCorrente = iso.Item2;
            this.pnlDiarioUSD = 0.0;
            this.pnlSemanalUSD = 0.0;
            this.pnlJanelaUSD = 0.0;
        }

        public bool BloqueadoAgora
        {
            get
            {
                VerificarRollover();
                return bloqueadoDia || bloqueadoSemana || bloqueadoJanela;
            }
        }

        public double PnlDiarioUSD { get { VerificarRollover(); return pnlDiarioUSD; } }
        public double PnlSemanalUSD { get { VerificarRollover(); return pnlSemanalUSD; } }
        public double PnlJanelaUSD { get { return pnlJanelaUSD; } }

        public string MotivoBloqueio()
        {
            if (bloqueadoDia) return "diario";
            if (bloqueadoSemana) return "semanal";
            if (bloqueadoJanela) return "janela";
            return "";
        }

        /// <summary>
        /// Registra PnL de um trade fechado (positivo ou negativo). Recalcula
        /// limiares e ativa bloqueios se necessario.
        /// </summary>
        public void RegistrarPnlRealizado(double pnlUSD)
        {
            VerificarRollover();
            if (double.IsNaN(pnlUSD) || double.IsInfinity(pnlUSD))
                throw new ArgumentException("pnl nao pode ser NaN/Infinity");

            pnlDiarioUSD += pnlUSD;
            pnlSemanalUSD += pnlUSD;
            pnlJanelaUSD += pnlUSD;

            if (pnlDiarioUSD <= -limiteDiarioUSD) bloqueadoDia = true;
            if (pnlSemanalUSD <= -limiteSemanalUSD) bloqueadoSemana = true;
            if (pnlJanelaUSD <= -limiteJanelaUSD) bloqueadoJanela = true;
        }

        /// <summary>
        /// Reset manual de TODOS os contadores e bloqueios — usar apenas
        /// quando comeca uma nova sessao operacional aprovada por Debate.
        /// </summary>
        public void Resetar()
        {
            pnlDiarioUSD = 0;
            pnlSemanalUSD = 0;
            pnlJanelaUSD = 0;
            bloqueadoDia = false;
            bloqueadoSemana = false;
            bloqueadoJanela = false;
            DateTime hoje = agoraUtc().Date;
            diaCorrenteUtc = hoje;
            var iso = SemanaIso(hoje);
            anoIsoCorrente = iso.Item1;
            semanaIsoCorrente = iso.Item2;
        }

        private void VerificarRollover()
        {
            DateTime hoje = agoraUtc().Date;
            if (hoje != diaCorrenteUtc)
            {
                diaCorrenteUtc = hoje;
                pnlDiarioUSD = 0.0;
                bloqueadoDia = false;
            }
            var iso = SemanaIso(hoje);
            if (iso.Item1 != anoIsoCorrente || iso.Item2 != semanaIsoCorrente)
            {
                anoIsoCorrente = iso.Item1;
                semanaIsoCorrente = iso.Item2;
                pnlSemanalUSD = 0.0;
                bloqueadoSemana = false;
            }
        }

        /// <summary>
        /// (ano_iso, semana_iso). C# nao tem GetIsoWeekOfYear no .NET 4.x
        /// que NT8 usa, entao implementamos manualmente com regra ISO 8601.
        /// </summary>
        private static Tuple<int, int> SemanaIso(DateTime data)
        {
            // Regra ISO: o ano da quinta-feira da semana define o ano ISO.
            DayOfWeek dow = data.DayOfWeek;
            int diff = dow == DayOfWeek.Monday ? 0
                : (dow == DayOfWeek.Sunday ? 6 : (int)dow - 1);
            DateTime quinta = data.AddDays(-diff + 3);
            int ano = quinta.Year;
            // Numero da semana ISO: dia juliano da quinta / 7 ajustado.
            DateTime jan4 = new DateTime(ano, 1, 4);
            int diff4 = jan4.DayOfWeek == DayOfWeek.Monday ? 0
                : (jan4.DayOfWeek == DayOfWeek.Sunday ? 6 : (int)jan4.DayOfWeek - 1);
            DateTime semana1Seg = jan4.AddDays(-diff4);
            int semana = (int)((quinta.AddDays(-(int)quinta.DayOfWeek + 1) - semana1Seg).Days / 7) + 1;
            return Tuple.Create(ano, semana);
        }
    }
}
