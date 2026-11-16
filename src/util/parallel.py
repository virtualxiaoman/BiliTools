"""并发执行工具：按输入顺序返回结果。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional


def parallel_run(
    items,
    fn: Callable[[Any, int], Any],
    threads: int,
    on_complete: Optional[Callable[[int, Any], None]] = None,
) -> list:
    """并发执行 ``fn(item, idx)``，返回按输入顺序排列的结果列表。

    ``on_complete`` 会在每个任务实际完成后立即调用，调用顺序是任务完成顺序，
    而不是输入顺序。结果列表本身仍按输入顺序排列，避免改变下载接口的返回值语义。

    :param items: 输入列表
    :param fn: fn(item, index) -> result；异常会上抛（线程池退出时会等其余任务跑完）
    :param threads: 并发线程数
    :param on_complete: 可选的完成回调，签名为 ``(index, result)``
    """
    results: list = [None] * len(items)
    if len(items) <= 1 or threads <= 1:
        for i, item in enumerate(items):
            result = fn(item, i)
            results[i] = result
            if on_complete is not None:
                on_complete(i, result)
        return results
    with ThreadPoolExecutor(max_workers=threads) as ex:
        future_to_idx = {ex.submit(fn, item, i): i for i, item in enumerate(items)}
        for future in as_completed(future_to_idx):
            index = future_to_idx[future]
            result = future.result()
            results[index] = result
            if on_complete is not None:
                on_complete(index, result)
    return results
