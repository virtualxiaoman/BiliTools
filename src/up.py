import requests
import json
import base64

from src.config import UserAgent
from src.config import BiliCookies as Cookies
from src.utils import AuthUtil

import requests


class BiliUserInfo:
    def __init__(self, mid):
        self.mid = mid
        self.info = None
        self.wts, self.w_rid = AuthUtil().get_wbi()

    def fetch_info(self):
        """方法一：直接使用传入的签名参数访问接口"""
        url = "https://api.bilibili.com/x/space/wbi/acc/info"
        url = "https://api.bilibili.com/x/space/acc/info"
        params = {
            'mid': self.mid,
            'w_rid': self.w_rid,
            'wts': self.wts
        }
        params = self._append_bili_risk_params(params)  # 追加风控参数
        # todo 此处参数已经失效：以下是一个成功的参数，目前来看似乎所有的参数都必须使用
        # https://api.bilibili.com/x/space/wbi/acc/info?mid=47261023&token=&platform=web&web_location=1550101&dm_img_list=[%7B%22x%22:966,%22y%22:1288,%22z%22:0,%22timestamp%22:7,%22k%22:74,%22type%22:0%7D]&dm_img_str=V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ&dm_cover_img_str=QU5HTEUgKE5WSURJQSwgTlZJRElBIEdlRm9yY2UgUlRYIDUwODAgTGFwdG9wIEdQVSAoMHgwMDAwMkM1OSkgRGlyZWN0M0QxMSB2c181XzAgcHNfNV8wLCBEM0QxMSlHb29nbGUgSW5jLiAoTlZJRElBKQ&dm_img_inter=%7B%22ds%22:[%7B%22t%22:4,%22c%22:%22ZGVmYXVsdC1lbnRyeQ%22,%22p%22:[770,64,-225],%22s%22:[180,434,272]%7D],%22wh%22:[3412,2149,0],%22of%22:[128,256,128]%7D&w_webid=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzcG1faWQiOiIzMzMuMTM4NyIsImJ1dmlkIjoiRTVFRkYwRjQtNjg0NC0zQzVELTQxODYtNTBDQkI0MjEzNzlDMTUyMjFpbmZvYyIsInVzZXJfYWdlbnQiOiJNb3ppbGxhLzUuMCAoV2luZG93cyBOVCAxMC4wOyBXaW42NDsgeDY0KSBBcHBsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBsaWtlIEdlY2tvKSBDaHJvbWUvMTQ1LjAuMC4wIFNhZmFyaS81MzcuMzYgRWRnLzE0NS4wLjAuMCIsImJ1dmlkX2ZwIjoiMzE5MThmYjg4MGU4NmY0ZTEwZGY4MTU5ZjIwOWI2ZmIiLCJiaWxpX3RpY2tldCI6ImV5SmhiR2NpT2lKSVV6STFOaUlzSW10cFpDSTZJbk13TXlJc0luUjVjQ0k2SWtwWFZDSjkuZXlKbGVIQWlPakUzTnpFNU5ESTFOeklzSW1saGRDSTZNVGMzTVRZNE16TXhNaXdpY0d4MElqb3RNWDAuMmZPR0MtbHRSMXJ6N2d2NVU0djRsbjZrdHQ5TVBQQ2ozbEI0SEl0MU53OCIsImNyZWF0ZWRfYXQiOjE3NzE3NzAzMDUsInR0bCI6ODY0MDAsInVybCI6Ii80NzI2MTAyMyIsInJlc3VsdCI6MCwiaXNzIjoiZ2FpYSIsImlhdCI6MTc3MTc3MDMwNX0.fOcpLhLpAY4IXr0tFdcni0ElTfGcuNF5E8FbwM4nhfbhoe13zw4_gP291VKsxlV8wvP_gNag7fSFCzCRuQsZg6qEgKBxAN-vFJWIgd9CYd7bTJ1-FoGt6sJF-GUGfstlRMWP__CVJVazsoyZE8eUhDBe_DcPc5RXqd0TnTnUsbV1FBhyH7slTVTqybuo1ZwancvgEiiHe6LmsaIN6ylA2uZ0hkUe93HByULHQgajTv9rIUc6kjzlIfnDK6PuzwUhbXcvx7wpBFJZ-75MISvK_-1gr25mgp5ve6-g3KgIVMxO4zcX4Lk_ssB3KdMdUV7VMGwSa6iQLexONpct_bnuXg&w_rid=2da684901f464b6a4a6a008ffadcf58b&wts=1771770305
        # 可能可以参考https://www.52pojie.cn/thread-2040484-1-1.html

        headers = {
            'User-Agent': UserAgent().pcChrome,
            'Cookie': Cookies().bilicookie,
            'Referer': f'https://space.bilibili.com/{self.mid}/'
        }

        try:
            response = requests.get(url, params=params, headers=headers)
            res_json = response.json()
            if res_json.get('code') == 0:
                self.info = res_json
            else:
                print(f"API报错: {res_json.get('message')} (Code: {res_json.get('code')})")
        except Exception as e:
            print(f"请求发生异常: {e}")

    def get_name(self):
        """方法二：获取昵称，若无数据则触发 fetch_info"""
        if self.info is None:
            self.fetch_info()

        # 再次检查 self.info 是否获取成功
        if self.info and 'data' in self.info:
            # 检查mid是否匹配
            if self.info['data'].get('mid') == self.mid:
                return self.info['data'].get('name')
            else:
                print(f"请注意数据错误: 返回的mid {self.info['data'].get('mid')} 与请求的mid {self.mid} 不匹配")
                # todo 以后该函数可以试着支持重新传mid
        return None

    @staticmethod
    def _append_bili_risk_params(params):
        """
        向现有的 params 字典中追加 B 站空间页所需的风控和设备指纹参数。
        """
        # 1. 固定的基础参数
        params['token'] = ''
        params['platform'] = 'web'
        params['web_location'] = '1550101'

        # 2. 生成显卡 WebGL 指纹 (Base64编码，并强制去掉末尾的 '=')
        # 使用常见的浏览器和显卡指纹，降低被风控的概率
        webgl_vendor = "WebGL 1.0 (OpenGL ES 2.0 Chromium)".encode('utf-8')
        params['dm_img_str'] = base64.b64encode(webgl_vendor).decode('utf-8').rstrip('=')

        webgl_renderer = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)Google Inc. (NVIDIA)".encode(
            'utf-8')
        params['dm_cover_img_str'] = base64.b64encode(webgl_renderer).decode('utf-8').rstrip('=')

        # 3. 生成用户交互轨迹 (必须转换为没有空格的 JSON 字符串)
        dm_img_list = [{"x": 966, "y": 1288, "z": 0, "timestamp": 7, "k": 74, "type": 0}]
        params['dm_img_list'] = json.dumps(dm_img_list, separators=(',', ':'))

        dm_img_inter = {
            "ds": [{"t": 4, "c": "default-entry", "p": [770, 64, -225], "s": [180, 434, 272]}],
            "wh": [3412, 2149, 0],
            "of": [128, 256, 128]
        }
        params['dm_img_inter'] = json.dumps(dm_img_inter, separators=(',', ':'))

        # 4. 补充 w_webid (设备/请求票据)
        # 注意：这个值是 B 站后端基于你的 IP 和目标 mid 动态签发的 JWT，有效期通常为 24 小时。
        # 这里先留一个接口传入你抓包到的值，实际生产环境中建议动态获取。
        params['w_webid'] = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzcG1faWQiOiIzMzMuMTM4NyIsImJ1dmlkIjoiRTVFRkYwRjQtNjg0NC0zQzVELTQxODYtNTBDQkI0MjEzNzlDMTUyMjFpbmZvYyIsInVzZXJfYWdlbnQiOiJNb3ppbGxhLzUuMCAoV2luZG93cyBOVCAxMC4wOyBXaW42NDsgeDY0KSBBcHBsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBsaWtlIEdlY2tvKSBDaHJvbWUvMTQ1LjAuMC4wIFNhZmFyaS81MzcuMzYgRWRnLzE0NS4wLjAuMCIsImJ1dmlkX2ZwIjoiMzE5MThmYjg4MGU4NmY0ZTEwZGY4MTU5ZjIwOWI2ZmIiLCJiaWxpX3RpY2tldCI6ImV5SmhiR2NpT2lKSVV6STFOaUlzSW10cFpDSTZJbk13TXlJc0luUjVjQ0k2SWtwWFZDSjkuZXlKbGVIQWlPakUzTnpFNU5ESTFOeklzSW1saGRDSTZNVGMzTVRZNE16TXhNaXdpY0d4MElqb3RNWDAuMmZPR0MtbHRSMXJ6N2d2NVU0djRsbjZrdHQ5TVBQQ2ozbEI0SEl0MU53OCIsImNyZWF0ZWRfYXQiOjE3NzE3NzAzMDUsInR0bCI6ODY0MDAsInVybCI6Ii80NzI2MTAyMyIsInJlc3VsdCI6MCwiaXNzIjoiZ2FpYSIsImlhdCI6MTc3MTc3MDMwNX0.fOcpLhLpAY4IXr0tFdcni0ElTfGcuNF5E8FbwM4nhfbhoe13zw4_gP291VKsxlV8wvP_gNag7fSFCzCRuQsZg6qEgKBxAN-vFJWIgd9CYd7bTJ1-FoGt6sJF-GUGfstlRMWP__CVJVazsoyZE8eUhDBe_DcPc5RXqd0TnTnUsbV1FBhyH7slTVTqybuo1ZwancvgEiiHe6LmsaIN6ylA2uZ0hkUe93HByULHQgajTv9rIUc6kjzlIfnDK6PuzwUhbXcvx7wpBFJZ-75MISvK_-1gr25mgp5ve6-g3KgIVMxO4zcX4Lk_ssB3KdMdUV7VMGwSa6iQLexONpct_bnuXg'

        return params


class BiliContract:
    """
    Bilibili 契约功能管理类
    """

    def __init__(self):
        """
        初始化
        """
        self.url = "https://api.bilibili.com/x/v1/contract/add_contract"
        self.csrf = Cookies().bili_jct
        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Referer": "https://www.bilibili.com/",
            "Cookie": Cookies().bilicookie,
            "Content-Type": "application/x-www-form-urlencoded"
        }

    def add_contract(self, up_mid: int) -> bool:
        """
        执行签约请求
        :param up_mid: 目标UP主的UID
        :return: 是否成功
        """
        payload = {
            "aid": "",
            "up_mid": up_mid,
            "source": "4",
            "scene": "105",
            "platform": "web",
            "mobi_app": "pc",
            "csrf": self.csrf
        }

        try:
            response = requests.post(self.url, data=payload, headers=self.headers, timeout=10)
            response.raise_for_status()  # 检查 HTTP 状态码

            res_json = response.json()
            # 根据文档，code 为 0 表示成功
            if res_json.get("code") == 0:
                user_info = BiliUserInfo(up_mid)
                up_name = user_info.get_name() or ""
                print(f"成功成为UP主 {up_name} (UID: {up_mid}) 的老粉！")
                return True
            else:
                print(f"签约失败，错误码：{res_json.get('code')}，消息：{res_json.get('message')}")
                return False

        except Exception as e:
            print(f"请求发生异常: {e}")
            return False


# --- 使用示例 ---
if __name__ == "__main__":
    bilic = BiliContract()
    ans = bilic.add_contract(up_mid=47261023)
    print(f"操作结果: {ans}")
