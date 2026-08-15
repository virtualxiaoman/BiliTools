"""
登录服务：扫码登录、登录状态查询。

取代旧 `src/login.py` 的 `BiliLogin`：
- `generate_qr()` / `poll()` 拆为无状态接口，轮询交给调用方（UI 线程），服务本身不阻塞；
- cookie 的解析/保存统一走 `src/config/cookie.py` 与 `src/config/path.py`；
- 登录成功后调用 `BiliCookies.refresh()` 使新 cookie 全局生效。

[使用方法]
    service = LoginService()
    url, qr_key = service.generate_qr()
    # 展示 url 生成的二维码给用户扫描
    result = service.poll(qr_key)  # 循环调用直至返回登录成功
    print(result)
"""

import logging
import time
from pathlib import Path
from typing import Optional, Tuple

from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.config.path import DEFAULT_COOKIE_PATH, DEFAULT_QR_IMAGE_PATH
from src.models.login_model import LoginUser
from src.urls.login_urls import LoginUrls

logger = logging.getLogger(__name__)

# 二维码轮询状态码（来自 BAC 文档）
_QR_POLL_CODES = {
    86101: "未扫码",
    86038: "二维码失效",
    86090: "扫码成功但未确认",
    0: "登录成功",
}


class LoginService:
    """B 站登录服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    # ---- 登录状态 ----

    def get_login_state(self) -> LoginUser:
        """获取登录状态与当前用户信息。

        :return: LoginUser。本地无有效登录凭证（无 cookie 文件或无 SESSDATA）时，
                 视为未登录，直接返回 is_login=False 的 LoginUser（不发网络请求）。
        """
        if not self.session.cookie.has_valid_session:
            return LoginUser()
        data = self.session.get(LoginUrls.LOGIN_STATE)
        return LoginUser.from_nav_json(data)

    def get_mid(self) -> Optional[int]:
        """获取当前登录用户 UID/mid。"""
        return self.get_login_state().mid

    def get_uname(self) -> str:
        """获取当前登录用户名。"""
        return self.get_login_state().uname

    # ---- 扫码登录 ----

    def generate_qr(self, save_qr_path: Optional[Path] = None) -> Tuple[str, str]:
        """生成扫码登录二维码。

        :param save_qr_path: 二维码图片保存路径。None 时保存到 QR_IMAGE_PATH（assets/cookie/qr_login.png）
        :return: (二维码登录 url, qrcode_key)，将 url 交给用户扫描
        """
        data = self.session.get(LoginUrls.QR_GENERATE)
        qrcode_key = data["qrcode_key"]
        url = data["url"]

        # 生成并保存二维码图片
        try:
            import qrcode
        except ImportError:
            logger.warning("[LoginService] 未安装 qrcode 库，跳过二维码图片生成，仅返回登录 url。")
            return url, qrcode_key

        save_path = Path(save_qr_path) if save_qr_path is not None else DEFAULT_QR_IMAGE_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)
        qr = qrcode.QRCode()
        qr.add_data(url)
        qr.make()
        img = qr.make_image()
        img.save(str(save_path))
        logger.info("[LoginService] 二维码已保存到 %s", save_path.resolve())
        return url, qrcode_key

    def poll(self, qrcode_key: str) -> int:
        """轮询一次扫码登录状态（不阻塞）。

        :param qrcode_key: generate_qr 返回的 key
        :return: 状态码。0 表示登录成功；其他见 _QR_POLL_CODES
        """
        code, _ = self._poll_once(qrcode_key)
        return code

    def poll_full(self, qrcode_key: str) -> Tuple[int, Optional[str]]:
        """轮询一次扫码登录状态，返回 (状态码, set-cookie)。

        与 `poll()` 的区别：登录成功时把响应头里的 set-cookie 一并返回，
        供 UI 直接调用 `save_cookie()` 保存（poll 只返回状态码、丢弃了 cookie）。

        :param qrcode_key: generate_qr 返回的 key
        :return: (状态码, set-cookie 原始字符串)。登录成功时 set-cookie 非空
        """
        code, resp = self._poll_once(qrcode_key)
        return code, resp.headers.get("set-cookie", "") or None

    def _poll_once(self, qrcode_key: str):
        """轮询一次并返回 (状态码, 响应)。登录成功时响应头含 set-cookie。"""
        resp = self.session.session.get(
            LoginUrls.QR_LOGIN, params={"qrcode_key": qrcode_key}, timeout=self.session.timeout
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        code = data.get("code")
        logger.info("[LoginService] 二维码状态码 %s：%s", code, _QR_POLL_CODES.get(code, "未知"))
        return code, resp

    def qr_login(
        self,
        *,
        timeout: float = 60.0,
        interval: float = 1.0,
        save_cookie_path: Optional[Path] = None,
        img_show: bool = True,
    ) -> bool:
        """完整扫码登录流程：生成二维码 → 轮询直到登录成功/超时。

        [注意] 该方法内部阻塞轮询，UI 场景请使用 generate_qr + poll 自行驱动。

        :param timeout: 超时时间（秒），超时返回 False
        :param interval: 轮询间隔（秒）
        :param save_cookie_path: cookie 保存路径。None 时保存到 DEFAULT_COOKIE_PATH
        :param img_show: 是否用本地图片查看器打开二维码
        :return: 登录成功返回 True
        """
        url, qrcode_key = self.generate_qr()
        if img_show:
            try:
                from PIL import Image
                # 二维码图片由 generate_qr 保存到 QR_IMAGE_PATH（或自定义路径），这里打开同一份
                qr_img_path = DEFAULT_QR_IMAGE_PATH
                if not qr_img_path.exists():
                    logger.warning("[LoginService] 二维码图片不存在：%s", qr_img_path)
                else:
                    Image.open(str(qr_img_path)).show()
            except Exception as e:
                logger.warning("[LoginService] 打开二维码图片失败：%s", e)

        save_path = Path(save_cookie_path) if save_cookie_path is not None else DEFAULT_COOKIE_PATH
        start = time.time()
        while time.time() - start < timeout:
            code, resp = self._poll_once(qrcode_key)
            if code == 0:
                # 登录成功：响应头携带 set-cookie
                set_cookie = resp.headers.get("set-cookie", "")
                if not set_cookie:
                    logger.warning("[LoginService] 登录成功但未获取到 set-cookie，请手动检查 cookie 文件。")
                    return True
                self.save_cookie(set_cookie, save_path)
                return True
            time.sleep(interval)
        logger.warning("[LoginService] 扫码登录超时（%.0fs）", timeout)
        return False

    def save_cookie(self, cookie: str, full_path: Optional[Path] = None) -> Path:
        """保存 cookie 字符串到文件，并刷新全局 cookie 缓存。

        从原始 set-cookie 中提取 SESSDATA/bili_jct/DedeUserID 等关键字段（含登录成功 url 中的 cookie）。

        :param cookie: 原始 cookie 字符串（通常是响应头 set-cookie）
        :param full_path: 保存路径。None 时保存到 DEFAULT_COOKIE_PATH
        :return: 保存的文件路径
        """
        import re

        save_path = Path(full_path) if full_path is not None else DEFAULT_COOKIE_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # 提取关键字段（原始实现来自旧 login.py 的正则解析）
        patterns = {
            "SESSDATA": r"SESSDATA=(.*?)(?:;|$)",
            "bili_jct": r"bili_jct=(.*?)(?:;|$)",
            "DedeUserID": r"DedeUserID=(.*?)(?:;|$)",
            "DedeUserID__ckMd5": r"DedeUserID__ckMd5=(.*?)(?:;|$)",
            "sid": r"sid=(.*?)(?:;|$)",
        }
        extracted = []
        for key, pattern in patterns.items():
            match = re.search(pattern, cookie)
            if match:
                extracted.append(f"{key}={match.group(1)}")
        cookie_string = "; ".join(extracted) if extracted else cookie.strip()

        save_path.write_text(cookie_string, encoding="utf-8")
        logger.info("[LoginService] cookie 已保存到 %s", save_path.resolve())
        # 刷新全局缓存，使新 cookie 立即生效
        BiliCookies.refresh(save_path)
        return save_path
