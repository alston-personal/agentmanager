import importlib.util
import pathlib
import tempfile
import unittest
from PIL import Image

P=pathlib.Path(__file__).resolve().parents[1]/"scripts/isolate_mio_product_candidate.py"
spec=importlib.util.spec_from_file_location("isolate_mio_product_candidate",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ProductCandidateTests(unittest.TestCase):
    def test_simple_studio_photo_creates_unapproved_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            src=pathlib.Path(d)/"source.png";out=pathlib.Path(d)/"candidate.png"
            img=Image.new("RGB",(300,300),"white")
            for y in range(65,240):
                for x in range(90,205):
                    img.putpixel((x,y),(70,35,30))
            img.save(src)
            result=m.isolate_uniform_background(src,out)
            self.assertEqual(result["state"],"candidate")
            self.assertTrue(out.is_file())
            self.assertEqual(Image.open(out).getpixel((0,0))[3],0)
            self.assertNotIn("approved",result)
    def test_busy_background_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            src=pathlib.Path(d)/"source.png";out=pathlib.Path(d)/"candidate.png"
            img=Image.new("RGB",(300,300),(100,90,80));img.save(src)
            result=m.isolate_uniform_background(src,out)
            self.assertEqual(result["state"],"needs_target_segmentation")
            self.assertFalse(out.exists())

if __name__=="__main__":unittest.main()
