"""Catálogo de Skills executáveis do orquestrador CAOS.

Este pacote concentra as Skills declaradas no Requirement 11 do
``requirements.md`` e detalhadas na seção 6 (Catálogo de Skills) do
``design.md``. Cada Skill encapsula uma ferramenta externa (terminal cmd,
Git, MSBuild, Web Search, leitor de CSV, inspetor de dados, cache de LLM,
controle de orçamento de tokens) sob uma interface tipada com timeout,
captura truncada de saída e auditoria estruturada.

Skills entregues pelas Tasks 5–8: ``Skill_Terminal``, ``Skill_Git``,
``Skill_Data_Inspector``, ``Skill_Data_Integrity``, ``Skill_LLM_Cache``,
``Skill_Token_Budget``, ``Skill_MSBuild``, ``Skill_Web_Search``.
"""
