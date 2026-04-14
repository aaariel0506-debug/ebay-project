"""
Token 安全存储 — 使用 Fernet 对称加密
Linux 环境下（无 macOS Keychain / SecretService），将 token 加密存储到文件。
加密密钥来自 settings.TOKEN_ENCRYPTION_KEY（.env 中配置）。
"""
import keyring
import keyrings.alt.file
from core.config.settings import settings


class TokenStore:
    """
    安全存储和读取 token。
    使用 keyrings.alt.file.EncryptedKeyring，加密存储到文件。
    密钥来自 TOKEN_ENCRYPTION_KEY 环境变量。
    """

    SERVICE_NAME = "ebay-ms"

    def __init__(self):
        self._init_keyring()

    def _init_keyring(self) -> None:
        """初始化加密 keyring，使用 TOKEN_ENCRYPTION_KEY 作为密码"""
        key = settings.TOKEN_ENCRYPTION_KEY
        if not key:
            return
        try:
            enc_keyring = keyrings.alt.file.EncryptedKeyring()
            enc_keyring.keyring_key = key
            keyring.set_keyring(enc_keyring)
        except Exception:
            pass

    def save_token(self, token_name: str, token: str) -> None:
        """保存 token（加密存储）"""
        try:
            keyring.set_password(self.SERVICE_NAME, token_name, token)
        except Exception as e:
            raise RuntimeError(f"Failed to save token '{token_name}': {e}")

    def get_token(self, token_name: str) -> str | None:
        """读取 token"""
        try:
            return keyring.get_password(self.SERVICE_NAME, token_name)
        except Exception:
            return None

    def delete_token(self, token_name: str) -> None:
        """删除 token"""
        try:
            keyring.delete_password(self.SERVICE_NAME, token_name)
        except Exception:
            pass


# 单例
token_store = TokenStore()
