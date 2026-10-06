import base64
import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image
from services.invoice_intake import vision_ocr as vision
from services.invoice_intake.invoice_core import Extraction, InvoiceStore, extract_invoice
from services.invoice_intake.template_ocr import seller_region_text, extract_template_invoice


def fixture():
    p = dict.fromkeys(vision.TEXT_FIELDS + vision.MONEY_FIELDS)
    p.update(invoice_number='AB12345678', invoice_date='2026-09-21', seller_name='測試商行',
             seller_tax_id='16908319', buyer_name='買方測試有限公司', buyer_tax_id='23040145', amount_before_tax=1000,
             tax_amount=50, total_amount=1050, needs_review=False, uncertain_fields=[],
             line_items=[{'description': '加工', 'quantity': 1000, 'unit_price': 1, 'amount': 1000}],
             stamp_text='測試商行 16908319', seller_address='測試地址')
    return p


def image_bytes():
    b=BytesIO()
    Image.new('RGB', (32, 24), 'white').save(b, format='PNG')
    return b.getvalue()


def legacy():
    f={k: fixture().get('seller_name' if k=='vendor_name' else k) for k in vision.CORE_FIELDS}
    f['vendor_name']='買方測試有限公司'
    return Extraction(f, {}, {'engine':'legacy'}, False)


class VisionTests(unittest.TestCase):
    def test_exact_original_bytes_and_prompt_sent(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({'output_text':json.dumps(fixture())}).encode()
        data=image_bytes()
        with patch.object(vision.urllib.request, 'urlopen', return_value=response) as call:
            result=vision.read_invoice(data, api_key='test-secret', model='configured-model')
        body=json.loads(call.call_args.args[0].data)
        self.assertEqual(base64.b64decode(body['input'][1]['data']),data)
        self.assertEqual(body['input'][0]['text'],vision.PROMPT)
        self.assertEqual(result['payload']['seller_address'],'測試地址')
        self.assertNotIn('test-secret',json.dumps(result))

    def test_invalid_payload_rejected(self):
        for bad in ([], {}, dict(fixture(), total_amount=True), dict(fixture(), line_items=[{}]),
                    dict(fixture(), needs_review='false')):
            with self.assertRaises(ValueError): vision.validate_payload(bad)

    def test_partial_payload_keeps_readable_fields(self):
        partial={
            'invoice_number':'EC55544057',
            'invoice_date':'2026-09-25',
            'amount_before_tax':24500,
            'tax_amount':1225,
            'total_amount':25725,
            'line_items':[{'description':'印刷品','quantity':24500,'unit_price':1,'amount':24500}],
            'needs_review':True,
            'uncertain_fields':['seller_name'],
        }
        vision.validate_payload(partial)
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({'output_text':json.dumps(partial)}).encode()
        with patch.object(vision.urllib.request, 'urlopen', return_value=response):
            result=vision.read_invoice(image_bytes(), api_key='test-secret', model='configured-model')
        payload=result['payload']
        self.assertEqual(payload['invoice_number'],'EC55544057')
        self.assertEqual(payload['total_amount'],25725)
        self.assertIsNone(payload['seller_name'])
        self.assertIsNone(payload['seller_tax_id'])
        self.assertEqual(payload['line_items'][0]['description'],'印刷品')


    def test_uncertain_values_are_preserved_but_invalid_values_are_rejected(self):
        p=fixture();p.update(invoice_date='2026-02-30', seller_tax_id='123', uncertain_fields=['seller_name'])
        f, issues=vision.validated_fields(p)
        self.assertIsNone(f['invoice_date']);self.assertIsNone(f['seller_tax_id'])
        self.assertEqual(f['vendor_name'], '測試商行')
        self.assertIn('vendor_name', issues)
        p=fixture();p['uncertain_fields']=['invoice_date','amount_before_tax','tax_amount','total_amount']
        f,issues=vision.validated_fields(p)
        self.assertEqual(f['invoice_date'],'2026-09-21')
        self.assertEqual((f['amount_before_tax'],f['tax_amount'],f['total_amount']),(1000,50,1050))
        p=fixture();p['tax_amount']=51
        f,issues=vision.validated_fields(p)
        self.assertIn('amount_sum_mismatch',issues)
        self.assertEqual(f['tax_amount'],51)  # validation must not rewrite the image reading

    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'primary','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':'test'})
    def test_primary_retains_details_comparison_and_requires_review(self):
        result={'payload':fixture(), 'image_sha256':'test', 'model':'test'}
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice',return_value=legacy()), \
             patch.object(vision,'read_invoice',return_value=result):
            with tempfile.TemporaryDirectory() as tmp:
                store=InvoiceStore(Path(tmp),data_scope='test')
                initial=store.ingest(image_bytes(),'test.png','image/png')
                store.process(initial['invoice_id'])
                persisted=store.get_invoice(initial['invoice_id'])
                self.assertEqual(persisted['fields']['vendor_name'],'買方測試有限公司')
                self.assertEqual(persisted['fields']['buyer_tax_id'],'23040145')
                self.assertEqual(persisted['status'],'needs_review')
                raw=persisted['recognition']
                self.assertEqual(raw['vision']['payload']['line_items'][0]['quantity'],1000)
                self.assertEqual(raw['vision']['field_trace']['buyer_tax_id']['value'],'23040145')
                self.assertEqual(raw['vision']['field_trace']['buyer_tax_id']['status'],'extracted')
                self.assertFalse(raw['comparison']['vendor_name']['equal'])
                self.assertEqual(raw['conflicts']['vendor_name']['vision'],'測試商行')
                self.assertEqual(raw['conflicts']['vendor_name']['resolution'],'preserve_legacy_pending_review')
                self.assertEqual(Path(store.get_original(initial['invoice_id'])['path']).read_bytes(),image_bytes())

    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'shadow','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':'test'})
    def test_shadow_disagreement_retains_legacy_and_requires_review(self):
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice',return_value=legacy()), \
             patch.object(vision,'read_invoice',return_value={'payload':fixture()}):
            result=extract_invoice(image_bytes())
        self.assertEqual(result.fields['vendor_name'],'買方測試有限公司')
        self.assertTrue(result.review_required)

    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'primary','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':'test'})
    def test_provider_failure_falls_back_without_claiming_vision_success(self):
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice',return_value=legacy()), \
             patch.object(vision,'read_invoice',side_effect=vision.VisionError('RATE_LIMITED')):
            result=extract_invoice(image_bytes())
        self.assertEqual(result.raw['vision']['status'],'RATE_LIMITED')
        self.assertTrue(result.review_required)

    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'primary','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':''})
    def test_missing_credentials_no_network(self):
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice',return_value=legacy()), \
             patch.object(vision,'read_invoice') as read:
            result=extract_invoice(image_bytes())
        read.assert_not_called()
        self.assertEqual(result.raw['vision']['status'],'CREDENTIAL_MISSING')
        self.assertTrue(result.review_required)

    def test_buyer_header_is_excluded_from_seller_text(self):
        text='三聯式\n買受人\n買方有限公司\n12345678\n營業人蓋用統一發票專用章\n測試商行\n16908319'
        self.assertNotIn('12345678',seller_region_text(text))
        self.assertIn('16908319',seller_region_text(text))
        self.assertEqual(seller_region_text('買受人\n12345678'),'')
        with patch('rapidocr.RapidOCR'), patch('services.invoice_intake.template_ocr.ocr_page',return_value=(text,.95)):
            result=extract_template_invoice(b'fake')
        self.assertEqual(result['fields']['seller_tax_id'],'16908319')


if __name__=='__main__': unittest.main()


class VisionMergeRegressionTests(unittest.TestCase):
    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'primary','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':'test'})
    def test_primary_vision_null_never_erases_legacy_value(self):
        legacy_result = legacy()
        payload = fixture()
        payload['invoice_date'] = None
        payload['seller_tax_id'] = None
        payload['amount_before_tax'] = None
        payload['tax_amount'] = None
        payload['total_amount'] = None
        payload['needs_review'] = True
        payload['uncertain_fields'] = ['invoice_date','seller_tax_id','amount_before_tax','tax_amount','total_amount']
        legacy_result.fields.update({
            'invoice_date':'2026-09-25',
            'seller_tax_id':'16908319',
            'amount_before_tax':24500,
            'tax_amount':1225,
            'total_amount':25725,
        })
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice', return_value=legacy_result), \
             patch.object(vision, 'read_invoice', return_value={'payload':payload,'image_sha256':'x','model':'test'}):
            result = extract_invoice(image_bytes())
        self.assertEqual(result.fields['invoice_date'],'2026-09-25')
        self.assertEqual(result.fields['seller_tax_id'],'16908319')
        self.assertEqual(result.fields['amount_before_tax'],24500)
        self.assertEqual(result.fields['tax_amount'],1225)
        self.assertEqual(result.fields['total_amount'],25725)

    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'primary','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':'test'})
    def test_primary_vision_conflict_preserves_legacy_and_traces_candidate(self):
        legacy_result = legacy()
        legacy_result.fields['invoice_number'] = 'EC55544057'
        payload = fixture()
        payload['invoice_number'] = 'AB12345678'
        payload['needs_review'] = True
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice', return_value=legacy_result), \
             patch.object(vision, 'read_invoice', return_value={'payload':payload,'image_sha256':'x','model':'test'}):
            result = extract_invoice(image_bytes())
        self.assertEqual(result.fields['invoice_number'],'EC55544057')
        self.assertEqual(result.raw['conflicts']['invoice_number']['vision'],'AB12345678')
        self.assertIn('invoice_number', result.raw['review']['confirm_fields'])


class VisionRoutingTests(unittest.TestCase):
    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'primary','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':'test'})
    def test_primary_skips_paid_vision_when_local_is_complete_and_high_confidence(self):
        local = legacy()
        local.fields.update({
            'invoice_number':'EC55544057',
            'invoice_date':'2026-09-25',
            'vendor_name':'榮昌企業有限公司',
            'buyer_tax_id':'23040145',
            'seller_tax_id':'16672215',
            'amount_before_tax':24500,
            'tax_amount':1225,
            'total_amount':25725,
        })
        local.confidence = {
            'invoice_number':0.99,'invoice_date':0.95,'vendor_name':0.95,
            'buyer_tax_id':0.90,'seller_tax_id':0.95,
            'amount_before_tax':0.98,'tax_amount':0.98,'total_amount':0.98,
        }
        local.raw.update({
            'review': {'status':'extracted','required_fields':[],'confirm_fields':[],'reasons':[]},
            'template': {'document_type':'two_part_uniform_invoice'},
            'line_items': [{'description':'印刷品','quantity':24500,'unit_price':1,'amount':24500}],
        })
        local.review_required = False
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice', return_value=local), \
             patch.object(vision, 'read_invoice') as read:
            result = extract_invoice(image_bytes())
        read.assert_not_called()
        self.assertEqual(result.raw['vision']['status'],'SKIPPED_LOCAL_SUFFICIENT')
        self.assertEqual(result.raw['vision_route']['decision'],'skip')

    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'primary','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':'test'})
    def test_three_part_missing_buyer_tax_id_invokes_vision(self):
        local = legacy()
        local.fields.update({
            'invoice_number':'EC55544057',
            'invoice_date':'2026-09-25',
            'vendor_name':'榮昌企業有限公司',
            'buyer_tax_id':None,
            'seller_tax_id':'16672215',
            'amount_before_tax':24500,
            'tax_amount':1225,
            'total_amount':25725,
        })
        local.confidence = {
            'invoice_number':0.99,'invoice_date':0.95,'vendor_name':0.95,
            'seller_tax_id':0.95,'amount_before_tax':0.98,'tax_amount':0.98,'total_amount':0.98,
        }
        local.raw.update({
            'review': {'status':'extracted','required_fields':[],'confirm_fields':[],'reasons':[]},
            'template': {'document_type':'three_part_uniform_invoice'},
            'line_items': [{'description':'印刷品','quantity':24500,'unit_price':1,'amount':24500}],
        })
        local.review_required = False
        payload = fixture()
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice', return_value=local), \
             patch.object(vision, 'read_invoice', return_value={'payload':payload,'image_sha256':'x','model':'test'}) as read:
            result = extract_invoice(image_bytes())
        read.assert_called_once()
        self.assertEqual(result.raw['vision_route']['reason'],'missing:buyer_tax_id')

    @patch.dict(os.environ, {'INVOICE_VISION_MODE':'primary','GEMINI_INVOICE_MODEL':'test','GEMINI_API_KEY':'test'})
    def test_primary_invokes_vision_when_local_needs_review(self):
        local = legacy()
        local.review_required = True
        local.raw['review'] = {'status':'needs_review','required_fields':['invoice_date'],'confirm_fields':[],'reasons':['missing:invoice_date']}
        result_payload = fixture()
        with patch('services.invoice_intake.invoice_core.extract_legacy_invoice', return_value=local), \
             patch.object(vision, 'read_invoice', return_value={'payload':result_payload,'image_sha256':'x','model':'test'}) as read:
            result = extract_invoice(image_bytes())
        read.assert_called_once()
        self.assertEqual(result.raw['vision_route']['decision'],'invoke')
        self.assertEqual(result.raw['vision_route']['reason'],'local_review_required')
