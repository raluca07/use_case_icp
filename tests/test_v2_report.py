from rdr.v2_report import API_NAMES, search_tasks


def test_api_inventory_and_train_dev_search_are_explicit():
    assert "gmail.show_inbox_threads" in API_NAMES
    assert "venmo.create_payment_request" in API_NAMES
    assert "file_system.create_file" in API_NAMES
    result = search_tasks()
    assert result["tasks_searched"] == 147
    assert result["matching_task"] is None
