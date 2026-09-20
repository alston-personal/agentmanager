"""No-network regression tests for Mio's governed single-image post."""
import json
import struct
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from agentos_node.social.contracts import SocialRequest
from agentos_node.social.credentials import AccountBinding, EphemeralCredentialVault
from agentos_node.social.governance import RuntimeWriteAcceptance
from agentos_node.social.threads import ThreadsCapability

ASSET=Path(__file__).resolve().parents[1]/"personas/mio/approved/assets/mio-evening-park-20260920.png"

class FakeImageTransport:
    def __init__(self): self.calls=[]; self.status_reads=0
    def api(self,path,*,token,method="GET",params=None):
        self.calls.append((path,method,dict(params or {})))
        if path=="me/threads":
            assert method=="POST"
            return {"id":"image-container-100"}
        if path=="image-container-100":
            self.status_reads+=1
            return {"status":"FINISHED" if self.status_reads>=2 else "IN_PROGRESS"}
        if path=="me/threads_publish":
            assert params=={"creation_id":"image-container-100"}
            return {"id":"image-post-200"}
        raise AssertionError(path)

def request(**kwargs):
    return SocialRequest(product_id="galaxy",platform="threads",operation="publish",
                         account_binding_id="galaxy:threads:42",target_account_id="42",
                         primary_text="有時候散步，只是為了看看今天的天空。🌱",
                         write_intent_id="mio-image-immutable-asset-test",**kwargs)

class MioImageContractTests(unittest.TestCase):
    def test_reject_non_https_or_incomplete_media(self):
        for url in ("http://localhost/a.png","file:///tmp/a.png","https://example.org/a.png#fragment"):
            with self.subTest(url=url),self.assertRaisesRegex(ValueError,"invalid_publish_image_url"):
                request(image_url=url,image_alt_text="一張風景圖").validate()
        with self.assertRaisesRegex(ValueError,"image_alt_text_required"):
            request(image_url="https://example.org/a.png").validate()
        with self.assertRaisesRegex(ValueError,"image_alt_text_without_image"):
            request(image_alt_text="孤立文字").validate()

    def test_image_container_is_published_only_when_finished(self):
        vault=EphemeralCredentialVault()
        vault.bind(AccountBinding("galaxy:threads:42","galaxy","threads","42","sunlake.milkcat"),"dummy-token")
        transport=FakeImageTransport()
        cap=ThreadsCapability(vault,transport)
        req=request(image_url="https://raw.githubusercontent.com/a/b/sha/file.png",image_alt_text="黃昏裡的公園")
        acceptance=RuntimeWriteAcceptance("accepted-image-1","galaxy","threads",frozenset({"publish"}),frozenset({req.account_binding_id}))
        with patch("agentos_node.social.threads.time.sleep"):
            receipt=cap.publish(req,acceptance=acceptance)
        self.assertTrue(receipt["ok"],receipt)
        self.assertEqual(receipt["platform_object_id"],"image-post-200")
        create=transport.calls[0][2]
        self.assertEqual(create["media_type"],"IMAGE")
        self.assertEqual(create["alt_text"],"黃昏裡的公園")
        self.assertNotIn("auto_publish_text",create)
        self.assertEqual([v[0] for v in transport.calls],["me/threads","image-container-100","image-container-100","me/threads_publish"])

    def test_platform_image_readback_requires_media_and_https(self):
        normalized=ThreadsCapability._safe_media({"id":"image-post-200","text":"散步","media_type":"IMAGE","media_url":"https://img.test/a.png"})
        self.assertTrue(normalized["image_visible"])
        self.assertEqual(normalized["media_type"],"IMAGE")
        self.assertFalse(ThreadsCapability._safe_media({"id":"fake","media_type":"TEXT"})["image_visible"])

    def test_carousel_rejects_invalid_media_and_mutually_exclusive_single_image(self):
        urls=["https://example.org/one.jpg","https://example.org/two.jpg"]
        with self.assertRaisesRegex(ValueError,"invalid_publish_carousel"):
            request(image_urls=urls[:1],image_alt_texts=["one"]).validate()
        with self.assertRaisesRegex(ValueError,"invalid_publish_carousel"):
            request(image_urls=urls,image_alt_texts=["only-one"]).validate()
        with self.assertRaisesRegex(ValueError,"invalid_publish_carousel"):
            request(image_url=urls[0],image_alt_text="single",image_urls=urls,image_alt_texts=["one","two"]).validate()
        with self.assertRaisesRegex(ValueError,"invalid_publish_carousel_item"):
            request(image_urls=[urls[0],"http://localhost/unsafe"],image_alt_texts=["one","two"]).validate()
        self.assertEqual(request(image_urls=urls,image_alt_texts=["one","two"]).validate().image_urls,urls)

    def test_two_original_images_publish_as_one_carousel_parent(self):
        class FakeCarouselTransport:
            def __init__(self): self.calls=[];self.children=0
            def api(self,path,*,token,method="GET",params=None):
                d=dict(params or {})
                self.calls.append((path,method,d))
                if path=="me/threads" and d.get("is_carousel_item")=="true":
                    self.children+=1
                    return {"id":f"child-{self.children}"}
                if path in {"child-1","child-2","carousel-parent"}:
                    return {"status":"FINISHED"}
                if path=="me/threads" and d.get("media_type")=="CAROUSEL":
                    assert d["children"]=="child-1,child-2"
                    assert "image_url" not in d
                    return {"id":"carousel-parent"}
                if path=="me/threads_publish":
                    assert d=={"creation_id":"carousel-parent"}
                    return {"id":"public-carousel-post"}
                raise AssertionError((path,method,d))
        urls=["https://cdn.example.org/first.jpg","https://cdn.example.org/second.jpg"]
        vault=EphemeralCredentialVault()
        vault.bind(AccountBinding("galaxy:threads:42","galaxy","threads","42","sunlake.milkcat"),"dummy-token")
        transport=FakeCarouselTransport()
        cap=ThreadsCapability(vault,transport)
        req=request(image_urls=urls,image_alt_texts=["燉飯與干貝","甜點"])
        acceptance=RuntimeWriteAcceptance("accepted-carousel-1","galaxy","threads",frozenset({"publish"}),frozenset({req.account_binding_id}))
        with patch("agentos_node.social.threads.time.sleep"):
            receipt=cap.publish(req,acceptance=acceptance)
        self.assertTrue(receipt["ok"],receipt)
        self.assertEqual(receipt["platform_object_id"],"public-carousel-post")
        self.assertEqual([call[0] for call in transport.calls],[
            "me/threads","child-1","me/threads","child-2","me/threads","carousel-parent","me/threads_publish"])
        self.assertEqual(transport.calls[0][2]["alt_text"],"燉飯與干貝")
        self.assertEqual(transport.calls[2][2]["alt_text"],"甜點")

    def test_pinned_original_artwork_is_valid_png(self):
        data=ASSET.read_bytes()
        self.assertTrue(data.startswith(bytes.fromhex("89504e470d0a1a0a")))
        offset=8; pixels=b""; width=height=0; palette=b""
        while offset<len(data):
            length=struct.unpack(">I",data[offset:offset+4])[0]
            kind=data[offset+4:offset+8]; chunk=data[offset+8:offset+8+length]
            stored=struct.unpack(">I",data[offset+8+length:offset+12+length])[0]
            self.assertEqual(zlib.crc32(kind+chunk)&0xffffffff,stored)
            if kind==b"IHDR":
                width,height,depth,mode,*_=struct.unpack(">IIBBBBB",chunk)
                self.assertEqual((width,height,depth,mode),(640,640,8,3))
            elif kind==b"PLTE": palette=chunk
            elif kind==b"IDAT": pixels+=chunk
            elif kind==b"IEND": break
            offset+=12+length
        decoded=zlib.decompress(pixels)
        self.assertEqual(len(decoded),height*(width+1))
        self.assertGreater(len(palette),30)
        self.assertTrue(all(decoded[y*(width+1)]==0 for y in range(height)))

if __name__=="__main__": unittest.main()
