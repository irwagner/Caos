"""Configuração compartilhada da suíte de Property-Based Tests (Task 18).

Este ``conftest.py`` registra dois profiles de Hypothesis e ativa o
profile selecionado pela variável de ambiente ``HYPOTHESIS_PROFILE``:

- ``default`` (ativado quando a env var está ausente ou é
  ``"default"``): mantém ``max_examples=20`` como teto baseline para
  rodadas locais rápidas. Os testes individuais que declaram
  ``@settings(max_examples=N)`` continuam respeitando seu próprio ``N``
  porque ``@settings`` no teste tem precedência sobre o profile global.
- ``gate`` (ativado com ``HYPOTHESIS_PROFILE=gate``): eleva o teto
  para ``max_examples=100`` para corresponder ao gate de qualidade
  exigido pela Task 18 do spec. Testes individuais com
  ``@settings(max_examples=N)`` mais alto que 100 mantêm seu valor;
  testes sem ``@settings`` herdam 100.

``deadline=None`` é forçado em ambos os profiles porque vários testes
de propriedade do CAOS escrevem em ``tmp_path`` (I/O lento em Windows)
e estourariam o deadline default de 200ms.

``HealthCheck.function_scoped_fixture`` é suprimido porque a maioria
dos testes consome ``tmp_path_factory``/``tmp_path`` dentro de
``@given``, padrão idiomático aceito pelo time.

Notas de design (Task 18):

- Não alteramos os ``@settings(max_examples=...)`` existentes nos
  testes individuais — alguns deles foram dimensionados para 20-50
  casos por restrições de tempo de fixture. O profile ``gate`` apenas
  define o teto para testes que herdam do profile.
- ``derandomize=False`` no profile ``gate`` mantém shrinking habilitado
  e geração não-determinística entre runs (CI assina cada falha com a
  semente do Hypothesis para reproduzir).
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, Verbosity, settings

# ---------------------------------------------------------------------------
# Profile "default": baseline local (20 exemplos)
# ---------------------------------------------------------------------------

settings.register_profile(
    "default",
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

# ---------------------------------------------------------------------------
# Profile "gate": gate de qualidade do CAOS (100 exemplos, shrinking on)
# ---------------------------------------------------------------------------

settings.register_profile(
    "gate",
    max_examples=100,
    deadline=None,
    derandomize=False,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    verbosity=Verbosity.normal,
)

# ---------------------------------------------------------------------------
# Carga do profile via env var (default = "default")
# ---------------------------------------------------------------------------

_PROFILE_ATIVO = os.environ.get("HYPOTHESIS_PROFILE", "default")
settings.load_profile(_PROFILE_ATIVO)
