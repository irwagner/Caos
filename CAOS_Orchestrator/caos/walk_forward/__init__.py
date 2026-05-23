"""Pacote ``caos.walk_forward``.

Pipeline Python de Walk-Forward sobre dados do MNQ (Spec 2). Este pacote é
desenvolvido em camadas independentes (models → data_reader → janelas →
runner → metricas → engine → relatorio → CLI) e é consumido pelo Conselho
do Spec 1 como evidência de Debate (Resultado_Walk_Forward → NotaZettel em
``Decisoes_do_Conselho``).

A Task 1 expõe os modelos Pydantic em :mod:`caos.walk_forward.models`.
A Task 2 acrescenta :mod:`caos.walk_forward.data_reader` (leitor de CSVs
do MNQ com schema rígido e integração com Skill_Data_Integrity).
A Task 3 acrescenta :mod:`caos.walk_forward.janelas` (gerador
determinístico de :class:`JanelaWF`).
A Task 4 acrescenta :mod:`caos.walk_forward.runner` (BacktestRunner +
detecção de look-ahead via :class:`BarrasTesteIterator`).
A Task 5 acrescenta :mod:`caos.walk_forward.metricas`
(:class:`Trade` específico do MetricasCalculator e a fachada
:class:`MetricasCalculator`). Para evitar colisão com
:class:`caos.walk_forward.runner.Trade` (modelo mínimo emitido pela
Estrategia), o ``Trade`` do MetricasCalculator é exposto via importação
explícita ``from caos.walk_forward.metricas import Trade``; o ``Trade``
re-exportado deste pacote permanece o do Runner.
A Task 6 acrescenta :mod:`caos.walk_forward.engine`
(:class:`WalkForwardEngine`) que orquestra integridade → janelas →
execução por janela → agregação, abortando se >30% das janelas
falharem (R10.2).
A Task 7 acrescenta :mod:`caos.walk_forward.relatorio`
(:class:`RelatorioWriter` + :func:`escrever_relatorio`) que serializa
:class:`ResultadoWalkForward` em JSON canônico + Markdown com
frontmatter compatível com :class:`caos.models.NotaZettel` (área
``Decisoes_do_Conselho``) e, opcionalmente, integra com
:class:`caos.council_recorder.CouncilRecorder`.
Os demais submódulos serão adicionados nas tasks subsequentes.
"""

from caos.walk_forward.data_reader import (
    COLUNAS_OBRIGATORIAS,
    COLUNAS_NUMERICAS,
    DadosForaDeOrdemError,
    ManifestoInvalidoError,
    SchemaInvalidoError,
    SkillDataReader,
    WalkForwardDataReaderError,
)
from caos.walk_forward.engine import (
    FonteDados,
    LIMIAR_TAXA_FALHAS,
    METRICAS_AGREGAVEIS,
    WalkForwardEngine,
)
from caos.walk_forward.fontes_dados import (
    DIR_RAIZ_MNQ_RELATIVO,
    FonteCsv,
    FonteDadosError,
    GRANULARIDADES_VALIDAS,
    SERIES_VALIDAS,
    SerieTrade,
    listar_contratos_disponiveis,
    listar_csvs_existentes,
    resolver_fonte,
    validar_contrato,
    validar_granularidade,
    validar_serie,
)
from caos.walk_forward.janelas import (
    EntradaDados,
    JanelaGenerator,
    gerar_janelas,
)
from caos.walk_forward.metricas import (
    DIAS_UTEIS_POR_ANO,
    LadoTrade,
    MetricasCalculator,
)
from caos.walk_forward.caracterizacao import (
    LAGS_AUTOCORRELACAO_MINUTOS,
    LIMIAR_GAP_SIGNIFICATIVO_PCT,
    RelatorioCaracterizacao,
    SumarioAutocorrelacao,
    SumarioGaps,
    SumarioRangeDiario,
    SumarioVolatilidadeIntradia,
    calcular_autocorrelacao,
    calcular_gaps,
    calcular_range_diario,
    calcular_volatilidade_intradia,
    caracterizar_serie,
)
from caos.walk_forward.models import (
    ConfiguracaoWalkForward,
    CustosOperacionais,
    JanelaWF,
    ResultadoJanela,
    ResultadoWalkForward,
    StatusJanela,
    StatusWalkForward,
    Granularidade,
)
from caos.walk_forward.normalizador_nt8 import (
    FUSO_DEFAULT_NT8,
    NormalizadorNt8Error,
    ResultadoNormalizacao,
    detectar_destino_canonico,
    normalizar_arquivo,
    varrer_e_normalizar,
)
from caos.walk_forward.relatorio import (
    AREA_NOTA_ZETTEL,
    AGENTE_AUTOR_PADRAO,
    MODELO_ATHENA_PADRAO,
    NOME_ARQUIVO_JSON,
    NOME_ARQUIVO_MD,
    SUBDIR_RELATORIOS,
    RelatorioWriter,
    escrever_relatorio,
)
from caos.walk_forward.runner import (
    BacktestRunner,
    BarrasTesteIterator,
    Estrategia,
    LookAheadException,
    Trade,
)

__all__ = [
    # Modelos (Task 1)
    "ConfiguracaoWalkForward",
    "CustosOperacionais",
    "JanelaWF",
    "ResultadoJanela",
    "ResultadoWalkForward",
    "StatusJanela",
    "StatusWalkForward",
    "Granularidade",
    # Data Reader (Task 2)
    "COLUNAS_OBRIGATORIAS",
    "COLUNAS_NUMERICAS",
    "DadosForaDeOrdemError",
    "ManifestoInvalidoError",
    "SchemaInvalidoError",
    "SkillDataReader",
    "WalkForwardDataReaderError",
    # JanelaGenerator (Task 3)
    "EntradaDados",
    "JanelaGenerator",
    "gerar_janelas",
    # BacktestRunner (Task 4)
    "BacktestRunner",
    "BarrasTesteIterator",
    "Estrategia",
    "LookAheadException",
    "Trade",
    # MetricasCalculator (Task 5)
    "DIAS_UTEIS_POR_ANO",
    "LadoTrade",
    "MetricasCalculator",
    # Caracterizacao do instrumento (Decisao 2026-05-23-01 item 3)
    "LAGS_AUTOCORRELACAO_MINUTOS",
    "LIMIAR_GAP_SIGNIFICATIVO_PCT",
    "RelatorioCaracterizacao",
    "SumarioAutocorrelacao",
    "SumarioGaps",
    "SumarioRangeDiario",
    "SumarioVolatilidadeIntradia",
    "calcular_autocorrelacao",
    "calcular_gaps",
    "calcular_range_diario",
    "calcular_volatilidade_intradia",
    "caracterizar_serie",
    # WalkForwardEngine (Task 6)
    "FonteDados",
    "LIMIAR_TAXA_FALHAS",
    "METRICAS_AGREGAVEIS",
    "WalkForwardEngine",
    # FontesDados (refator pos-coleta de dados reais — Spec 5)
    "DIR_RAIZ_MNQ_RELATIVO",
    "FonteCsv",
    "FonteDadosError",
    "GRANULARIDADES_VALIDAS",
    "SERIES_VALIDAS",
    "SerieTrade",
    "listar_contratos_disponiveis",
    "listar_csvs_existentes",
    "resolver_fonte",
    "validar_contrato",
    "validar_granularidade",
    "validar_serie",
    # Normalizador NT8 (importação de dados reais — pos-export do usuário)
    "FUSO_DEFAULT_NT8",
    "NormalizadorNt8Error",
    "ResultadoNormalizacao",
    "detectar_destino_canonico",
    "normalizar_arquivo",
    "varrer_e_normalizar",
    # RelatorioWriter (Task 7)
    "AREA_NOTA_ZETTEL",
    "AGENTE_AUTOR_PADRAO",
    "MODELO_ATHENA_PADRAO",
    "NOME_ARQUIVO_JSON",
    "NOME_ARQUIVO_MD",
    "SUBDIR_RELATORIOS",
    "RelatorioWriter",
    "escrever_relatorio",
]
