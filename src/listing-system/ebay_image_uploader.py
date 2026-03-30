#!/usr/bin/env python3
"""
eBay 图片上传工具
支持本地图片上传到 eBay 图片托管，获取 PictureURL 用于 Listing

功能：
- 单张/批量上传
- 自动压缩（超过 eBay 尺寸限制时）
- 格式转换（统一为 JPEG）
- 上传进度显示
- 错误重试

eBay 图片要求：
- 格式：JPEG, PNG, TIFF, BMP, GIF
- 大小：最大 7MB/张
- 尺寸：最小 500px，推荐 1600px+（支持 zoom）
- 数量：最多 12 张（1 主图 + 11 附图）
"""

import os
import io
import logging
import requests
import base64
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from PIL import Image

logger = logging.getLogger("ebay_image_uploader")


@dataclass
class UploadResult:
    """单张图片上传结果"""
    file_path: str
    success: bool = False
    picture_url: str = ""
    error: str = ""
    size_before: int = 0
    size_after: int = 0
    dimensions: str = ""


class EbayImageUploader:
    """eBay 图片上传器"""

    def __init__(self, ebay_client, config: Dict[str, Any] = None):
        """
        Args:
            ebay_client: EbayClient 实例（已配置 Token）
            config: 可选配置，覆盖默认值
        """
        self.client = ebay_client
        self.config = config or {}

        # 图片配置
        self.max_size_mb = self.config.get("max_size_mb", 7)
        self.min_dimension = self.config.get("min_dimension", 500)
        self.recommended_dimension = self.config.get("recommended_dimension", 1600)
        self.quality = self.config.get("jpeg_quality", 90)
        self.max_retries = self.config.get("max_retries", 3)

        logger.info(f"图片上传器初始化完成 | 最大尺寸：{self.max_size_mb}MB | 质量：{self.quality}%")

    def upload_local_image(self, file_path: str) -> UploadResult:
        """
        上传单张本地图片

        Args:
            file_path: 本地图片文件路径

        Returns:
            UploadResult
        """
        path = Path(file_path)
        result = UploadResult(file_path=str(path))

        # 检查文件是否存在
        if not path.exists():
            result.error = f"文件不存在：{file_path}"
            logger.error(f"[{file_path}] {result.error}")
            return result

        # 读取并处理图片
        try:
            img_data, original_size = self._prepare_image(path)
            result.size_before = original_size
            result.size_after = len(img_data)
        except Exception as e:
            result.error = f"图片处理失败：{e}"
            logger.error(f"[{file_path}] {result.error}")
            return result

        # 上传到 eBay
        for attempt in range(self.max_retries):
            try:
                picture_url = self._upload_to_ebay(img_data, path.suffix.lower())
                if picture_url:
                    result.picture_url = picture_url
                    result.success = True
                    logger.info(f"[{file_path}] 上传成功：{picture_url}")
                    return result
            except Exception as e:
                logger.warning(f"[{file_path}] 上传失败 (尝试 {attempt+1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    result.error = f"上传失败（重试{self.max_retries}次）: {e}"
                    logger.error(f"[{file_path}] {result.error}")
                    return result

        return result

    def upload_batch(self, file_paths: List[str]) -> List[UploadResult]:
        """
        批量上传本地图片

        Args:
            file_paths: 本地图片文件路径列表

        Returns:
            List[UploadResult]
        """
        results = []
        logger.info(f"开始批量上传 {len(file_paths)} 张图片...")

        for i, path in enumerate(file_paths, 1):
            logger.info(f"[{i}/{len(file_paths)}] 处理：{path}")
            result = self.upload_local_image(path)
            results.append(result)

        success_count = sum(1 for r in results if r.success)
        logger.info(f"批量上传完成：成功 {success_count}/{len(file_paths)} 张")

        return results

    def upload_from_folder(self, folder_path: str, pattern: str = "*") -> List[UploadResult]:
        """
        上传文件夹中的所有图片

        Args:
            folder_path: 文件夹路径
            pattern: 文件匹配模式（如 "*.jpg", "*.png"）

        Returns:
            List[UploadResult]
        """
        folder = Path(folder_path)
        if not folder.exists():
            logger.error(f"文件夹不存在：{folder_path}")
            return []

        # 支持的图片格式
        image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"]

        # 获取所有图片文件
        if pattern == "*":
            files = [f for f in folder.iterdir() if f.suffix.lower() in image_extensions]
        else:
            files = list(folder.glob(pattern))

        # 排序（按文件名）
        files.sort(key=lambda x: x.name)

        logger.info(f"在 {folder_path} 中找到 {len(files)} 张图片")
        return self.upload_batch([str(f) for f in files])

    # ─── 内部方法 ──────────────────────────────────────

    def _prepare_image(self, path: Path) -> tuple:
        """
        准备图片数据（压缩、格式转换）

        Returns:
            (图片二进制数据，原始大小)
        """
        original_size = path.stat().st_size

        # 检查是否超过大小限制
        max_bytes = self.max_size_mb * 1024 * 1024
        if original_size <= max_bytes:
            # 不需要压缩，直接读取
            with open(path, "rb") as f:
                return f.read(), original_size

        # 需要压缩
        logger.info(f"[{path.name}] 文件过大 ({original_size/1024/1024:.1f}MB)，开始压缩...")

        img = Image.open(path)

        # 转换为 RGB（处理 PNG 透明通道等）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # 调整尺寸（如果超过推荐尺寸）
        max_dim = max(img.size)
        if max_dim > self.recommended_dimension:
            ratio = self.recommended_dimension / max_dim
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"调整尺寸：{img.size[0]}x{img.size[1]}")

        # 压缩为 JPEG
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=self.quality, optimize=True)
        img_data = output.getvalue()

        logger.info(f"压缩后大小：{len(img_data)/1024:.1f}KB (原始：{original_size/1024:.1f}KB)")

        return img_data, original_size

    def _upload_to_ebay(self, img_data: bytes, file_ext: str) -> Optional[str]:
        """
        上传图片到 eBay

        使用 Trading API 的 UploadFile 调用

        Returns:
            PictureURL 或 None
        """
        # 确定 MIME 类型
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".tiff": "image/tiff",
        }
        mime_type = mime_map.get(file_ext, "image/jpeg")

        # 编码图片数据
        img_base64 = base64.b64encode(img_data).decode("utf-8")

        # 构建 UploadFile 请求
        # 注意：Trading API 使用 XML 格式
        xml_request = f"""<?xml version="1.0" encoding="utf-8"?>
<UploadFileRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <WarningLevel>High</WarningLevel>
    <PictureDetails>
        <PictureData>
            <Data>{img_base64}</Data>
            <Format>{mime_type}</Format>
        </PictureData>
    </PictureDetails>
</UploadFileRequest>"""

        # 发送请求
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1113",
            "X-EBAY-API-CALL-NAME": "UploadFile",
            "X-EBAY-API-SITEID": "0",  # US
            "X-EBAY-API-APP-NAME": self.client.env_config.get("app_id", ""),
            "X-EBAY-API-DEV-NAME": self.client.env_config.get("dev_id", ""),
            "X-EBAY-API-CERT-NAME": self.client.env_config.get("cert_id", ""),
            "X-EBAY-API-REQUEST-ENCODING": "base64",
            "Content-Type": "text/xml",
        }

        # 如果有 User Token，添加认证头
        user_token = self.client.get_user_token()
        if user_token:
            headers["X-EBAY-API-IAF-TOKEN"] = user_token

        endpoint = f"{self.client.api_base.replace('api.', 'api.')}call.cgi"
        # Trading API 端点
        if self.client.env_config.get("environment") == "sandbox":
            endpoint = "https://api.sandbox.ebay.com/ws/api.dll"
        else:
            endpoint = "https://api.ebay.com/ws/api.dll"

        resp = requests.post(endpoint, headers=headers, data=xml_request, timeout=60)

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

        # 解析 XML 响应
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(resp.content)
            ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}

            # 检查是否成功
            ack = root.find(".//ebay:Ack", ns)
            if ack is None or ack.text not in ["Success", "Warning"]:
                error_msg = root.find(".//ebay:ErrorMessage", ns)
                error_text = error_msg.text if error_msg is not None else "Unknown error"
                raise Exception(f"eBay API 错误：{error_text}")

            # 获取 PictureURL
            picture_url = root.find(".//ebay:PictureURL", ns)
            if picture_url is not None and picture_url.text:
                return picture_url.text
            else:
                raise Exception("未返回 PictureURL")

        except ET.ParseError as e:
            raise Exception(f"XML 解析失败：{e}")

    def upload_from_url(self, image_url: str) -> UploadResult:
        """
        从 URL 下载并上传图片

        Args:
            image_url: 图片 URL

        Returns:
            UploadResult
        """
        result = UploadResult(file_path=image_url)

        try:
            # 下载图片
            resp = requests.get(image_url, timeout=30)
            if resp.status_code != 200:
                result.error = f"下载失败：HTTP {resp.status_code}"
                return result

            img_data = resp.content
            result.size_before = len(img_data)

            # 确定文件扩展名
            content_type = resp.headers.get("Content-Type", "")
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
            }
            ext = ext_map.get(content_type.split(";")[0], ".jpg")

            # 上传到 eBay
            picture_url = self._upload_to_ebay(img_data, ext)
            if picture_url:
                result.picture_url = picture_url
                result.success = True
                result.size_after = len(img_data)
                logger.info(f"[{image_url}] 上传成功：{picture_url}")
            else:
                result.error = "上传失败：未返回 PictureURL"

        except Exception as e:
            result.error = f"上传失败：{e}"
            logger.error(f"[{image_url}] {result.error}")

        return result


# ─── 命令行工具 ──────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json
    from ebay_client import EbayClient

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    print("=" * 60)
    print("🖼️  eBay 图片上传工具")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("\n用法:")
        print("  python3 ebay_image_uploader.py <图片文件/文件夹>")
        print("  python3 ebay_image_uploader.py image1.jpg image2.jpg")
        print("  python3 ebay_image_uploader.py ./product_images/")
        sys.exit(1)

    # 初始化客户端
    try:
        client = EbayClient()
        uploader = EbayImageUploader(client)
    except Exception as e:
        print(f"❌ 初始化失败：{e}")
        sys.exit(1)

    # 处理输入
    args = sys.argv[1:]
    all_results = []

    for arg in args:
        path = Path(arg)
        if path.is_dir():
            results = uploader.upload_from_folder(str(path))
            all_results.extend(results)
        elif path.is_file():
            result = uploader.upload_local_image(str(path))
            all_results.append(result)
        else:
            # 可能是 URL
            if arg.startswith("http"):
                result = uploader.upload_from_url(arg)
                all_results.append(result)
            else:
                print(f"⚠️  跳过不存在的路径：{arg}")

    # 输出结果
    print("\n" + "=" * 60)
    print("上传结果汇总")
    print("=" * 60)

    success_count = sum(1 for r in all_results if r.success)
    print(f"成功：{success_count}/{len(all_results)}")

    for r in all_results:
        status = "✅" if r.success else "❌"
        print(f"\n{status} {r.file_path}")
        if r.success:
            print(f"   URL: {r.picture_url}")
            print(f"   大小：{r.size_after/1024:.1f}KB")
        else:
            print(f"   错误：{r.error}")

    # 输出 JSON 结果（便于脚本调用）
    print("\n" + "=" * 60)
    print("JSON 输出:")
    print("=" * 60)
    output = {
        "total": len(all_results),
        "success": success_count,
        "pictures": [
            {"file": r.file_path, "url": r.picture_url, "success": r.success, "error": r.error}
            for r in all_results
        ]
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
