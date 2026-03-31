#!/usr/bin/env python3
"""
Upload listing results to Google Drive
"""
import os, json, urllib.request, glob

key = os.environ.get('MATON_API_KEY', '')
folder_id = '15h280yccE1bN4gzTuAM-QlxI1sCRqdGu'  # listing folder
gateway = 'https://gateway.maton.ai/google-drive'

def upload(path, name):
    if not os.path.exists(path):
        print(f'SKIP: {path}')
        return
    ext = os.path.splitext(path)[1].lower()
    mime = {
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.html': 'text/html'
    }.get(ext, 'application/octet-stream')
    with open(path, 'rb') as f:
        data = f.read()
    boundary = '----FormBoundary7MA4YWxk'
    meta = json.dumps({'name': name, 'parents': [folder_id]}).encode()
    body = (f'--{boundary}\r\nContent-Type: application/json\r\n\r\n').encode()
    body += meta + f'\r\n--{boundary}\r\n'.encode()
    body += f'Content-Type: {mime}\r\n\r\n'.encode() + data + f'\r\n--{boundary}--\r\n'.encode()
    req = urllib.request.Request(
        f'{gateway}/upload/drive/v3/files?uploadType=multipart',
        data=body, method='POST'
    )
    req.add_header('Authorization', f'Bearer {key}')
    req.add_header('Content-Type', f'multipart/related; boundary={boundary}')
    try:
        r = urllib.request.urlopen(req)
        result = json.load(r)
        print(f'OK: {name} -> {result.get("id")}')
    except Exception as e:
        print(f'FAIL: {name} -> {e}')

BASE = os.path.dirname(os.path.abspath(__file__))
LISTING_DIR = os.path.dirname(BASE)

upload(os.path.join(LISTING_DIR, '商品数据.xlsx'), '商品数据_结果.xlsx')
for f in glob.glob(os.path.join(LISTING_DIR, 'output', '*.html')):
    upload(f, os.path.basename(f))
