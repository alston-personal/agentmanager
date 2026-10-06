import io
import unittest
from PIL import Image

from scripts.invoice_ocr_failure_diff import classify_field
from services.invoice_intake.template_ocr import (
    anchor_row_reocr,
    choose_dual_model_amounts,
    choose_layout_amounts,
    choose_reocr_amounts,
)


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


    def test_layout_amounts_use_anchor_geometry_and_arithmetic(self):
        evidence=[
            {"text":"銷售額合計","confidence":0.99,"box":[[10,10],[60,10],[60,30],[10,30]]},
            {"text":"1546","confidence":0.94,"box":[[90,10],[130,10],[130,30],[90,30]]},
            {"text":"營業稅","confidence":0.99,"box":[[10,40],[60,40],[60,60],[10,60]]},
            {"text":"77","confidence":0.91,"box":[[90,40],[110,40],[110,60],[90,60]]},
            {"text":"總計","confidence":0.99,"box":[[10,70],[60,70],[60,90],[10,90]]},
            {"text":"1623","confidence":0.93,"box":[[90,70],[130,70],[130,90],[90,90]]},
        ]
        values,meta=choose_layout_amounts(evidence)
        self.assertEqual(values["amount_before_tax"],1546)
        self.assertEqual(values["tax_amount"],77)
        self.assertEqual(values["total_amount"],1623)
        self.assertEqual(meta["validation"],"subtotal_plus_tax_equals_total")

    def test_layout_amounts_never_derives_missing_total(self):
        evidence=[
            {"text":"銷售額合計","confidence":0.99,"box":[[10,10],[60,10],[60,30],[10,30]]},
            {"text":"1546","confidence":0.94,"box":[[90,10],[130,10],[130,30],[90,30]]},
            {"text":"營業稅","confidence":0.99,"box":[[10,40],[60,40],[60,60],[10,60]]},
            {"text":"77","confidence":0.91,"box":[[90,40],[110,40],[110,60],[90,60]]},
        ]
        values,_=choose_layout_amounts(evidence)
        self.assertIsNone(values["total_amount"])


    def test_dual_model_ensemble_recovers_complementary_real_benchmark_errors(self):
        # Public RP sample: small kept total but misread subtotal/tax;
        # medium read subtotal/tax but dropped the leading 1 from total.
        small_text="1506\n22\n1623"
        medium_text="1546\n77\n623"
        subtotal,tax,total,observed=choose_dual_model_amounts(small_text,medium_text)
        self.assertTrue(observed)
        self.assertEqual((subtotal,tax,total),(1546,77,1623))

    def test_dual_model_ensemble_never_synthesizes_unseen_total(self):
        subtotal,tax,total,observed=choose_dual_model_amounts("1546\n77","")
        self.assertFalse(observed)
        self.assertIsNone(total)

    def test_anchor_row_reocr_recovers_amount_rows_from_preprocessed_crops(self):
        class Result:
            def __init__(self,text):
                self.txts=[text]
                self.scores=[0.96]
                self.boxes=[[[1,1],[20,1],[20,10],[1,10]]]

        values=iter(["1546","1546","77","77","1623","1623"])
        def engine(_image):
            return Result(next(values))

        page=Image.new("RGB",(500,300),"white")
        buf=io.BytesIO()
        page.save(buf,format="PNG")
        evidence=[
            {"text":"銷售額合計","confidence":0.99,"box":[[20,40],[100,40],[100,60],[20,60]]},
            {"text":"營業稅","confidence":0.99,"box":[[20,100],[100,100],[100,120],[20,120]]},
            {"text":"總計","confidence":0.99,"box":[[20,160],[100,160],[100,180],[20,180]]},
        ]
        candidates=anchor_row_reocr(engine,buf.getvalue(),evidence)
        chosen,meta=choose_reocr_amounts(candidates)
        self.assertEqual(chosen["amount_before_tax"],1546)
        self.assertEqual(chosen["tax_amount"],77)
        self.assertEqual(chosen["total_amount"],1623)
        self.assertEqual(meta["validation"],"subtotal_plus_tax_equals_total")

    def test_reocr_does_not_derive_missing_value_from_two_fields(self):
        candidates={
            "amount_before_tax":[{"value":1546,"votes":2,"best_confidence":0.97}],
            "tax_amount":[{"value":77,"votes":2,"best_confidence":0.96}],
            "total_amount":[],
        }
        chosen,_=choose_reocr_amounts(candidates)
        self.assertIsNone(chosen["total_amount"])

if __name__=="__main__":
    unittest.main()
