// EstrategiaVvgClassifierLogica.cs — classificador VVG stateful (puro).
// Spec — VVG Late-Session Reversal (MNQ), Tarefa 7.
//
// Porta C# LITERAL do classificador VVG. A fonte canônica de produção é
// caos/walk_forward/estrategias/vvg_classifier.py (classe VvgClassifier,
// Tarefa 3); a porta de referência Python que espelha exatamente o estilo
// imperativo que o C# adota é caos/estrategias_modelo/vvg.py (classe
// _ClassificadorVvgModelo, Tarefa 5). Este arquivo é a tradução LINHA A
// LINHA de _ClassificadorVvgModelo — o ground truth da Property 11
// (test_vvg_paridade_py_cs.py, Tarefa 9). Qualquer divergência de
// comportamento quebra a paridade Python↔C# (R1.6) e DEVE ser revertida
// no mesmo commit.
//
// Decisão arquitetural-chave (mesmo padrão de EstrategiaCrabelLogica.cs e
// EstrategiaVvgLateSessionLogica.cs): classe PURA stateful, SEM qualquer
// dependência do runtime NinjaScript. Usa apenas .NET base (DateTime,
// TimeSpan, TimeZoneInfo, Queue, KeyValuePair, Math). Nenhum símbolo NT8
// (Strategy, Bars, Close, EnterLong, ...) é referenciado — portanto nada
// aqui está fora da whitelist ninjascript-api.md. Isso permite testar o
// classificador em isolamento e dirigir os dois lados (Python e C#) com as
// mesmas barras na Property 11.
//
// Acesso a close(D-1) sem AddDataSeries adicional (R5.5): o close de fim de
// RTH do dia anterior é capturado internamente bar-a-bar (campo
// _closeRthCorrente, promovido a _closeDMenos1 na transição de dia), sem
// exigir uma série diária separada — o setup permanece com a série
// primária de 1 minuto.
//
// Fuso horário: a conversão UTC→Nova York usa
// TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time"), que no
// Windows resolve o horário de verão (DST, EST/EDT) automaticamente —
// equivalente ao zoneinfo.ZoneInfo("America/New_York") do lado Python.
//
// Coordenação com a Tarefa 6 (paralela) — struct ParametrosVvg:
// para ser robusto a uma corrida de ordem de tarefas, o construtor
// PRIMÁRIO recebe os TRÊS valores consumidos diretamente
// (multiplicadorVolume, thresholdGapPct, nDiasBaseline) e NÃO depende da
// definição de ParametrosVvg. Há também um construtor de conveniência que
// aceita ParametrosVvg (definida em EstrategiaVvgLateSessionLogica.cs,
// mesmo namespace) e apenas encaminha os três campos — usado pela Tarefa
// 10 (StrategyVvgLateSessionReversal) para passar os parâmetros congelados
// sem duplicar literais. Como o classificador só LÊ esses três campos
// (nunca constrói a struct), o acoplamento é mínimo e o arquivo compila
// mesmo que ParametrosVvg evolua noutros campos.

using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.Strategies.CAOS
{
    /// <summary>
    /// Resultado da classificação VVG de um dia útil. Espelho fiel de
    /// <c>ResultadoClassificacao</c> (vvg_classifier.py) /
    /// <c>ResultadoClassificacaoModelo</c> (vvg.py).
    ///
    /// Campos:
    /// <list type="bullet">
    /// <item><c>VvgPositivo</c> — <c>true</c> se e somente se AMBAS as
    /// condições de R1.2 (volume e gap) são verdadeiras. <c>false</c> em
    /// warmup ou quando qualquer condição falha.</item>
    /// <item><c>VolumeMorning</c> — soma do volume das barras em
    /// [09:30, 10:00) NY do dia.</item>
    /// <item><c>VolumeBaseline</c> — média do <c>VolumeMorning</c> dos
    /// <c>nDiasBaseline</c> dias úteis válidos anteriores (shift(1): NÃO
    /// inclui o dia corrente).</item>
    /// <item><c>GapPct</c> — <c>abs(open(09:30) - close(D-1)) / abs(close(D-1))</c>
    /// (fração).</item>
    /// <item><c>RazaoVolume</c> — <c>VolumeMorning / VolumeBaseline</c>
    /// (0.0 se o baseline não é positivo).</item>
    /// <item><c>Motivo</c> — auditoria em pt-BR. Um de: <c>"OK"</c>,
    /// <c>"warmup-incompleto"</c>, <c>"volume-baixo"</c>, <c>"gap-baixo"</c>,
    /// <c>"dia-invalido"</c>.</item>
    /// </list>
    /// </summary>
    public class ResultadoClassificacao
    {
        public bool VvgPositivo { get; set; }
        public double VolumeMorning { get; set; }
        public double VolumeBaseline { get; set; }
        public double GapPct { get; set; }
        public double RazaoVolume { get; set; }
        public string Motivo { get; set; }
    }

    /// <summary>
    /// Classificador VVG stateful por dia útil (R1). Tradução literal de
    /// <c>_ClassificadorVvgModelo</c> (caos/estrategias_modelo/vvg.py),
    /// que por sua vez espelha o classificador de produção
    /// <c>VvgClassifier</c> (vvg_classifier.py).
    ///
    /// Consome barras OHLCV de minuto via <see cref="OnBarra"/> (em ordem
    /// cronológica) e devolve um <see cref="ResultadoClassificacao"/>
    /// exatamente na barra em que a janela morning [09:30, 10:00) NY de um
    /// dia válido fecha (primeira barra com hora >= 10:00 NY). Em todas as
    /// outras barras (e em dias de fim de semana) devolve <c>null</c>.
    ///
    /// Estado mantido (todo determinístico — função apenas das barras já
    /// vistas, sem random, sem I/O, sem relógio real):
    /// <list type="bullet">
    /// <item><c>_historico</c> — fila rolling (capacidade =
    /// <c>nDiasBaseline</c>) de pares (data, VolumeMorning) dos últimos N
    /// dias úteis válidos. O baseline é a média da componente de volume.
    /// O dia corrente só entra na sua finalização (transição de dia) —
    /// shift(1) semântico, anti look-ahead.</item>
    /// <item><c>_closeDMenos1</c> — close de fim de RTH do último dia útil
    /// válido anterior. Usado no gap.</item>
    /// <item>Acumuladores do dia corrente.</item>
    /// </list>
    ///
    /// Regra de warmup (R1.4): enquanto o histórico tiver menos de
    /// <c>nDiasBaseline</c> dias OU ainda não houver close do dia anterior,
    /// a classificação devolve <c>VvgPositivo = false</c> com motivo
    /// <c>"warmup-incompleto"</c> (nunca emite sinal sob incerteza
    /// estatística).
    /// </summary>
    public class EstrategiaVvgClassifierLogica
    {
        // ------------------------------------------------------------------
        // Constantes congeladas (espelham vvg_classifier.py / vvg.py)
        // ------------------------------------------------------------------

        /// <summary>
        /// Número mínimo de barras de minuto que um dia precisa ter para
        /// ser contado como dia útil válido (constante herdada do Spec 4 —
        /// Decisão 2026-05-26-01). Pregão regular MNQ ~= 1380 barras;
        /// abertura noturna de fim de semana no Globex tem ~120-300 barras.
        /// O limiar 300 descarta sessões truncadas. 300 barras ~= os 300
        /// minutos de 09:30 a 14:30 NY — qualquer dia que efetivamente
        /// alcança o horário de entrada da estratégia (14:30 NY) já
        /// satisfaz o limiar. Espelha <c>MIN_BARRAS_DIA_VALIDO</c> (Python).
        /// </summary>
        public const int MIN_BARRAS_DIA_VALIDO = 300;

        // Janela morning [09:30, 10:00) NY: mede VolumeMorning e captura o
        // open de referência do gap. TimeSpan (não const, que não admite
        // TimeSpan) espelhando HORA_MORNING_INICIO / HORA_MORNING_FIM.
        private static readonly TimeSpan HORA_MORNING_INICIO = new TimeSpan(9, 30, 0);
        private static readonly TimeSpan HORA_MORNING_FIM = new TimeSpan(10, 0, 0);

        // Sessão RTH [09:30, 16:00) NY. Captura o close de fim de RTH
        // (close(D-1) do gap). Espelha HORA_RTH_INICIO / HORA_RTH_FIM.
        private static readonly TimeSpan HORA_RTH_INICIO = new TimeSpan(9, 30, 0);
        private static readonly TimeSpan HORA_RTH_FIM = new TimeSpan(16, 0, 0);

        // Fuso do RTH do MNQ. No Windows, "Eastern Standard Time" cobre EST
        // e EDT (DST resolvido pela biblioteca, sem offset hardcoded).
        // Equivale a zoneinfo.ZoneInfo("America/New_York") do lado Python.
        private static readonly TimeZoneInfo FusoNovaYork =
            TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        // ------------------------------------------------------------------
        // Parâmetros congelados consumidos (os três campos de ParametrosVvg)
        // ------------------------------------------------------------------

        private readonly double _multiplicadorVolume;
        private readonly double _thresholdGapPct;
        private readonly int _nDiasBaseline;

        // ------------------------------------------------------------------
        // Estado mutável (espelha os atributos de _ClassificadorVvgModelo)
        // ------------------------------------------------------------------

        // Histórico rolling: fila de (data, VolumeMorning). A capacidade
        // máxima é imposta manualmente (descarte do mais antigo quando
        // Count > nDiasBaseline), replicando o maxlen do deque Python.
        private readonly Queue<KeyValuePair<DateTime, double>> _historico;

        // close de fim de RTH do último dia útil válido (close(D-1)).
        // null = ainda não capturado (espelha Optional[float] None).
        private double? _closeDMenos1;

        // Estado do dia corrente. null = nenhum dia iniciado ainda.
        private DateTime? _diaCorrente;
        private double _volumeMorningAtual;
        private double? _openDiaAtual;
        private double? _closeRthCorrente;
        private int _barrasDiaCorrente;
        private bool _morningClassificada;

        // ------------------------------------------------------------------
        // Construtores
        // ------------------------------------------------------------------

        /// <summary>
        /// Construtor primário (sem dependência de <c>ParametrosVvg</c>).
        /// Recebe diretamente os três valores que o classificador consome.
        /// Espelha <c>_ClassificadorVvgModelo.__init__</c>.
        /// </summary>
        /// <param name="multiplicadorVolume">
        /// Multiplicador de volume congelado. <c>VvgPositivo</c> exige
        /// <c>VolumeMorning &gt;= multiplicadorVolume * VolumeBaseline</c>.
        /// </param>
        /// <param name="thresholdGapPct">
        /// Threshold de gap congelado (fração). <c>VvgPositivo</c> exige
        /// <c>GapPct &gt;= thresholdGapPct</c>.
        /// </param>
        /// <param name="nDiasBaseline">
        /// Janela do baseline rolling de volume, em dias úteis válidos.
        /// Deve ser &gt;= 1.
        /// </param>
        public EstrategiaVvgClassifierLogica(
            double multiplicadorVolume, double thresholdGapPct, int nDiasBaseline)
        {
            if (nDiasBaseline < 1)
                throw new ArgumentException(
                    "nDiasBaseline deve ser >= 1; recebido " + nDiasBaseline);

            _multiplicadorVolume = multiplicadorVolume;
            _thresholdGapPct = thresholdGapPct;
            _nDiasBaseline = nDiasBaseline;

            _historico = new Queue<KeyValuePair<DateTime, double>>();
            _closeDMenos1 = null;
            _diaCorrente = null;
            _volumeMorningAtual = 0.0;
            _openDiaAtual = null;
            _closeRthCorrente = null;
            _barrasDiaCorrente = 0;
            _morningClassificada = false;
        }

        /// <summary>
        /// Construtor de conveniência que aceita a struct
        /// <see cref="ParametrosVvg"/> (definida em
        /// EstrategiaVvgLateSessionLogica.cs, Tarefa 6) e encaminha apenas
        /// os três campos consumidos. Usado pela Tarefa 10 para injetar os
        /// parâmetros congelados sem duplicar literais. O classificador
        /// nunca constrói a struct — apenas lê
        /// <c>MultiplicadorVolume</c>, <c>ThresholdGapPct</c> e
        /// <c>NDiasBaseline</c> — então o acoplamento é mínimo.
        /// </summary>
        public EstrategiaVvgClassifierLogica(ParametrosVvg p)
            : this(p.MultiplicadorVolume, p.ThresholdGapPct, p.NDiasBaseline)
        {
        }

        // ------------------------------------------------------------------
        // API pública
        // ------------------------------------------------------------------

        /// <summary>
        /// Processa uma barra OHLCV de minuto e devolve o resultado quando a
        /// janela morning fecha. Tradução literal de
        /// <c>_ClassificadorVvgModelo.on_barra</c>.
        ///
        /// Devolve um <see cref="ResultadoClassificacao"/> apenas na
        /// primeira barra de um dia cuja hora (NY) é &gt;= 10:00. Em
        /// qualquer outra barra — e em dias de fim de semana — devolve
        /// <c>null</c>.
        ///
        /// Observação: <paramref name="high"/> e <paramref name="low"/>
        /// fazem parte do contrato OHLCV da barra mas NÃO são usados pelo
        /// classificador (espelha o lado Python, que recebe a barra inteira
        /// e lê apenas open/close/volume).
        /// </summary>
        public ResultadoClassificacao OnBarra(
            DateTime timestampUtc,
            double open,
            double high,
            double low,
            double close,
            double volume)
        {
            DateTime tsNy = ParaNovaYork(timestampUtc);
            DateTime dia = tsNy.Date;
            TimeSpan hora = tsNy.TimeOfDay;
            double openBarra = open;
            double closeBarra = close;
            double volumeBarra = volume;

            // 1. Transição de dia (NY).
            if (_diaCorrente == null)
            {
                IniciarDia(dia);
            }
            else if (dia != _diaCorrente.Value)
            {
                // Finaliza o dia anterior (atualiza baseline e close(D-1))
                // ANTES de iniciar o novo dia — garante shift(1).
                FinalizarDia();
                IniciarDia(dia);
            }

            // 2. Acumulação do dia corrente.
            _barrasDiaCorrente += 1;

            // 2a. close corrente de RTH (vira close(D-1) na finalização).
            if (HORA_RTH_INICIO <= hora && hora < HORA_RTH_FIM)
            {
                _closeRthCorrente = closeBarra;
            }

            // 2b. janela morning [09:30, 10:00): acumula volume e captura open.
            if (HORA_MORNING_INICIO <= hora && hora < HORA_MORNING_FIM)
            {
                if (_openDiaAtual == null)
                {
                    _openDiaAtual = openBarra;
                }
                _volumeMorningAtual += volumeBarra;
            }

            // 3. Primeira barra >= 10:00: classifica.
            if ((!_morningClassificada) && (hora >= HORA_MORNING_FIM))
            {
                _morningClassificada = true;
                return Classificar(dia);
            }

            return null;
        }

        // ------------------------------------------------------------------
        // Helpers internos (espelham os métodos privados de _ClassificadorVvgModelo)
        // ------------------------------------------------------------------

        /// <summary>Reseta os acumuladores para um novo dia (NY).</summary>
        private void IniciarDia(DateTime dia)
        {
            _diaCorrente = dia;
            _volumeMorningAtual = 0.0;
            _openDiaAtual = null;
            _closeRthCorrente = null;
            _barrasDiaCorrente = 0;
            _morningClassificada = false;
        }

        /// <summary>
        /// Fecha o dia corrente: atualiza baseline e close(D-1) se o dia for
        /// válido. Aplica o filtro de dia útil (sábado/domingo) e o limiar
        /// <see cref="MIN_BARRAS_DIA_VALIDO"/>. shift(1) é garantido porque
        /// este método roda na transição de dia, ANTES de o novo dia ser
        /// classificado. Espelha <c>_finalizar_dia</c>.
        /// </summary>
        private void FinalizarDia()
        {
            if (_diaCorrente == null)
            {
                return;
            }

            // weekday() < 5 (Python: seg=0..sex=4) == não-sábado e não-domingo.
            DayOfWeek dow = _diaCorrente.Value.DayOfWeek;
            bool diaUtil = dow != DayOfWeek.Saturday && dow != DayOfWeek.Sunday;
            bool temBarras = _barrasDiaCorrente >= MIN_BARRAS_DIA_VALIDO;
            if (!(diaUtil && temBarras))
            {
                return;
            }

            // close de fim de RTH vira close(D-1) do próximo dia válido.
            if (_closeRthCorrente != null)
            {
                _closeDMenos1 = _closeRthCorrente;
            }

            // Entra no baseline somente se houve janela morning real (open
            // capturado em [09:30, 10:00)). Evita poluir o baseline com 0.0
            // de dias sem morning.
            if (_openDiaAtual != null)
            {
                _historico.Enqueue(new KeyValuePair<DateTime, double>(
                    _diaCorrente.Value, _volumeMorningAtual));

                // Descarte do mais antigo quando excede a capacidade
                // (replica o maxlen=nDiasBaseline do deque Python).
                while (_historico.Count > _nDiasBaseline)
                {
                    _historico.Dequeue();
                }
            }
        }

        /// <summary>
        /// Média do <c>VolumeMorning</c> no histórico rolling (0.0 se vazio).
        /// Loop explícito (sem LINQ Average) para mapear 1:1 ao
        /// <c>_media_baseline</c> Python — portabilidade literal.
        /// </summary>
        private double MediaBaseline()
        {
            if (_historico.Count == 0)
            {
                return 0.0;
            }
            double soma = 0.0;
            foreach (KeyValuePair<DateTime, double> entrada in _historico)
            {
                soma += entrada.Value;
            }
            return soma / _historico.Count;
        }

        /// <summary>
        /// Classifica o dia corrente no fechamento da janela morning.
        /// Devolve <c>null</c> para sábado/domingo. Para dias úteis, aplica
        /// warmup (R1.4) e a regra R1.2. Espelha <c>_classificar</c>.
        /// </summary>
        private ResultadoClassificacao Classificar(DateTime dia)
        {
            // Sábado/domingo: dia inválido -> sem classificação.
            DayOfWeek dow = dia.DayOfWeek;
            if (dow == DayOfWeek.Saturday || dow == DayOfWeek.Sunday)
            {
                return null;
            }

            // Dia útil sem janela morning real (gap de dados em 09:30-10:00):
            // estruturalmente inválido para o VVG.
            if (_openDiaAtual == null)
            {
                return new ResultadoClassificacao
                {
                    VvgPositivo = false,
                    VolumeMorning = 0.0,
                    VolumeBaseline = MediaBaseline(),
                    GapPct = 0.0,
                    RazaoVolume = 0.0,
                    Motivo = "dia-invalido"
                };
            }

            double volumeMorning = _volumeMorningAtual;
            double volumeBaseline = MediaBaseline();

            // Warmup (R1.4): histórico incompleto OU sem close do dia anterior.
            bool warmupIncompleto =
                _historico.Count < _nDiasBaseline
                || _closeDMenos1 == null;
            if (warmupIncompleto)
            {
                double gapWarmup = 0.0;
                if (_closeDMenos1 != null && _closeDMenos1.Value != 0.0)
                {
                    gapWarmup = Math.Abs(_openDiaAtual.Value - _closeDMenos1.Value)
                        / Math.Abs(_closeDMenos1.Value);
                }
                return new ResultadoClassificacao
                {
                    VvgPositivo = false,
                    VolumeMorning = volumeMorning,
                    VolumeBaseline = volumeBaseline,
                    GapPct = gapWarmup,
                    RazaoVolume = 0.0,
                    Motivo = "warmup-incompleto"
                };
            }

            // Gap (R1.1). close(D-1) garantidamente não-null aqui.
            double closeAnterior = _closeDMenos1.Value;
            double gapPct;
            if (closeAnterior == 0.0)
            {
                // Defensivo: close zerado tornaria o gap indefinido.
                gapPct = 0.0;
            }
            else
            {
                gapPct = Math.Abs(_openDiaAtual.Value - closeAnterior)
                    / Math.Abs(closeAnterior);
            }

            double razaoVolume = 0.0;
            if (volumeBaseline > 0.0)
            {
                razaoVolume = volumeMorning / volumeBaseline;
            }

            // R1.2: vvg_positivo = (volume) AND (gap).
            bool condVolume = volumeMorning >= _multiplicadorVolume * volumeBaseline;
            bool condGap = gapPct >= _thresholdGapPct;

            bool vvgPositivo;
            string motivo;
            if (condVolume && condGap)
            {
                vvgPositivo = true;
                motivo = "OK";
            }
            else if (!condVolume)
            {
                vvgPositivo = false;
                motivo = "volume-baixo";
            }
            else
            {
                // volume OK, mas gap insuficiente.
                vvgPositivo = false;
                motivo = "gap-baixo";
            }

            return new ResultadoClassificacao
            {
                VvgPositivo = vvgPositivo,
                VolumeMorning = volumeMorning,
                VolumeBaseline = volumeBaseline,
                GapPct = gapPct,
                RazaoVolume = razaoVolume,
                Motivo = motivo
            };
        }

        // ------------------------------------------------------------------
        // Acessores (testes / debug) — espelham as @property Python
        // ------------------------------------------------------------------

        /// <summary>Quantidade de dias úteis válidos atualmente no baseline.</summary>
        public int DiasNoBaseline
        {
            get { return _historico.Count; }
        }

        /// <summary>close de fim de RTH do último dia útil válido (close(D-1)).</summary>
        public double? CloseDiaAnterior
        {
            get { return _closeDMenos1; }
        }

        // ------------------------------------------------------------------
        // Conversão de fuso
        // ------------------------------------------------------------------

        /// <summary>
        /// Converte um timestamp UTC para horário de Nova York (DST
        /// automático). Espelho de <c>_para_ny</c>. Coage o
        /// <see cref="DateTimeKind"/> para <c>Utc</c> antes de converter —
        /// aceita tanto barras já marcadas como UTC quanto barras com kind
        /// <c>Unspecified</c> (assumidas UTC), espelhando a convenção
        /// leniente do lado Python.
        /// </summary>
        private static DateTime ParaNovaYork(DateTime timestampUtc)
        {
            DateTime utc = DateTime.SpecifyKind(timestampUtc, DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, FusoNovaYork);
        }
    }
}
