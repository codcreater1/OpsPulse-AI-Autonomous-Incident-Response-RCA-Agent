"""Tiny synthetic service with an intentional bug, used by scripts/demo.py."""

STOCK = {"apple": 3, "pear": 0}


def available(sku):
    return STOCK.get(sku)


def reserve(sku, quantity):
    if available(sku) >= quantity:
        STOCK[sku] -= quantity
        return True
    return False
