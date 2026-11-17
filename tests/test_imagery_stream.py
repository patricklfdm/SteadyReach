import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.parse import parse_qs,urlsplit
from ras_workflow.imagery import export_pixels


class ImageStreamTests(unittest.TestCase):
    def test_broken_temporary_link_uses_identical_locked_request(self):
        params=dict(f='json',bbox='1,2,3,4',bboxSR=26913,imageSR=26913,size='1600,1600',
            format='png32',adjustAspectRatio='false',mosaicRule='locked-ids',renderingRule='natural-color')
        get=Mock(side_effect=[HTTPError('temporary',404,'expired',{},None),'stream.png']);state={}
        result=export_pixels({'href':'temporary'},params,get,4000000,state)
        self.assertEqual(result,'stream.png')
        self.assertEqual(state['image_transport'],'DIRECT_STREAM_AFTER_HREF_FAILURE')
        args=get.call_args.args
        query=parse_qs(urlsplit(args[0]).query)
        self.assertEqual(query,{k:[str(v)] for k,v in dict(params,f='image').items()})
        self.assertEqual(args[1:],('image_stream.png',4000000))
        self.assertEqual(params['f'],'json')

    def test_access_and_validation_errors_do_not_use_fallback(self):
        for error in (HTTPError('temporary',403,'denied',{},None),ValueError('budget exceeded')):
            get=Mock(side_effect=error)
            with self.assertRaises(type(error)):
                export_pixels({'href':'temporary'},{'f':'json'},get,1,{})
            self.assertEqual(get.call_count,1)

    def test_successful_link_does_not_duplicate_download(self):
        get=Mock(return_value='image.png');state={}
        self.assertEqual(export_pixels({'href':'temporary'},{},get,3,state),'image.png')
        self.assertEqual(state['image_transport'],'EXPORTED_HREF')
        self.assertEqual(get.call_count,1)
