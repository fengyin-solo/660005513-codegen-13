"""批量回测接口的回归测试。

运行：
    cd backend && pip install httpx
    PYTHONPATH=. python -m pytest tests/ -v
（没有 pytest 时也可直接执行本文件：python tests/test_batch.py）
"""
from fastapi.testclient import TestClient

from app.main import app, BATCH_MAX

client = TestClient(app)

BASE = {"lowerPrice": 95, "upperPrice": 115, "gridCount": 20,
        "capitalPerGrid": 1000, "initialCapital": 100000}


def _cfg(**overrides):
    c = dict(BASE)
    c.update(overrides)
    return c


def test_single_backtest_still_works():
    """原有单次回测入口不受影响。"""
    r = client.post("/api/backtest", json=BASE)
    assert r.status_code == 200
    data = r.json()
    for k in ("returnRate", "maxDrawdown", "sharpeRatio", "orders", "equityCurve"):
        assert k in data
    assert isinstance(data["sharpeRatio"], (int, float))


def test_batch_runs_every_valid_combo():
    r = client.post("/api/backtest/batch", json={"configs": [
        _cfg(cid=1),
        _cfg(cid=2, lowerPrice=90, upperPrice=110, gridCount=10, capitalPerGrid=2000),
        _cfg(cid=3, lowerPrice=92, upperPrice=118, gridCount=30, capitalPerGrid=800),
    ]})
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 3 and d["executed"] == 3 and d["skippedCount"] == 0
    for item in d["results"]:
        for k in ("returnRate", "maxDrawdown", "sharpeRatio", "tradeCount"):
            assert k in item
    # 两组参数不同，跑在同一段固定行情上，结果可以不同但都应产生
    assert len({x["returnRate"] for x in d["results"]}) >= 1


def test_batch_out_of_range_and_inverted_are_skipped_but_batch_survives():
    r = client.post("/api/backtest/batch", json={"configs": [
        _cfg(cid=1),
        _cfg(cid=2, lowerPrice=120, upperPrice=100),          # 下限>=上限
        _cfg(cid=3, gridCount=200),                            # 网格数越界
        _cfg(cid=4, lowerPrice=10),                            # 下限越界
        _cfg(cid=5, gridCount=40, capitalPerGrid=50000,
             initialCapital=10000),                            # 总资金超初始资金
        _cfg(cid=6, upperPrice=999),                           # 上限越界
    ]})
    d = r.json()
    assert d["executed"] == 1, d
    assert d["skippedCount"] == 5
    assert {s["index"] for s in d["skipped"]} == {2, 3, 4, 5, 6}
    assert all(s["reason"] for s in d["skipped"])


def test_batch_duplicate_points_to_first_occurrence():
    r = client.post("/api/backtest/batch", json={"configs": [
        _cfg(cid=10),
        _cfg(cid=11, lowerPrice=90, upperPrice=110),
        _cfg(cid=12),  # 与第 1 条重复
    ]})
    d = r.json()
    assert d["executed"] == 2
    dup = [s for s in d["skipped"] if s["index"] == 3][0]
    assert "第 10 条" in dup["reason"]  # 引用首条的 cid，与客户端草稿行号对齐


def test_batch_malformed_entries_never_fail_the_whole_batch():
    r = client.post("/api/backtest/batch", json={"configs": [
        _cfg(cid=1),
        {"cid": 2, "lowerPrice": "abc", **{k: v for k, v in BASE.items() if k != "lowerPrice"}},
        {"cid": 3, "upperPrice": 110},  # 缺字段
        [1, 2, 3],                      # 不是对象
        "garbage",
        _cfg(cid=5, lowerPrice=88, upperPrice=112, gridCount=24, capitalPerGrid=1200),
    ]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["executed"] == 2
    assert {s["index"] for s in d["skipped"]} == {2, 3, 4, 5}


def test_batch_over_limit_is_reported_per_row():
    configs = [_cfg(cid=i, lowerPrice=50 + i) for i in range(BATCH_MAX + 3)]
    r = client.post("/api/backtest/batch", json={"configs": configs})
    assert r.status_code == 200
    d = r.json()
    assert d["executed"] == BATCH_MAX
    over = [s for s in d["skipped"] if s["index"] > BATCH_MAX]
    assert len(over) == 3


if __name__ == "__main__":
    import inspect
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and inspect.isfunction(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
