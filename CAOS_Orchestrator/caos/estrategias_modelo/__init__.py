"""Pacote ``caos.estrategias_modelo`` — espelhos Python das estratégias C# (Spec 4+).

Análogo conceitual a :mod:`caos.ninjascript_modelo` (Spec 3): cada
módulo aqui é uma reimplementação fiel de uma classe de **lógica pura**
em C#, usada exclusivamente para validar paridade Python ↔ C# via
:mod:`hypothesis`.

A regra arquitetural é a mesma do Spec 3: a fonte da verdade
**operacional** é o C# (que é o que roda no NT8); a fonte da verdade
**semântica** é o Python (testável em CI). Qualquer divergência entre
a implementação C# e a porta Python é tratada como veto técnico
durante revisão.

Módulos:

- :mod:`caos.estrategias_modelo.orb` ↔ ``04_CODIGO/ninjascript/EstrategiaORBLogica.cs``.
- :mod:`caos.estrategias_modelo.vvg` ↔ ``04_CODIGO/ninjascript/EstrategiaVvgLateSessionLogica.cs``
  + ``EstrategiaVvgClassifierLogica.cs`` (porta de referência da
  estratégia VVG Late-Session Reversal — Spec 5).

Strategies plugadas no Walk-Forward (Python "oficial") ficam em
:mod:`caos.walk_forward.estrategias` e são a referência canônica da
regra de decisão. Os espelhos aqui só existem para o teste de paridade.

Nota sobre ``vvg``: diferente de ``orb`` (que apenas delega para a
função canônica nesta fase), :class:`~caos.estrategias_modelo.vvg.VvgModeloCSharpPort`
**reimplementa** a lógica de forma independente — é um ground truth
paralelo, não um wrapper. Isso evita que a Property 11 (paridade) seja
tautológica.
"""

from caos.estrategias_modelo.orb import OrbModeloCSharpPort
from caos.estrategias_modelo.vvg import VvgModeloCSharpPort

__all__ = ["OrbModeloCSharpPort", "VvgModeloCSharpPort"]
