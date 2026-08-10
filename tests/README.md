# 测试说明

## 运行方式

```bash
# 安装 pytest
pip install pytest

# 只跑单元测试（不联网，推荐日常使用）
pytest -m "not network"

# 跑全部测试（含真实网络，需要能访问 B 站且 cookie 已登录）
pytest --network

# 只跑某个文件
pytest tests/test_bvid.py
```

## 测试分类

| 文件 | 类型 | 内容 |
|------|------|------|
| `test_bvid.py` | 单元 | BV/AV 转换（含已知对照 + 往返 + 边界） |
| `test_filename.py` | 单元 | 文件名清洗与 `[标题](BV号).ext` 命名规则 |
| `test_cookie.py` | 单元 | Cookie 解析 / 进程内缓存 / refresh / 异常 |
| `test_auth.py` | 单元 | wbi 签名、设备ID、HMAC-SHA256、key 缓存 |
| `test_errors.py` | 单元 | 异常体系与错误码映射 |
| `test_models.py` | 单元 | dataclass 构造（VideoInfo/HistoryPage/LoginUser 等） |
| `test_api_bilibili.py` | 网络 | BiliSession 请求 / wbi / 错误路径（需 B 站） |
| `test_services_bilibili.py` | 网络 | 各 service 真实调用（含下载小文件，需登录） |

## 注意事项

- 网络测试用 `@pytest.mark.network` 标记，默认被跳过；`conftest.py` 提供跳过逻辑。
- 网络测试依赖 `assets/cookie/qr_login.txt`（已登录的 cookie），否则登录类测试会失败。
- 下载测试使用最小清晰度（P360），避免下载大文件拖慢测试。
- 测试会真实写入 `output/` 与临时目录，下载测试用 pytest 的 `tmp_path` fixture 自动清理。
