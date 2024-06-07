import inspect

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

CT = ColoredText

def _func_warning(func=None, warning_text=None, modify_tip=None):
    """
    输出函数的警告信息
    :param func: 函数本身、
    :param warning_text: 警告信息
    :param modify_tip: 建议修改的提示
    """
    if func is not None:
        func_name = func.__name__
        file_name = inspect.getsourcefile(func)
        file_name = file_name.split("/")[-1]  # 获取文件名
    else:
        raise ValueError("func_name不能为None")
    if warning_text is None:
        raise ValueError("warning_text不能为None")
    if modify_tip is None:
        modify_tip = "没有建议修改的提示"
    print(CT("Warning in func").red(), CT(file_name+'\\'+func_name).yellow(),
          CT(f": {warning_text}。\n修改建议:").red(), CT(f"{modify_tip}").pink())




