// Logger.cs — log estruturado auditável (Spec 3 — Task 1).
//
// Cobre R7 do requirements.md do Spec 3:
// - R7.1: cada evento gravado em <workspace>/05_BACKTEST/logs/AAAA-MM-DD-{strategia}.log.
// - R7.2: formato "<timestamp ISO 8601 UTC> <NIVEL> <evento> <payload-json>".
// - R7.3: fallback para Print(...) do NinjaScript em qualquer falha de I/O.
// - R7.4: workspace root configurável; default %USERPROFILE%\CAOS\.
//
// Helper estático sem dependências do runtime do NinjaScript — só usa
// System, System.IO, System.Text, System.Globalization. Recebe um Action<string>
// opcional (apontado para Print do NT8) que serve de fallback para qualquer
// IOException ou exceção inesperada de I/O.
//
// Convenção de namespace: NinjaTrader.NinjaScript.Strategies.CAOS, alinhada
// ao padrão do NT8 para que o NinjaScript Editor consiga compilar sem ajustes.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>Severidade do evento auditado.</summary>
    public enum LogNivel
    {
        INFO,
        WARN,
        ERROR
    }

    /// <summary>
    /// Logger estruturado para o núcleo CAOS. Grava em arquivo por dia /
    /// estratégia; em qualquer falha de I/O, recai para o callback de
    /// <see cref="Print"/> do NinjaScript.
    /// </summary>
    public static class Logger
    {
        // Formato canônico do timestamp para parsing automático no Spec 2:
        // 2025-01-02T13:32:00Z (segundos, sufixo "Z" — UTC explícito).
        private const string FormatoTimestamp = "yyyy-MM-ddTHH:mm:ssZ";

        // Buffer interno para escapar payloads JSON. Reservado para evitar
        // alocações excessivas em chamadas frequentes (cada barra pode logar).
        [ThreadStatic]
        private static StringBuilder _buffer;

        /// <summary>
        /// Resolve a raiz do workspace CAOS (R7.4): se <paramref name="workspaceRoot"/>
        /// estiver vazio ou nulo, usa <c>%USERPROFILE%\CAOS\</c>.
        /// </summary>
        public static string ResolverWorkspaceRoot(string workspaceRoot)
        {
            if (!string.IsNullOrWhiteSpace(workspaceRoot))
                return workspaceRoot.Trim();
            string userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            return Path.Combine(userProfile, "CAOS");
        }

        /// <summary>
        /// Caminho absoluto do arquivo de log do dia (R7.1).
        /// Usa <c>UtcNow</c> para evitar dependência de fuso da máquina.
        /// </summary>
        public static string CaminhoLogDoDia(string workspaceRoot, string nomeEstrategia)
        {
            string root = ResolverWorkspaceRoot(workspaceRoot);
            string diaIso = DateTime.UtcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            string nomeArquivo = string.Format(
                CultureInfo.InvariantCulture,
                "{0}-{1}.log",
                diaIso,
                SanitizarNome(nomeEstrategia));
            return Path.Combine(root, "05_BACKTEST", "logs", nomeArquivo);
        }

        /// <summary>
        /// Grava um evento no log estruturado (R7.1, R7.2).
        /// </summary>
        /// <param name="workspaceRoot">Raiz do workspace CAOS (vazio = default).</param>
        /// <param name="nomeEstrategia">Nome da estratégia para nome do arquivo.</param>
        /// <param name="nivel">Severidade.</param>
        /// <param name="evento">Identificador curto, kebab-case, sem espaços.</param>
        /// <param name="payload">Pares chave→valor que viram JSON. <c>null</c> equivale a {}.</param>
        /// <param name="printFallback">Callback opcional (Print do NT8) usado em falha de I/O (R7.3).</param>
        public static void Logar(
            string workspaceRoot,
            string nomeEstrategia,
            LogNivel nivel,
            string evento,
            IDictionary<string, object> payload,
            Action<string> printFallback)
        {
            string linha = MontarLinha(nivel, evento, payload);
            string caminho;
            try
            {
                caminho = CaminhoLogDoDia(workspaceRoot, nomeEstrategia);
            }
            catch (Exception)
            {
                // ResolverWorkspaceRoot/Combine falhar é improvável, mas
                // se acontecer cai direto no fallback.
                if (printFallback != null) printFallback(linha);
                return;
            }

            try
            {
                string pasta = Path.GetDirectoryName(caminho);
                if (!string.IsNullOrEmpty(pasta) && !Directory.Exists(pasta))
                    Directory.CreateDirectory(pasta);

                // Append + flush imediato — idempotência sob crash do NT8.
                using (StreamWriter sw = new StreamWriter(caminho, append: true, encoding: Encoding.UTF8))
                {
                    sw.WriteLine(linha);
                    sw.Flush();
                }
            }
            catch (Exception)
            {
                // R7.3 — qualquer falha de I/O cai no Print do NT8.
                if (printFallback != null) printFallback(linha);
            }
        }

        /// <summary>
        /// Sobrecarga sem payload (eventos sem campos extras).
        /// </summary>
        public static void Logar(
            string workspaceRoot,
            string nomeEstrategia,
            LogNivel nivel,
            string evento,
            Action<string> printFallback)
        {
            Logar(workspaceRoot, nomeEstrategia, nivel, evento, null, printFallback);
        }

        // ------------------------------------------------------------------
        // Formatação
        // ------------------------------------------------------------------

        /// <summary>Constrói a linha completa "&lt;ts&gt; &lt;NIVEL&gt; &lt;evento&gt; &lt;json&gt;".</summary>
        public static string MontarLinha(
            LogNivel nivel,
            string evento,
            IDictionary<string, object> payload)
        {
            string ts = DateTime.UtcNow.ToString(FormatoTimestamp, CultureInfo.InvariantCulture);
            string eventoSan = SanitizarEvento(evento);
            string json = SerializarPayload(payload);
            return string.Format(
                CultureInfo.InvariantCulture,
                "{0} {1} {2} {3}",
                ts,
                nivel.ToString(),
                eventoSan,
                json);
        }

        /// <summary>
        /// Serializa <paramref name="payload"/> num JSON minimalista. Não usa
        /// <c>System.Text.Json</c> para preservar compatibilidade com .NET
        /// Framework 4.8 puro, que é o runtime do NinjaTrader 8.
        /// </summary>
        private static string SerializarPayload(IDictionary<string, object> payload)
        {
            if (payload == null || payload.Count == 0) return "{}";

            StringBuilder sb = ObterBuffer();
            sb.Length = 0;
            sb.Append('{');
            bool primeiro = true;
            foreach (KeyValuePair<string, object> par in payload)
            {
                if (!primeiro) sb.Append(',');
                primeiro = false;
                sb.Append('"');
                EscaparString(sb, par.Key ?? string.Empty);
                sb.Append('"');
                sb.Append(':');
                AppendValor(sb, par.Value);
            }
            sb.Append('}');
            return sb.ToString();
        }

        private static void AppendValor(StringBuilder sb, object valor)
        {
            if (valor == null)
            {
                sb.Append("null");
                return;
            }
            if (valor is string s)
            {
                sb.Append('"');
                EscaparString(sb, s);
                sb.Append('"');
                return;
            }
            if (valor is bool b)
            {
                sb.Append(b ? "true" : "false");
                return;
            }
            if (valor is double d)
            {
                if (double.IsNaN(d) || double.IsInfinity(d))
                {
                    sb.Append("null"); // JSON não tem NaN; degrada para null.
                    return;
                }
                sb.Append(d.ToString("R", CultureInfo.InvariantCulture));
                return;
            }
            if (valor is float f)
            {
                if (float.IsNaN(f) || float.IsInfinity(f))
                {
                    sb.Append("null");
                    return;
                }
                sb.Append(f.ToString("R", CultureInfo.InvariantCulture));
                return;
            }
            if (valor is int i)
            {
                sb.Append(i.ToString(CultureInfo.InvariantCulture));
                return;
            }
            if (valor is long l)
            {
                sb.Append(l.ToString(CultureInfo.InvariantCulture));
                return;
            }
            if (valor is DateTime dt)
            {
                sb.Append('"');
                sb.Append(dt.ToUniversalTime().ToString(FormatoTimestamp, CultureInfo.InvariantCulture));
                sb.Append('"');
                return;
            }
            // Fallback genérico — tenta IFormattable, senão ToString().
            string txt = valor is IFormattable fmt
                ? fmt.ToString(null, CultureInfo.InvariantCulture)
                : valor.ToString();
            sb.Append('"');
            EscaparString(sb, txt);
            sb.Append('"');
        }

        private static void EscaparString(StringBuilder sb, string s)
        {
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                            sb.AppendFormat(CultureInfo.InvariantCulture, "\\u{0:x4}", (int)c);
                        else
                            sb.Append(c);
                        break;
                }
            }
        }

        private static string SanitizarEvento(string evento)
        {
            if (string.IsNullOrWhiteSpace(evento)) return "evento-sem-nome";
            // Espaços e caracteres de controle quebram o parser de log;
            // colapsamos em hífen para manter o evento como token único.
            StringBuilder sb = ObterBuffer();
            sb.Length = 0;
            foreach (char c in evento)
            {
                if (c <= ' ') sb.Append('-');
                else sb.Append(c);
            }
            return sb.ToString();
        }

        private static string SanitizarNome(string nome)
        {
            if (string.IsNullOrWhiteSpace(nome)) return "estrategia-sem-nome";
            StringBuilder sb = ObterBuffer();
            sb.Length = 0;
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

        private static StringBuilder ObterBuffer()
        {
            if (_buffer == null) _buffer = new StringBuilder(256);
            return _buffer;
        }
    }
}
