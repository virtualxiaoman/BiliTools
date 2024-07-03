class Config:
    def __init__(self):
        self.LOGIN_COOKIE_PATH = "cookie/qr_login.txt"
        self.LOGIN_QR_PATH = "cookie/qr_login.png"
        self.MAX_RETRY = 3  # 最大重试次数3次
        self.RETRY_DELAY = 1.2  # 重试延迟1.2秒


class bilicookies:
    def __init__(self, path=Config().LOGIN_COOKIE_PATH):
        try:
            with open(path, "r") as file:
                self.bilicookie = file.read()  # 读取cookie文件
        except FileNotFoundError:
            raise FileNotFoundError("Cookie 文件不存在: {}".format(path))
        except Exception as e:
            raise Exception("读取 Cookie 文件时发生错误: {}".format(str(e)))
        self.bilicookie = open(path, "r").read()
        self.SESSDATA = None
        self.bili_jct = None  # csrf参数
        self.get_SESSDATA()
        self.get_bili_jct()

    def get_SESSDATA(self):
        # 使用split()方法根据分号";"将字符串拆分成多个子字符串
        cookie_parts = self.bilicookie.split(";")
        # 遍历这些子字符串，找到以"SESSDATA="开头的子字符串
        SESSDATA_value = None
        for part in cookie_parts:
            if part.strip().startswith("SESSDATA="):
                key_value_pair = part.split("=")  # 使用split()方法根据等号"="将该子字符串拆分成键值对
                SESSDATA_value = key_value_pair[1]  # 提取键值对中的值，即SESSDATA的值
                break
        self.SESSDATA = SESSDATA_value
        if self.SESSDATA is None:
            print("SESSDATA not found in cookies")
            exit(1)

    def get_bili_jct(self):
        # 使用split()方法根据分号";"将字符串拆分成多个子字符串
        cookie_parts = self.bilicookie.split(";")
        # 遍历这些子字符串，找到以"bili_jct="开头的子字符串
        bili_jct_value = None
        for part in cookie_parts:
            if part.strip().startswith("bili_jct="):
                key_value_pair = part.split("=")
                bili_jct_value = key_value_pair[1]
                break
        self.bili_jct = bili_jct_value
        if self.bili_jct is None:
            print("bili_jct not found in cookies")
            exit(1)

class useragent:
    def __init__(self):
        self.pcChrome = """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"""
