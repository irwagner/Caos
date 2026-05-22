"""Espelho Python de ``EstrategiaORBLogica.cs`` (Spec 4 — Task 3).

Reimplementação fiel da função pura ``DecidirAcao`` do C#. Existe
exclusivamente para validar paridade Python ↔ C# via Property 19
(``test_orb_python_csharp_paridade.py``).

**Disciplina de divergência:** se em algum momento alguém otimizar a
função em C# (por exemplo, um early-exit antes do parsing de
timestamp), a porta aqui DEVE ser ajustada na mesma revisão. A Property
19 falha imediatamente em qualquer divergência de comportamento entre
:func:`caos.walk_forward.estrategias.orb_logica.decidir_acao` (Python
canônico) e :meth:`OrbModeloCSharpPort.decidir_acao` (Python que
espelha o C#).

Nesta primeira iteração, a porta C# é uma cópia byte-a-byte da função
Python canônica, então o espelho aqui simplesmente delega. Mantemos a
camada de indireção para que futuros descompassos sejam trivialmente
expressáveis sem mudar o teste.
"""

from __future__ import annotations

from caos.walk_forward.estrategias.orb_logica import (
    Barra,
    DecisaoORB,
    EstadoORB,
    ParametrosORB,
    decidir_acao,
)


class OrbModeloCSharpPort:
    """Porta Python da função C# ``EstrategiaORBLogica.DecidirAcao``.

    Em produção, esta classe é apenas um wrapper sobre
    :func:`decidir_acao`. Existe para que a Property 19 chame
    explicitamente o "lado C#" e o "lado Python canônico" como entidades
    distintas — assim, quando uma divergência for introduzida no
    futuro, o teste falha sem ambiguidade.
    """

    @staticmethod
    def decidir_acao(
        barra: Barra,
        estado: EstadoORB,
        parametros: ParametrosORB,
    ) -> DecisaoORB:
        """Reproduz fielmente ``EstrategiaORBLogica.DecidirAcao``.

        Atual: delega para :func:`decidir_acao` (são idênticos nesta
        iteração). Caso o C# seja modificado por otimização ou bugfix,
        esta função DEVE ser ajustada na mesma revisão para manter a
        Property 19 verde.
        """
        return decidir_acao(barra, estado, parametros)


__all__ = ["OrbModeloCSharpPort"]
