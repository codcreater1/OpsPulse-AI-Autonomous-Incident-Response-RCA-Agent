"""Reproduces the production failure: an order for an unknown SKU."""

from inventory import reserve


def handle_order(order):
    return reserve(order["sku"], order["quantity"])


if __name__ == "__main__":
    print(handle_order({"sku": "banana", "quantity": 1}))
