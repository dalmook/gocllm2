from __future__ import annotations

import base64
import json
import time
from typing import Any, Dict, Optional

import requests


class AESCipher:
    def __init__(self, key_hex: str):
        try:
            from Cryptodome.Cipher import AES as _AES
        except Exception as e:
            raise RuntimeError("Cryptodome is required for Knox AES encryption/decryption") from e
        self.bs = 16
        self._aes = _AES
        raw = bytes.fromhex(key_hex)
        self.key = raw[0:32]
        self.iv = raw[32:48]

    def _pad(self, b: bytes) -> bytes:
        pad_len = self.bs - (len(b) % self.bs)
        return b + bytes([pad_len]) * pad_len

    def _unpad(self, b: bytes) -> bytes:
        return b[: -b[-1]]

    def encrypt(self, data: str) -> str:
        pt = self._pad(data.encode("utf-8"))
        cipher = self._aes.new(self.key, self._aes.MODE_CBC, self.iv)
        ct = cipher.encrypt(pt)
        return base64.b64encode(ct).decode("utf-8")

    def decrypt(self, data_b64: bytes) -> str:
        ct = base64.b64decode(data_b64)
        cipher = self._aes.new(self.key, self._aes.MODE_CBC, self.iv)
        pt = self._unpad(cipher.decrypt(ct))
        return pt.decode("utf-8", errors="ignore")


class KnoxMessenger:
    def __init__(self, host: str, system_id: str, token: str, *, verify_ssl: bool = False):
        self.host = host
        self.system_id = system_id
        self.token = token
        self.verify_ssl = verify_ssl

        self.user_id = ""
        self.x_device_id = ""
        self.key = ""

        self.session = requests.Session()

    def device_regist(self, max_retries: int = 3, retry_delay: int = 4) -> None:
        api = "/messenger/contact/api/v1.0/device/o1/reg"
        header = {"Authorization": self.token, "System-ID": self.system_id}
        last_err: Exception | None = None

        for _ in range(max_retries):
            try:
                resp = self.session.get(self.host + api, headers=header, verify=self.verify_ssl, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                self.user_id = str(data["userID"])
                self.x_device_id = str(data["deviceServerID"])
                return
            except Exception as e:
                last_err = e
                time.sleep(retry_delay)

        raise RuntimeError(f"knox device_regist failed: {last_err}")

    def get_keys(self) -> None:
        api = "/messenger/msgctx/api/v1.0/key/getkeys"
        header = {"Authorization": self.token, "x-device-id": self.x_device_id}
        resp = self.session.get(self.host + api, headers=header, verify=self.verify_ssl, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self.key = data["key"]

    def _post_encrypted(self, api: str, body_dict: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        header = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.token,
            "System-ID": self.system_id,
            "x-device-id": self.x_device_id,
            "x-device-type": "relation",
        }
        if extra_headers:
            header.update(extra_headers)

        request_id = int(round(time.time() * 1000))
        body_dict.setdefault("requestId", request_id)

        cipher = AESCipher(self.key)
        enc_body = cipher.encrypt(json.dumps(body_dict, ensure_ascii=False))
        resp = self.session.post(self.host + api, headers=header, data=enc_body, verify=self.verify_ssl, timeout=15)
        resp.raise_for_status()
        return json.loads(cipher.decrypt(resp.text.encode("utf-8")))

    def send_text(self, chatroom_id: int, text: str) -> Dict[str, Any]:
        api = "/messenger/message/api/v1.0/message/chatRequest"
        request_id = int(round(time.time() * 1000))
        body = {
            "requestId": request_id,
            "chatroomId": int(chatroom_id),
            "chatMessageParams": [{"msgId": request_id, "msgType": 0, "chatMsg": text, "msgTtl": 3600}],
        }
        return self._post_encrypted(api, body)

    def send_adaptive_card(self, chatroom_id: int, card: Dict[str, Any]) -> Dict[str, Any]:
        api = "/messenger/message/api/v1.0/message/chatRequest"
        request_id = int(round(time.time() * 1000))
        payload = {"adaptiveCards": json.dumps(card, ensure_ascii=False)}
        body = {
            "requestId": request_id,
            "chatroomId": int(chatroom_id),
            "chatMessageParams": [
                {
                    "msgId": request_id,
                    "msgType": 19,
                    "chatMsg": json.dumps(payload, ensure_ascii=False),
                    "msgTtl": 3600,
                }
            ],
        }
        return self._post_encrypted(api, body)

    def recall_message(self, chatroom_id: int, msg_id: int, sent_time: int) -> Dict[str, Any]:
        api = "/messenger/message/api/v1.0/message/recallMessageRequest"
        body = {
            "chatroomId": int(chatroom_id),
            "msgId": int(msg_id),
            "sentTime": int(sent_time),
        }
        return self._post_encrypted(api, body)
