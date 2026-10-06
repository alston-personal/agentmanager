import unittest

from scripts.invoice_ocr_failure_diff import classify_field


class InvoiceOCRFailureDiffTests(unittest.TestCase):
    def test_exact_raw_token_but_parser_empty_is_parser_or_layout_miss(self):
        evidence=[{"text":"24500","confidence":0.91,"box":[[1,1],[2,1],[2,2],[1,2]]}]
        result=classify_field("amount_before_tax",24500,evidence,{"amount_before_tax":None})
        self.assertEqual(result["category"],"parser_or_layout_miss")

    def test_one_digit_loss_is_recognizer_near_miss(self):
        evidence=[{"text":"623","confidence":0.66,"box":[[1,1],[2,1],[2,2],[1,2]]}]
        result=classify_field("total_amount",1623,evidence,{"total_amount":None})
        self.assertEqual(result["category"],"recognizer_near_miss")

    def test_absent_value_is_detector_or_recognizer_miss(self):
        evidence=[{"text":"營業稅","confidence":0.98,"box":None}]
        result=classify_field("tax_amount",1225,evidence,{"tax_amount":None})
        self.assertEqual(result["category"],"detector_or_recognizer_miss")

    def test_correct_parser_wins(self):
        evidence=[]
        result=classify_field("seller_tax_id","16672215",evidence,{"seller_tax_id":"16672215"})
        self.assertEqual(result["category"],"parsed_correct")


if __name__=="__main__":
    unittest.main()
