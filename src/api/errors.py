"""
统一异常体系。

旧代码以 `return False / None / -1 / 114514 / print` 混合表达失败，
调用方（尤其是 UI）无法判断失败原因。这里收敛为异常，由上层决定处理方式。
"""


class BiliError(Exception):
    """B 站 API 相关错误的基类。"""


class BiliAuthError(BiliError):
    """未登录或登录已失效（典型错误码 -101）。"""


class BiliForbiddenError(BiliError):
    """权限不足 / 被拒绝访问（典型错误码 -403，如空间信息风控）。"""


class BiliRiskError(BiliError):
    """触发风控（典型错误码 -412），通常可稍后重试。"""


class BiliAPIError(BiliError):
    """API 返回的业务错误：携带错误码与错误信息。

    :param code: 接口返回的错误码（如 -352、-404）
    :param message: 接口返回的错误信息
    """

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Bilibili API 错误，错误码：{code}，错误信息：{message}")


class VideoNotFoundError(BiliAPIError):
    """视频不存在或已失效（典型错误码 -404）。"""


class DownloadError(BiliError):
    """下载失败（网络中断、文件写入失败、ffmpeg 合并失败等）。"""


class FFmpegNotFoundError(DownloadError):
    """系统未安装 ffmpeg，无法进行音视频合成。"""


def raise_for_code(code: int, message: str) -> None:
    """根据错误码抛出对应异常；code == 0 时直接返回。

    :param code: 接口返回的 code 字段
    :param message: 接口返回的 message 字段
    """
    if code == 0:
        return
    if code == -101:
        raise BiliAuthError(f"未登录，请先登录。错误信息：{message}")
    if code == -403:
        raise BiliForbiddenError(f"权限不足，错误信息：{message}")
    if code == -412:
        raise BiliRiskError(f"触发风控，请稍后重试。错误信息：{message}")
    if code == -404:
        raise VideoNotFoundError(code, message)
    raise BiliAPIError(code, message)
