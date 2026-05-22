"""Pacote ``caos.ninjascript_modelo`` — espelho Python do núcleo C# (Spec 3).

Reimplementação fiel da **lógica decisória pura** dos componentes C# do
Spec 3 (``Cerberus_CSharp``, ``Trailing_3_Fases``, ``MfeMaeTracker``) em
Python puro, sem dependência do runtime do NinjaTrader 8.

A motivação é estritamente operacional: no Spec 3, o NT8 compila os
``.cs`` via NinjaScript Editor (F5), o que impede execução de testes
automatizados em CI sem instalar Visual Studio + .NET SDK + NUnit.
Em vez disso, este pacote permite exercitar Properties 16, 17 e 18 via
:mod:`hypothesis`. As Properties são consideradas válidas para o C# se
e somente se forem válidas para a porta Python aqui — qualquer
divergência futura entre as duas é tratada como veto técnico em
revisão de código.

Cada módulo tem 1:1 correspondência com seu arquivo C#:

- :mod:`caos.ninjascript_modelo.cerberus`    ↔ ``04_CODIGO/ninjascript/Cerberus.cs``
- :mod:`caos.ninjascript_modelo.trailing`    ↔ ``04_CODIGO/ninjascript/TrailingTresFases.cs``
- :mod:`caos.ninjascript_modelo.mfe_mae`     ↔ ``04_CODIGO/ninjascript/MfeMaeTracker.cs``

Convenções:

- Identificadores em snake_case Python (``autorizar_entrada``), mas a
  semântica reproduz exatamente o equivalente C# em PascalCase.
- Toda função pública carrega docstring com referência ao requirement
  do Spec 3 que ela cobre (R3.1, R4.5, R5.4, ...).
- Datas/timestamps em UTC, mesma convenção do Spec 1.
"""

from caos.ninjascript_modelo.cerberus import CerberusModelo
from caos.ninjascript_modelo.mfe_mae import (
    DirecaoTradeMfeMae,
    MfeMaeModelo,
    TradeMfeMae,
)
from caos.ninjascript_modelo.trailing import (
    DirecaoTrade,
    FaseTrailing,
    TrailingModelo,
)

__all__ = [
    "CerberusModelo",
    "DirecaoTrade",
    "DirecaoTradeMfeMae",
    "FaseTrailing",
    "MfeMaeModelo",
    "TradeMfeMae",
    "TrailingModelo",
]
