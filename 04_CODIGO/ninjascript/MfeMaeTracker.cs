// MfeMaeTracker.cs — instrumentação MFE/MAE por trade (Spec 3 — Task 4).
//
// Cobre R5 do requirements.md:
// - R5.1: acompanha mfe_atual e mae_atual em ticks por trade aberto.
// - R5.2: ao fechar, escreve linha CSV em
//   05_BACKTEST/mfe_mae/AAAA-MM-DD-{estrategia}.csv.
// - R5.3: header canônico
//   id_trade,entrada_timestamp,saida_timestamp,direcao,mfe_ticks,mae_ticks,pnl_usd.
// - R5.4: mfe_ticks >= 0 e mae_ticks <= 0 em qualquer linha gravada (Property 18).
//
// Classe pura — não usa runtime do NinjaScript. A lógica de captura de
// preço (GetCurrentAsk/Bid) fica em Strategy_CAOS, que invoca Atualizar.

using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>Direção do trade rastreado.</summary>
    public enum DirecaoTradeMfeMae
    {
        Long,
        Short
    }

    /// <summary>
    /// Snapshot imutável do trade fechado (linha do CSV).
    /// </summary>
    public class TradeMfeMae
    {
        public int IdTrade;
        public DateTime EntradaTimestamp;
        public DateTime SaidaTimestamp;
        public DirecaoTradeMfeMae Direcao;
        public int MfeTicks;
        public int MaeTicks;
        public double PnlUSD;
    }

    /// <summary>
    /// Acompanha MFE/MAE de uma posição aberta e grava 1 linha por trade
    /// fechado em <c>&lt;workspace&gt;/05_BACKTEST/mfe_mae/AAAA-MM-DD-{estrategia}.csv</c>.
    /// </summary>
    public class MfeMaeTracker
    {
        private const string Header =
            "id_trade,entrada_timestamp,saida_timestamp,direcao,mfe_ticks,mae_ticks,pnl_usd";
        private const string FormatoTimestamp = "yyyy-MM-ddTHH:mm:ssZ";

        private readonly string workspaceRoot;
        private readonly string nomeEstrategia;
        private readonly double tickSize;

        // Estado da posição corrente. Quando idTradeAtual == 0, não há trade aberto.
        private int idTradeAtual;
        private DirecaoTradeMfeMae direcaoAtual;
        private double entradaPreco;
        private DateTime entradaTimestamp;
        private int mfeTicks;
        private int maeTicks;

        public MfeMaeTracker(string workspaceRoot, string nomeEstrategia, double tickSize)
        {
            if (tickSize <= 0.0 || double.IsNaN(tickSize) || double.IsInfinity(tickSize))
                throw new ArgumentOutOfRangeException("tickSize", "tickSize deve ser > 0");
            this.workspaceRoot = workspaceRoot ?? string.Empty;
            this.nomeEstrategia = string.IsNullOrWhiteSpace(nomeEstrategia)
                ? "estrategia-sem-nome"
                : nomeEstrategia.Trim();
            this.tickSize = tickSize;
            this.idTradeAtual = 0;
        }

        /// <summary>True quando há um trade aberto sendo rastreado.</summary>
        public bool TemTradeAberto { get { return idTradeAtual != 0; } }

        /// <summary>MFE corrente em ticks (>= 0 sempre por construção).</summary>
        public int MfeTicksCorrente { get { return mfeTicks; } }

        /// <summary>MAE corrente em ticks (&lt;= 0 sempre por construção).</summary>
        public int MaeTicksCorrente { get { return maeTicks; } }

        /// <summary>
        /// Abre o rastreamento de um novo trade. <paramref name="idTrade"/>
        /// deve ser positivo e único por sessão.
        /// </summary>
        public void AbrirTrade(
            int idTrade,
            DirecaoTradeMfeMae direcao,
            double entradaPreco,
            DateTime entradaTimestamp)
        {
            if (idTrade <= 0)
                throw new ArgumentOutOfRangeException("idTrade", "idTrade deve ser > 0");
            if (TemTradeAberto)
                throw new InvalidOperationException(
                    "MfeMaeTracker já tem trade aberto (id=" + idTradeAtual
                    + "); chame FecharTrade antes de AbrirTrade novamente.");
            if (double.IsNaN(entradaPreco) || double.IsInfinity(entradaPreco))
                throw new ArgumentException("entradaPreco inválido", "entradaPreco");

            this.idTradeAtual = idTrade;
            this.direcaoAtual = direcao;
            this.entradaPreco = entradaPreco;
            this.entradaTimestamp = entradaTimestamp.ToUniversalTime();
            this.mfeTicks = 0;
            this.maeTicks = 0;
        }

        /// <summary>
        /// Atualiza MFE/MAE com <paramref name="precoAtual"/>. Operação
        /// idempotente: chamadas repetidas com o mesmo preço não mudam nada.
        /// </summary>
        public void Atualizar(double precoAtual)
        {
            if (!TemTradeAberto) return;
            if (double.IsNaN(precoAtual) || double.IsInfinity(precoAtual)) return;

            // Excursão em ticks, sinalizada pela direção do trade.
            // Para LONG: subir é favorável (positivo).
            // Para SHORT: descer é favorável (positivo).
            double delta = direcaoAtual == DirecaoTradeMfeMae.Long
                ? precoAtual - entradaPreco
                : entradaPreco - precoAtual;
            int deltaTicks = (int)Math.Round(delta / tickSize, MidpointRounding.AwayFromZero);

            // R5.4: mfe sempre >= 0; mae sempre <= 0.
            if (deltaTicks > mfeTicks) mfeTicks = deltaTicks;
            if (deltaTicks < maeTicks) maeTicks = deltaTicks;
        }

        /// <summary>
        /// Fecha o trade corrente, calcula PnL final e devolve o snapshot.
        /// Caller é responsável por persistir via <see cref="EscreverLinhaCSV"/>.
        /// </summary>
        public TradeMfeMae FecharTrade(double saidaPreco, DateTime saidaTimestamp, double pnlUSD)
        {
            if (!TemTradeAberto)
                throw new InvalidOperationException("MfeMaeTracker não tem trade aberto para fechar");
            if (double.IsNaN(saidaPreco) || double.IsInfinity(saidaPreco))
                throw new ArgumentException("saidaPreco inválido", "saidaPreco");

            // Atualiza uma última vez com o preço de saída — assim a excursão
            // realizada pelo próprio fill conta na MFE/MAE.
            Atualizar(saidaPreco);

            TradeMfeMae snapshot = new TradeMfeMae();
            snapshot.IdTrade = idTradeAtual;
            snapshot.Direcao = direcaoAtual;
            snapshot.EntradaTimestamp = entradaTimestamp;
            snapshot.SaidaTimestamp = saidaTimestamp.ToUniversalTime();
            snapshot.MfeTicks = mfeTicks;
            snapshot.MaeTicks = maeTicks;
            snapshot.PnlUSD = pnlUSD;

            // Reset de estado.
            idTradeAtual = 0;
            mfeTicks = 0;
            maeTicks = 0;
            entradaPreco = 0.0;

            return snapshot;
        }

        /// <summary>
        /// Combina <see cref="FecharTrade"/> + persistência atômica em CSV.
        /// </summary>
        public TradeMfeMae FecharTradeEPersistir(
            double saidaPreco,
            DateTime saidaTimestamp,
            double pnlUSD,
            Action<string> printFallback)
        {
            TradeMfeMae snap = FecharTrade(saidaPreco, saidaTimestamp, pnlUSD);
            EscreverLinhaCSV(snap, printFallback);
            return snap;
        }

        /// <summary>
        /// Resolve o caminho do CSV do dia. Usa o dia de entrada (entrada_timestamp)
        /// para que o trade fique sempre no arquivo do dia em que foi aberto,
        /// mesmo que feche depois da virada de UTC.
        /// </summary>
        public string CaminhoCsvDoTrade(TradeMfeMae snap)
        {
            string root = Logger.ResolverWorkspaceRoot(workspaceRoot);
            string diaIso = snap.EntradaTimestamp.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            string nomeArquivo = string.Format(
                CultureInfo.InvariantCulture,
                "{0}-{1}.csv",
                diaIso,
                SanitizarNome(nomeEstrategia));
            return Path.Combine(root, "05_BACKTEST", "mfe_mae", nomeArquivo);
        }

        /// <summary>
        /// Grava 1 linha de <paramref name="snap"/> no CSV do dia, criando
        /// header automaticamente se o arquivo for novo. Em qualquer falha
        /// de I/O, recai no callback (R7.3 — coerente com o fallback do
        /// <see cref="Logger"/>).
        /// </summary>
        public void EscreverLinhaCSV(TradeMfeMae snap, Action<string> printFallback)
        {
            if (snap == null) return;
            string caminho = CaminhoCsvDoTrade(snap);
            string linha = FormatarLinha(snap);

            try
            {
                string pasta = Path.GetDirectoryName(caminho);
                if (!string.IsNullOrEmpty(pasta) && !Directory.Exists(pasta))
                    Directory.CreateDirectory(pasta);

                bool arquivoNovo = !File.Exists(caminho);
                using (StreamWriter sw = new StreamWriter(caminho, append: true, encoding: Encoding.UTF8))
                {
                    if (arquivoNovo) sw.WriteLine(Header);
                    sw.WriteLine(linha);
                    sw.Flush();
                }
            }
            catch (Exception)
            {
                if (printFallback != null)
                    printFallback("[MfeMae fallback] " + linha);
            }
        }

        /// <summary>Header canônico do CSV (R5.3) — exposto para testes.</summary>
        public static string CabecalhoCsv { get { return Header; } }

        /// <summary>Formatação de uma linha (R5.3) — exposta para testes.</summary>
        public static string FormatarLinha(TradeMfeMae snap)
        {
            return string.Format(
                CultureInfo.InvariantCulture,
                "{0},{1},{2},{3},{4},{5},{6}",
                snap.IdTrade,
                snap.EntradaTimestamp.ToString(FormatoTimestamp, CultureInfo.InvariantCulture),
                snap.SaidaTimestamp.ToString(FormatoTimestamp, CultureInfo.InvariantCulture),
                snap.Direcao == DirecaoTradeMfeMae.Long ? "LONG" : "SHORT",
                snap.MfeTicks,
                snap.MaeTicks,
                snap.PnlUSD.ToString("0.##", CultureInfo.InvariantCulture));
        }

        // ------------------------------------------------------------------
        private static string SanitizarNome(string nome)
        {
            StringBuilder sb = new StringBuilder(nome.Length);
            foreach (char c in nome)
            {
                bool valido =
                    (c >= 'a' && c <= 'z') ||
                    (c >= 'A' && c <= 'Z') ||
                    (c >= '0' && c <= '9') ||
                    c == '-' || c == '_';
                sb.Append(valido ? c : '-');
            }
            return sb.ToString();
        }
    }
}
