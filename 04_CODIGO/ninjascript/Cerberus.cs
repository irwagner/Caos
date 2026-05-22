// Cerberus.cs — gestão de risco em tempo real (Spec 3 — Task 2).
//
// Cobre R3 do requirements.md:
// - R3.1: AutorizarEntrada bloqueia contratos > MaxContratos.
// - R3.2: Circuit_Breaker_Diario configurável (default USD 500).
// - R3.5: rollover diário (UTC) reseta pnlDiarioRealizado e circuitBreaker.
//
// Classe pura — sem dependência do runtime do NinjaScript. Permite
// reimplementação byte-a-byte em caos.ninjascript_modelo.cerberus para
// validação automatizada via Property 16 (Hypothesis).
//
// Convenção: identificadores de método/parâmetro em inglês quando idiomáticos
// no ecossistema C#; mensagens, comentários e docstrings em pt-BR.

using System;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>
    /// Gerente de risco do CAOS dentro do NinjaTrader 8. Toda intenção de
    /// envio de ordem da <see cref="Strategy_CAOS"/> roteia por
    /// <see cref="AutorizarEntrada"/> antes de chamar <c>EnterLong</c>/<c>EnterShort</c>.
    /// </summary>
    public class Cerberus_CSharp
    {
        private readonly int maxContratos;
        private readonly double circuitBreakerUSD;

        private double pnlDiarioRealizado;
        private bool circuitBreakerAtivado;
        private DateTime diaCorrenteUtc;

        // Função para obter o "agora UTC". Default é DateTime.UtcNow, mas
        // testes podem injetar um clock fake para validar rollover sem
        // depender de horário real (a porta Python faz o mesmo).
        private readonly Func<DateTime> agoraUtc;

        /// <summary>
        /// Cria um novo Cerberus.
        /// </summary>
        /// <param name="maxContratos">Tamanho máximo de posição em contratos (R3.1).</param>
        /// <param name="circuitBreakerUSD">Drawdown diário máximo em USD; atingido fecha posição e bloqueia novas entradas (R3.2).</param>
        /// <param name="agoraUtc">Função que retorna o instante UTC atual; default = <see cref="DateTime.UtcNow"/>.</param>
        public Cerberus_CSharp(int maxContratos, double circuitBreakerUSD, Func<DateTime> agoraUtc = null)
        {
            if (maxContratos < 1)
                throw new ArgumentOutOfRangeException(
                    "maxContratos",
                    "maxContratos deve ser >= 1; recebido " + maxContratos);
            if (circuitBreakerUSD <= 0.0)
                throw new ArgumentOutOfRangeException(
                    "circuitBreakerUSD",
                    "circuitBreakerUSD deve ser > 0; recebido " + circuitBreakerUSD);

            this.maxContratos = maxContratos;
            this.circuitBreakerUSD = circuitBreakerUSD;
            this.agoraUtc = agoraUtc ?? (() => DateTime.UtcNow);
            this.diaCorrenteUtc = this.agoraUtc().Date;
            this.pnlDiarioRealizado = 0.0;
            this.circuitBreakerAtivado = false;
        }

        /// <summary>Tamanho máximo de posição configurado (R3.1).</summary>
        public int MaxContratos { get { return maxContratos; } }

        /// <summary>Limite diário de drawdown em USD (R3.2).</summary>
        public double CircuitBreakerUSD { get { return circuitBreakerUSD; } }

        /// <summary>PnL realizado acumulado no dia UTC corrente.</summary>
        public double PnlDiarioRealizado
        {
            get
            {
                VerificarRolloverDia();
                return pnlDiarioRealizado;
            }
        }

        /// <summary>True se o circuit breaker foi ativado no dia UTC corrente.</summary>
        public bool CircuitBreakerAtivo
        {
            get
            {
                VerificarRolloverDia();
                return circuitBreakerAtivado;
            }
        }

        /// <summary>
        /// Decide se uma intenção de entrada pode prosseguir (R3.1, R3.2).
        /// Bloqueia quando:
        /// <list type="bullet">
        /// <item>circuit breaker ativo;</item>
        /// <item><paramref name="contratos"/> &lt; 1 ou &gt; <see cref="MaxContratos"/>;</item>
        /// <item><paramref name="riscoUSD"/> &lt;= 0 (risco não declarado).</item>
        /// </list>
        /// </summary>
        public bool AutorizarEntrada(int contratos, double riscoUSD)
        {
            VerificarRolloverDia();
            if (circuitBreakerAtivado) return false;
            if (contratos < 1) return false;
            if (contratos > maxContratos) return false;
            if (double.IsNaN(riscoUSD) || double.IsInfinity(riscoUSD)) return false;
            if (riscoUSD <= 0.0) return false;
            return true;
        }

        /// <summary>
        /// Registra o PnL realizado de um trade fechado. Pode ser positivo ou
        /// negativo. Quando o acumulado do dia atinge <c>-CircuitBreakerUSD</c>
        /// (ou pior), o circuit breaker é ativado e bloqueia novas entradas
        /// até o próximo dia UTC (R3.2, R3.5).
        /// </summary>
        public void RegistrarPnlRealizado(double pnl)
        {
            VerificarRolloverDia();
            if (double.IsNaN(pnl) || double.IsInfinity(pnl))
                throw new ArgumentException("pnl não pode ser NaN/Infinity", "pnl");
            pnlDiarioRealizado += pnl;
            if (pnlDiarioRealizado <= -circuitBreakerUSD)
                circuitBreakerAtivado = true;
        }

        /// <summary>
        /// Reset manual (útil em testes e ao iniciar uma nova sessão).
        /// Em operação normal, <see cref="VerificarRolloverDia"/> faz isso
        /// automaticamente no rollover de UTC.
        /// </summary>
        public void Resetar()
        {
            pnlDiarioRealizado = 0.0;
            circuitBreakerAtivado = false;
            diaCorrenteUtc = agoraUtc().Date;
        }

        // ------------------------------------------------------------------
        // R3.5 — Rollover diário em UTC
        // ------------------------------------------------------------------
        private void VerificarRolloverDia()
        {
            DateTime hoje = agoraUtc().Date;
            if (hoje != diaCorrenteUtc)
            {
                diaCorrenteUtc = hoje;
                pnlDiarioRealizado = 0.0;
                circuitBreakerAtivado = false;
            }
        }
    }
}
