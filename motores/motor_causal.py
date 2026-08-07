def limpiar_causa(texto: str) -> str:
    return texto.split("|", 1)[-1].strip()


def pregunta_inicial(efecto: str, causa: str) -> str:
    return (
        f"¿Por qué “{limpiar_causa(causa)}” afecta o provoca "
        f"el efecto “{efecto}”?"
    )


def pregunta_siguiente(respuesta_anterior: str) -> str:
    texto = respuesta_anterior.strip().rstrip(".")
    return f"¿Por qué {texto.lower()}?"


def validar_respuesta(respuesta: str) -> list[str]:
    errores = []
    texto = respuesta.strip()

    if len(texto) < 8:
        errores.append("La respuesta es demasiado breve.")

    if texto.lower() in {
        "porque falló",
        "porque fallo",
        "error humano",
        "falta de mantenimiento",
        "por desgaste",
    }:
        errores.append(
            "Describe el mecanismo o la condición concreta, "
            "no una categoría general."
        )

    return errores
