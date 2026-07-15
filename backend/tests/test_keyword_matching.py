from src.keyword_matching import contains_any_complete_phrase, contains_complete_phrase


def test_short_keyword_matches_only_complete_word() -> None:
    assert contains_complete_phrase("Servicio de conectividad LEO para sedes rurales", "LEO")
    assert not contains_complete_phrase("Puente en la provincia de Leoncio Prado", "LEO")


def test_phrase_requires_complete_words_and_tolerates_spacing() -> None:
    assert contains_complete_phrase("Implementación de RADIO   ENLACE digital", "radio enlace")
    assert not contains_complete_phrase("Implementación de radio enlazado", "radio enlace")


def test_matching_is_case_and_accent_insensitive() -> None:
    assert contains_complete_phrase("Órbita terrestre baja", "orbita")
    assert contains_any_complete_phrase("Internet satelital", ["fibra óptica", "satelital"])
