class ColoredText:
    """
    用于更改输出到控制台的颜色
    使用方法：
        from easier_tools.Colorful_Console import ColoredText as CT
        print(CT("你要变蓝的文字").blue())
    """
    def __init__(self, text):
        self.RED = '\033[91m'
        self.YELLOW = '\033[93m'
        self.BLUE = '\033[94m'
        self.GREEN = '\033[92m'
        self.PINK = '\033[95m'
        self.END = '\033[0m'
        self.text = text

    def red(self):
        return f"{self.RED}{self.text}{self.END}"

    def yellow(self):
        return f"{self.YELLOW}{self.text}{self.END}"

    def blue(self):
        return f"{self.BLUE}{self.text}{self.END}"

    def green(self):
        return f"{self.GREEN}{self.text}{self.END}"

    def pink(self):
        return f"{self.PINK}{self.text}{self.END}"
