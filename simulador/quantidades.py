"""Quantidades de perguntas que o candidato pode escolher para a arguição."""

QUANTIDADES_PERGUNTAS: tuple[int, ...] = (5, 10, 15, 20, 30)


def quantidade_padrao(sugerida) -> int:
    """Usa a quantidade padrão do concurso quando ela é uma das opções; senão, 10."""
    return sugerida if isinstance(sugerida, int) and sugerida in QUANTIDADES_PERGUNTAS else 10
