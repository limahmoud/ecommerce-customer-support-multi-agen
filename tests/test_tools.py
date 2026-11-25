from tools import ALL_TOOLS


def test_all_tools_are_registered():
    assert len(ALL_TOOLS) == 9


def test_tool_names_are_unique():
    names = [current_tool.name for current_tool in ALL_TOOLS]

    assert len(names) == len(set(names))


def test_all_tools_have_descriptions():
    for current_tool in ALL_TOOLS:
        assert current_tool.description
        assert callable(current_tool.invoke)


def test_all_tools_are_read_only_customer_tools():
    expected_tools = {
        "get_my_profile",
        "get_customer_support_tickets",
        "get_orders_for_customer",
        "get_order_information",
        "get_products_in_order",
        "get_shipments_for_order",
        "track_shipment",
        "get_returns_for_order",
        "get_return_information",
    }

    actual_tools = {current_tool.name for current_tool in ALL_TOOLS}

    assert actual_tools == expected_tools
