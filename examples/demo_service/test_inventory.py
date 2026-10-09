from inventory import STOCK, reserve


def test_known_sku_is_reserved():
    STOCK["apple"] = 3
    assert reserve("apple", 2) is True and STOCK["apple"] == 1


def test_out_of_stock_sku_is_refused():
    assert reserve("pear", 1) is False


def test_unknown_sku_is_refused_instead_of_crashing():
    assert reserve("banana", 1) is False
