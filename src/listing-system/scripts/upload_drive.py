#!/usr/bin/env python3
"""
upload_to_drive.py
上传文件到 Google Drive 指定文件夹

用法:
    python3 upload_to_drive.py <本地文件路径> [--name <文件名>] [--folder listing|tax] [--overwrite]

环境变量:
    MATON_API_KEY - Maton API 密钥（已配置在系统环境变量中）

目标文件夹:
    08 ebay-project (ID: 1XKuXdsegh7ybT8Cdj43h5ZaAtRVE-Hky)

    listing 文件 -> ebay listing API (ID: 15h280yccE1bN4gzTuAM-QlxI1sCRqdGu)
      - output/ 目录的文件 -> 上传到 output/ 子文件夹（覆盖旧版本）
      - 其他文件 -> 上传到主文件夹（不覆盖）

    tax 文件 -> ebay tax (ID: 1GS22yLQLrNlC-5eikBlQrBfe_CrVx2PY)

输出文件路径:
    listing-system/output/* -> Google Drive: ebay listing API/output/（覆盖模式）
    其余 listing-system 文件 -> Google Drive: ebay listing API/（不覆盖）
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.parse

FOLDER_ID = "1XKuXdsegh7ybT8Cdj43h5ZaAtRVE-Hky"
GATEWAY_BASE = "https://gateway.maton.ai/google-drive"
MATON_KEY = os.environ.get("MATON_API_KEY", "")

# Google Drive 已有的子文件夹
SUBFOLDER_IDS = {
    "listing": "15h280yccE1bN4gzTuAM-QlxI1sCRqdGu",   # ebay listing API
    "tax": "1GS22yLQLrNlC-5eikBlQrBfe_CrVx2PY",        # ebay tax
}

LISTING_OUTPUT_SUBFOLDER = "output"


def is_output_file(local_path):
    """判断是否为 listing-system 的输出文件（位于 output/ 目录下）"""
    normalized = local_path.replace('\\', '/')
    if "/output/" in normalized or "/output\\" in normalized:
        return True
    # 也检查 listing-system/output
    if "listing-system/output" in normalized:
        return True
    return False


def get_or_create_output_subfolder(parent_folder_key):
    """获取或创建 listing output 子文件夹，返回子文件夹 ID"""
    parent_id = SUBFOLDER_IDS.get(parent_folder_key)
    if not parent_id:
        return None
    
    folder_name = LISTING_OUTPUT_SUBFOLDER
    
    # 先查找是否已存在
    query = urllib.parse.quote(f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder'")
    req = urllib.request.Request(
        f"{GATEWAY_BASE}/drive/v3/files?q={query}&fields=files(id,name)"
    )
    req.add_header('Authorization', f'Bearer {MATON_KEY}')

    try:
        resp = json.load(urllib.request.urlopen(req))
        files = resp.get('files', [])
        if files:
            return files[0]['id']
    except Exception as e:
        print(f"查找 output 文件夹失败: {e}")

    # 创建新文件夹
    metadata = json.dumps({
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }).encode('utf-8')

    req = urllib.request.Request(
        f"{GATEWAY_BASE}/drive/v3/files",
        data=metadata,
        method='POST'
    )
    req.add_header('Authorization', f'Bearer {MATON_KEY}')
    req.add_header('Content-Type', 'application/json')

    try:
        resp = json.load(urllib.request.urlopen(req))
        print(f"创建子文件夹: {folder_name} (ID: {resp.get('id')})")
        return resp.get('id')
    except Exception as e:
        print(f"创建 output 文件夹失败: {e}")
        return None


def delete_existing(filename, folder_key):
    """删除目标文件夹中同名文件（用于覆盖上传）"""
    folder_id = SUBFOLDER_IDS.get(folder_key)
    if not folder_id:
        return 0

    query = urllib.parse.quote(f"'{folder_id}' in parents and name = '{filename}'")
    req = urllib.request.Request(
        f"{GATEWAY_BASE}/drive/v3/files?q={query}&fields=files(id,name)"
    )
    req.add_header('Authorization', f'Bearer {MATON_KEY}')

    try:
        resp = json.load(urllib.request.urlopen(req))
        files = resp.get('files', [])
        deleted = 0
        for f in files:
            del_req = urllib.request.Request(
                f"{GATEWAY_BASE}/drive/v3/files/{f['id']}",
                method='DELETE'
            )
            del_req.add_header('Authorization', f'Bearer {MATON_KEY}')
            urllib.request.urlopen(del_req)
            deleted += 1
            print(f"  已删除旧文件: {f['name']}")
        return deleted
    except Exception as e:
        print(f"  删除旧文件失败: {e}")
        return 0


def delete_existing_in_subfolder(filename, subfolder_id):
    """删除子文件夹中同名文件（用于 output 目录覆盖）"""
    query = urllib.parse.quote(f"'{subfolder_id}' in parents and name = '{filename}'")
    req = urllib.request.Request(
        f"{GATEWAY_BASE}/drive/v3/files?q={query}&fields=files(id,name)"
    )
    req.add_header('Authorization', f'Bearer {MATON_KEY}')

    try:
        resp = json.load(urllib.request.urlopen(req))
        files = resp.get('files', [])
        deleted = 0
        for f in files:
            del_req = urllib.request.Request(
                f"{GATEWAY_BASE}/drive/v3/files/{f['id']}",
                method='DELETE'
            )
            del_req.add_header('Authorization', f'Bearer {MATON_KEY}')
            urllib.request.urlopen(del_req)
            deleted += 1
            print(f"  已删除旧文件: {f['name']}")
        return deleted
    except Exception as e:
        print(f"  删除旧文件失败: {e}")
        return 0


def upload_to_folder(local_path, filename, mime_type, folder_id):
    """上传文件到指定文件夹 ID"""
    with open(local_path, 'rb') as f:
        file_content = f.read()

    boundary = "----PythonFormBoundary7MA4YWxkTrZu0gW"
    
    metadata = json.dumps({
        "name": filename,
        "parents": [folder_id]
    }).encode('utf-8')

    body = (
        f"--{boundary}\r\n"
        f'Content-Type: application/json; charset=UTF-8\r\n\r\n'
    ).encode('utf-8') + metadata + f"\r\n--{boundary}\r\n".encode('utf-8')

    body += (
        f'Content-Type: {mime_type}\r\n\r\n'
    ).encode('utf-8') + file_content + f"\r\n--{boundary}--\r\n".encode('utf-8')

    req = urllib.request.Request(
        f"{GATEWAY_BASE}/upload/drive/v3/files?uploadType=multipart",
        data=body,
        method='POST'
    )
    req.add_header('Authorization', f'Bearer {MATON_KEY}')
    req.add_header('Content-Type', f'multipart/related; boundary={boundary}')

    try:
        resp = urllib.request.urlopen(req)
        result = json.load(resp)
        print(f"上传成功! File ID: {result.get('id')}")
        return result
    except Exception as e:
        print(f"上传失败: {e}", file=sys.stderr)
        return None


def upload_file(local_path, drive_folder_key=None, filename=None, overwrite=False):
    """上传单个文件到 Google Drive 指定文件夹"""
    if not os.path.exists(local_path):
        print(f"错误: 文件不存在: {local_path}", file=sys.stderr)
        return None

    if not MATON_KEY:
        print("错误: MATON_API_KEY 环境变量未设置", file=sys.stderr)
        return None

    if filename is None:
        filename = os.path.basename(local_path)

    # 根据路径自动判断文件夹类型
    if drive_folder_key:
        folder_key = drive_folder_key
    else:
        if "listing-system" in local_path or "/listing" in local_path:
            folder_key = "listing"
        elif "tax-system" in local_path or "/tax" in local_path:
            folder_key = "tax"
        else:
            folder_key = "listing"

    folder_name = "ebay listing API" if folder_key == "listing" else "ebay tax"

    # 判断是否为 output 文件
    is_output = is_output_file(local_path)
    
    file_size = os.path.getsize(local_path)
    mime_type = get_mime_type(local_path)

    print(f"上传文件: {filename}")
    print(f"本地路径: {local_path}")
    print(f"文件大小: {file_size} bytes")

    if is_output:
        # output 文件 -> 上传到 output/ 子文件夹（强制覆盖）
        print(f"检测为输出文件: 目标 {folder_name}/output/（覆盖模式）")
        subfolder_id = get_or_create_output_subfolder(folder_key)
        if not subfolder_id:
            print(f"错误: 无法获取 output 文件夹", file=sys.stderr)
            return None
        
        print(f"覆盖模式：检查并删除 output/ 同名旧文件...")
        delete_existing_in_subfolder(filename, subfolder_id)
        
        print(f"目标文件夹: {folder_name}/output/")
        return upload_to_folder(local_path, filename, mime_type, subfolder_id)
    else:
        # 非 output 文件 -> 上传到主文件夹（仅在 overwrite=True 时覆盖）
        if overwrite:
            print(f"覆盖模式：检查并删除同名旧文件...")
            delete_existing(filename, folder_key)

        print(f"目标文件夹: {folder_name}")
        
        if file_size <= 5 * 1024 * 1024:
            return upload_simple(local_path, filename, mime_type, folder_key)
        else:
            return upload_multipart(local_path, filename, mime_type, folder_key)


def upload_simple(local_path, filename, mime_type, folder_key):
    """简单上传方式（<= 5MB）"""
    folder_id = SUBFOLDER_IDS.get(folder_key)
    if not folder_id:
        print(f"错误: 未知的文件夹类型: {folder_key}", file=sys.stderr)
        return None

    return upload_to_folder(local_path, filename, mime_type, folder_id)


def upload_multipart(local_path, filename, mime_type, folder_name):
    """分块上传方式（> 5MB）"""
    print("文件大于 5MB，使用分块上传...")
    return upload_simple(local_path, filename, mime_type, folder_name)


def get_or_create_folder(folder_name):
    """获取或创建子文件夹，返回 folder ID"""
    query = urllib.parse.quote(f"name='{folder_name}' and '{FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'")
    req = urllib.request.Request(
        f"{GATEWAY_BASE}/drive/v3/files?q={query}&fields=files(id,name)"
    )
    req.add_header('Authorization', f'Bearer {MATON_KEY}')

    try:
        resp = json.load(urllib.request.urlopen(req))
        files = resp.get('files', [])
        if files:
            print(f"找到已存在文件夹: {folder_name} (ID: {files[0]['id']})")
            return files[0]['id']
    except Exception as e:
        print(f"查找文件夹失败: {e}", file=sys.stderr)

    metadata = json.dumps({
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [FOLDER_ID]
    }).encode('utf-8')

    req = urllib.request.Request(
        f"{GATEWAY_BASE}/drive/v3/files",
        data=metadata,
        method='POST'
    )
    req.add_header('Authorization', f'Bearer {MATON_KEY}')
    req.add_header('Content-Type', 'application/json')

    try:
        resp = json.load(urllib.request.urlopen(req))
        print(f"创建文件夹: {folder_name} (ID: {resp.get('id')})")
        return resp.get('id')
    except Exception as e:
        print(f"创建文件夹失败: {e}", file=sys.stderr)
        return None


def get_mime_type(filepath):
    """根据文件扩展名获取 MIME 类型"""
    ext = os.path.splitext(filepath)[1].lower()
    mime_types = {
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.csv': 'text/csv',
        '.pdf': 'application/pdf',
        '.json': 'application/json',
        '.txt': 'text/plain',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.zip': 'application/zip',
        '.html': 'text/html',
    }
    return mime_types.get(ext, 'application/octet-stream')


def list_folder_contents():
    """列出目标文件夹及子文件夹内容"""
    print(f"文件夹: 08 ebay-project (ID: {FOLDER_ID})\n")
    
    for folder_key, folder_id in SUBFOLDER_IDS.items():
        folder_name = "ebay listing API" if folder_key == "listing" else "ebay tax"
        
        # 获取文件夹内的文件
        query = urllib.parse.quote(f"'{folder_id}' in parents")
        req = urllib.request.Request(
            f"{GATEWAY_BASE}/drive/v3/files?q={query}&fields=files(id,name,mimeType,size,createdTime)"
        )
        req.add_header('Authorization', f'Bearer {MATON_KEY}')

        try:
            resp = json.load(urllib.request.urlopen(req))
            files = resp.get('files', [])
            print(f"📁 {folder_name}:")
            if files:
                for f in files:
                    size = f.get('size', 'N/A')
                    if size != 'N/A':
                        size_str = f"{int(size):,} bytes"
                    else:
                        size_str = 'N/A'
                    print(f"   {f['name']} ({size_str})")
            else:
                print(f"   (空)")
            print()
        except Exception as e:
            print(f"   列出失败: {e}\n")


def main():
    parser = argparse.ArgumentParser(description='上传文件到 Google Drive')
    parser.add_argument('filepath', nargs='?', help='要上传的文件路径')
    parser.add_argument('--name', '-n', help='上传后的文件名')
    parser.add_argument('--folder', '-f', choices=['listing', 'tax'],
                        help='上传到哪个子文件夹（自动根据路径判断）')
    parser.add_argument('--list', '-l', action='store_true',
                        help='列出当前文件夹内容')
    parser.add_argument('--overwrite', '-o', action='store_true',
                        help='上传前删除目标文件夹中同名文件（覆盖模式，仅对非 output 文件生效）')
    parser.add_argument('--folder-id', default=FOLDER_ID, help='目标文件夹 ID')

    args = parser.parse_args()

    if args.list:
        list_folder_contents()
        return

    if not args.filepath:
        parser.print_help()
        print("\n示例:")
        print("  python3 upload_to_drive.py /path/to/file.xlsx")
        print("  python3 upload_to_drive.py /path/to/file.xlsx --folder tax")
        print("  python3 upload_to_drive.py -l")
        print("\n说明:")
        print("  - listing-system/output/* 文件 -> 自动上传到 output/ 子文件夹（覆盖模式）")
        print("  - 其他 listing-system 文件 -> 上传到主文件夹（默认不覆盖）")
        return

    folder_name = args.folder if args.folder else None
    result = upload_file(args.filepath, folder_name, args.name, overwrite=args.overwrite)
    
    if result:
        print(f"\n完成! 文件已上传到 Google Drive")
        print(f"链接: https://drive.google.com/drive/folders/{FOLDER_ID}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
