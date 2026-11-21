
from tools.customer_tools import (
    find_customer_by_id,
    find_customer_by_email,
    get_customer_support_tickets,
)

from tools.order_tools import (
    get_orders_for_customer,
    get_order_information,
    get_products_in_order,
)

from tools.shipping_tools import (
    get_shipments_for_order,
    track_shipment,
)

from tools.returns_tools import (
    get_returns_for_order,
    get_return_information,
)


# All 10 read-only tools
ALL_TOOLS = [
    find_customer_by_id,
    find_customer_by_email,
    get_customer_support_tickets,

    get_orders_for_customer,
    get_order_information,
    get_products_in_order,

    get_shipments_for_order,
    track_shipment,

    get_returns_for_order,
    get_return_information,
]
