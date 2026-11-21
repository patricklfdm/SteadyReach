"""Bounded Windows OCR subprocess. No PowerShell execution-policy changes."""
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from .common import ROOT, runtime_scratch


class NoReadableText(ValueError):
    """OCR completed but found no text in the image."""


async def recognize(path):
    from winrt.windows.storage import StorageFile, FileAccessMode
    from winrt.windows.graphics.imaging import BitmapDecoder, BitmapPixelFormat, BitmapAlphaMode
    from winrt.windows.media.ocr import OcrEngine
    engine=OcrEngine.try_create_from_user_profile_languages()
    if engine is None:raise ValueError('No installed Windows OCR language matches the user profile; install a supported language or supply text/CSV')
    source=await StorageFile.get_file_from_path_async(str(Path(path).resolve()))
    stream=await source.open_async(FileAccessMode.READ)
    bitmap=None
    try:
        decoder=await BitmapDecoder.create_async(stream)
        bitmap=await decoder.get_software_bitmap_converted_async(BitmapPixelFormat.BGRA8,BitmapAlphaMode.PREMULTIPLIED)
        result=await engine.recognize_async(bitmap)
        return dict(text=result.text[:100_000],language=engine.recognizer_language.language_tag)
    finally:
        if bitmap is not None:bitmap.close()
        stream.close()


def image_text(path,scratch):
    from PIL import Image, ImageOps
    scratch=Path(scratch);scratch.mkdir(parents=True,exist_ok=True);target=scratch/'ocr.png'
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGB');image.thumbnail((2400,2400));image.save(target);image.close()
    result=subprocess.run([sys.executable,'-m','ras_workflow.local_ocr',str(target)],cwd=ROOT,
        capture_output=True,timeout=35,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Local OCR unavailable: '+result.stderr.decode('utf-8',errors='replace')[-700:])
    record=json.loads(result.stdout.decode('utf-8-sig'))
    if not record['text'].strip():raise NoReadableText('OCR returned no readable text; inspect the retained original or supply a text/CSV transcription')
    return record['text']


def probe():
    from PIL import Image,ImageDraw,ImageFont
    folder=runtime_scratch()/'ocr_probe';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'software_probe.png'
    try:
        image=Image.new('RGB',(1000,160),'white');draw=ImageDraw.Draw(image)
        draw.text((25,40),'STEADY REACH 457',font=ImageFont.load_default(size=55),fill='black');image.save(path);image.close()
        text=image_text(path,folder)
        if '457' not in text:raise ValueError('OCR executed but did not recognize the software-test number')
        return dict(status='READY',method='Windows OCR / PyWinRT',probe_text=text,scope='Software-only printed text; handwriting and site interpretation are unverified')
    except Exception as e:return dict(status='UNAVAILABLE',error=str(e),scope='PDF text and survey/parameter CSV remain available; retain original images for inspection')


if __name__=='__main__':
    try:
        if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
        print(json.dumps(asyncio.run(recognize(sys.argv[1])),ensure_ascii=False))
    except Exception as e:
        print(str(e),file=sys.stderr);raise SystemExit(1)
