from uuid import uuid4

from game_predictor_api.schemas.geometry_qualification import GridCorrectionCellSymbolPayload


def test_null_symbol_id_is_the_operators_cannot_tell() -> None:
    payload = GridCorrectionCellSymbolPayload.model_validate({"cellIndex": 3, "symbolId": None})

    domain = payload.to_domain()

    assert (domain.cell_index, domain.symbol_id) == (3, None)


def test_symbol_id_stays_required() -> None:
    symbol_id = uuid4()
    payload = GridCorrectionCellSymbolPayload.model_validate(
        {"cellIndex": 1, "symbolId": str(symbol_id)}
    )

    assert payload.to_domain().symbol_id == symbol_id
