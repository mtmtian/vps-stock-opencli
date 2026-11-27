import unittest

from tools import yinnet_source


def listing(first_stock):
    return f"""
        <header>YINNET 新加坡 VPS</header>
        <script src="/cdn-cgi/challenge-platform/loader.js"></script>
        <h2>新加坡 | VPS ①</h2>
        <span>{first_stock}</span><p>起 $10.00 USD 月繳</p>
        <p>CPU：1核 內存：1GB 硬盤：10GB 帶寬：1000Mbps 流量：2000GB</p>
        <a href="/index.php?rp=/store/sgvps/sgvps1">選擇方案</a>
        <h2>新加坡 | VPS ②</h2><span>1 可用</span><p>起 $16.00 USD 月繳</p>
    """


class YinnetStockTests(unittest.TestCase):
    def test_second_plan_does_not_supply_first_plans_stock_or_price(self):
        row = yinnet_source.parse_listing(listing("0 可用"))
        self.assertEqual((row["available"], row["price"], row["quantity"]), (False, 10, 0))

    def test_normal_page_with_background_challenge_script_and_visible_challenge(self):
        self.assertTrue(yinnet_source.parse_listing(listing("2 可用"))["available"])
        self.assertIsNone(yinnet_source.parse_listing("Verify you are human" + listing("2 可用"))["available"])

    def test_conflicting_signals_and_explicit_negative_stock(self):
        for text, expected in (("2 可用 已售完", None), ("不可購買", False), ("not in stock", False)):
            with self.subTest(text=text):
                self.assertIs(yinnet_source.parse_listing(listing(text))["available"], expected)
