"""最简单的 BiliTools 示例：扫码登录并下载一个视频。

从项目根目录执行：

    python -m examples.quick_start

首次运行会显示二维码，扫码成功后自动下载视频。之后再次运行时，
如果希望跳过扫码，可改用 examples/account.py 先检查登录状态，或直接复用已保存的 cookie。
"""

from src.services import LoginService, VideoService


# 可以替换成任意公开的视频 BV 号。
BVID = "BV1ov42117yC"


def login_and_download() -> None:
    # 1. 生成二维码并轮询登录状态；成功后 cookie 会保存到当前账号的 cookie 路径。
    if not LoginService().qr_login(timeout=120):
        raise SystemExit("扫码登录失败或超时，程序结束。")

    # 2. VideoService 读取刚保存的 cookie，完成 VIEW -> PLAY -> DASH -> 下载/合成流程。
    result = VideoService().download_video_with_audio(BVID)
    print(f"下载完成：{result.path}")


if __name__ == "__main__":
    login_and_download()
