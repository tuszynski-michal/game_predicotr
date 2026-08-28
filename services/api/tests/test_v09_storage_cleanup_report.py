from scripts.report_v09_storage_cleanup import build_report


def test_storage_cleanup_report_is_deterministic_and_handles_missing_relations() -> None:
    report = build_report(
        label="after",
        rows=[
            {
                "relation_name": "image_board_search_documents",
                "exists": False,
                "table_bytes": 0,
                "index_bytes": 0,
                "total_bytes": 0,
            },
            {
                "relation_name": "image_board_search_fast_documents",
                "exists": True,
                "table_bytes": 100,
                "index_bytes": 25,
                "total_bytes": 125,
            },
        ],
    )

    assert report["label"] == "after"
    assert report["totalBytes"] == 125
    assert report["relations"] == {
        "image_board_search_documents": {
            "exists": False,
            "tableBytes": 0,
            "indexBytes": 0,
            "totalBytes": 0,
        },
        "image_board_search_fast_documents": {
            "exists": True,
            "tableBytes": 100,
            "indexBytes": 25,
            "totalBytes": 125,
        },
    }
