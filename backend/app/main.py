import asyncio, time, random, math, json, threading
from typing import Any, List, Optional
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Grid Trading Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ACTIVE_CLIENTS = []
SIM_RUNNING = True
current_price = 100.0
ticks_history = []

# 参数合法范围（与前端 GridControl 的输入边界保持一致）
LIMIT_LOWER, LIMIT_UPPER = 50.0, 200.0
GRID_MIN, GRID_MAX = 5, 50
CAPITAL_MIN, CAPITAL_MAX = 100.0, 50000.0
INITIAL_CAPITAL_MIN, INITIAL_CAPITAL_MAX = 10000.0, 1000000.0
BATCH_MAX = 50

class GridConfig(BaseModel):
    lowerPrice: float = 95
    upperPrice: float = 115
    gridCount: int = 20
    capitalPerGrid: float = 1000
    initialCapital: float = 100000


class BatchBacktestRequest(BaseModel):
    # 用 Any 逐条接收，单条类型/字段异常只会被跳过而不会让整批 422
    configs: List[Any]


REQUIRED_NUMERIC = ("lowerPrice", "upperPrice", "gridCount", "capitalPerGrid", "initialCapital")


def parse_batch_config(raw: dict):
    """把一条原始输入解析成 GridConfig；失败返回 (None, 原因)。"""
    missing = [k for k in REQUIRED_NUMERIC if k not in raw]
    if missing:
        return None, f"缺少必填参数: {', '.join(missing)}"
    bad_type = [k for k in REQUIRED_NUMERIC if not isinstance(raw[k], (int, float)) or isinstance(raw[k], bool)]
    if bad_type:
        return None, f"参数必须为数值: {', '.join(bad_type)}"
    try:
        c = GridConfig(**raw)
        return c, None
    except Exception as e:
        return None, f"参数格式有误: {e}"


def validate_grid_config(c) -> Optional[str]:
    """返回越界原因；合法时返回 None。"""
    if c.lowerPrice <= 0 or c.upperPrice <= 0 or c.capitalPerGrid <= 0 or c.initialCapital <= 0:
        return "价格与资金必须为正数"
    if not (LIMIT_LOWER <= c.lowerPrice <= LIMIT_UPPER):
        return f"下限价格超出允许范围 [{LIMIT_LOWER:g}, {LIMIT_UPPER:g}]"
    if not (LIMIT_LOWER <= c.upperPrice <= LIMIT_UPPER):
        return f"上限价格超出允许范围 [{LIMIT_LOWER:g}, {LIMIT_UPPER:g}]"
    if c.lowerPrice >= c.upperPrice:
        return "下限价格必须小于上限价格"
    if not (GRID_MIN <= c.gridCount <= GRID_MAX):
        return f"网格数量超出允许范围 [{GRID_MIN}, {GRID_MAX}]"
    if not (CAPITAL_MIN <= c.capitalPerGrid <= CAPITAL_MAX):
        return f"每格资金超出允许范围 [{CAPITAL_MIN:g}, {CAPITAL_MAX:g}]"
    if not (INITIAL_CAPITAL_MIN <= c.initialCapital <= INITIAL_CAPITAL_MAX):
        return f"初始资金超出允许范围 [{INITIAL_CAPITAL_MIN:g}, {INITIAL_CAPITAL_MAX:g}]"
    if c.gridCount * c.capitalPerGrid > c.initialCapital:
        return "总网格资金(网格数量×每格资金)不能超过初始资金"
    return None


def config_signature(c) -> tuple:
    """参与去重的四要素：下限、上限、网格数量、每格资金。"""
    return (
        round(float(c.lowerPrice), 4),
        round(float(c.upperPrice), 4),
        int(c.gridCount),
        round(float(c.capitalPerGrid), 4),
    )


def simulate_market():
    global current_price, ticks_history
    price = 100.0
    while SIM_RUNNING:
        drift = 0.005 * math.sin(time.time() * 0.05)
        price += random.gauss(drift, 0.3)
        price = max(80, min(130, price))
        current_price = price
        tick = {
            "time": time.strftime("%H:%M:%S"),
            "price": round(price, 2),
            "bid": round(price - random.uniform(0.01, 0.05), 2),
            "ask": round(price + random.uniform(0.01, 0.05), 2),
            "volume": random.randint(100, 5000)
        }
        ticks_history.append(tick)
        if len(ticks_history) > 200:
            ticks_history = ticks_history[-200:]

        # Order book
        bids = [[round(price - 0.01 * i, 2), random.randint(100, 1000)] for i in range(1, 11)]
        asks = [[round(price + 0.01 * i, 2), random.randint(100, 1000)] for i in range(1, 11)]
        order_book = {"bids": bids, "asks": asks, "midPrice": price, "spread": round(asks[0][0] - bids[0][0], 2)}

        payload = json.dumps({"ticks": ticks_history[-60:], "orderBook": order_book})
        for ws in ACTIVE_CLIENTS:
            try: asyncio.run_coroutine_threadsafe(ws.send_text(payload), asyncio.get_event_loop())
            except: pass
        time.sleep(0.5)


@app.on_event("startup")
async def startup():
    threading.Thread(target=simulate_market, daemon=True).start()


@app.post("/api/backtest")
def run_backtest(config: GridConfig):
    return execute_backtest(config)


def execute_backtest(config) -> dict:
    step = (config.upperPrice - config.lowerPrice) / config.gridCount
    grid_prices = [config.lowerPrice + i * step for i in range(config.gridCount + 1)]

    # Simulate prices —— 固定随机源，保证不同参数组合跑在同一段行情上可公平对照
    np.random.seed(42)
    random.seed(42)
    prices = [100]
    for _ in range(200):
        prices.append(prices[-1] + random.gauss(0, 1.2))
    prices = [max(70, min(140, p)) for p in prices]

    buy_grids = {}  # price -> True (buy order placed)
    orders = []
    cash = config.initialCapital
    holdings = 0
    equity_curve = [cash]
    order_id = 0

    for p in prices:
        for gp in grid_prices:
            # Buy signal
            if p <= gp and gp not in buy_grids and cash >= config.capitalPerGrid:
                qty = config.capitalPerGrid / gp
                cash -= config.capitalPerGrid
                holdings += qty
                buy_grids[gp] = True
                order_id += 1
                orders.append({"id": order_id, "price": round(gp, 2), "side": "BUY", "quantity": round(qty, 2), "status": "FILLED", "profit": 0})

            # Sell signal
            upper_gp = gp + step * 0.5
            if p >= upper_gp and gp in buy_grids:
                qty = config.capitalPerGrid / gp
                buy_price = gp
                sell_price = gp + step * 0.5
                profit = qty * (sell_price - buy_price)
                cash += config.capitalPerGrid + profit
                holdings -= qty
                del buy_grids[gp]
                order_id += 1
                orders.append({"id": order_id, "price": round(sell_price, 2), "side": "SELL", "quantity": round(qty, 2), "status": "FILLED", "profit": round(profit, 2)})

        equity = cash + holdings * p
        equity_curve.append(round(equity, 2))

    total_profit = cash + holdings * prices[-1] - config.initialCapital
    return_rate = (total_profit / config.initialCapital) * 100

    # Sharpe ratio
    eq_arr = np.array(equity_curve, dtype=float)
    eq_returns = np.diff(eq_arr) / (eq_arr[:-1] + 1e-5)
    sharpe = float(np.mean(eq_returns) / max(np.std(eq_returns), 1e-5) * np.sqrt(252)) if len(eq_returns) > 1 else 0

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        if e > peak: peak = e
        dd = (peak - e) / peak * 100
        max_dd = max(max_dd, dd)

    # Win rate
    wins = sum(1 for o in orders if o["profit"] > 0)
    total = len([o for o in orders if o["side"] == "SELL"])
    win_rate = (wins / total * 100) if total > 0 else 0

    return {
        "orders": orders,
        "totalProfit": round(total_profit, 2),
        "returnRate": round(return_rate, 2),
        "sharpeRatio": round(sharpe, 2),
        "maxDrawdown": round(max_dd, 2),
        "winRate": round(win_rate, 1),
        "equityCurve": equity_curve
    }


@app.post("/api/backtest/batch")
def run_backtest_batch(req: BatchBacktestRequest):
    """批量回测：逐条校验、逐条执行。

    任意一条越界或与本批内更早的组合重复，只会在 skipped 中指出是哪一条并跳过，
    不影响其余组合的执行，整批不会失败。
    """
    results = []
    skipped = []
    seen = {}  # signature -> 首次出现条目的标识（优先用客户端 cid，否则用批内序号）

    for idx, raw in enumerate(req.configs, start=1):
        cid = raw.get("cid", idx) if isinstance(raw, dict) else idx
        if idx > BATCH_MAX:
            skipped.append({"index": idx, "cid": cid,
                            "reason": f"超过单批最大组数 {BATCH_MAX}", "config": {}})
            continue
        if not isinstance(raw, dict):
            c, parse_err = None, "该条不是有效的参数对象"
        else:
            c, parse_err = parse_batch_config(raw)
        if parse_err is not None:
            skipped.append({"index": idx, "cid": cid, "reason": parse_err,
                            "config": raw if isinstance(raw, dict) else {}})
            continue

        reason = validate_grid_config(c)
        if reason is None:
            sig = config_signature(c)
            if sig in seen:
                reason = f"与本批第 {seen[sig]} 条参数组合重复"
        if reason is not None:
            skipped.append({"index": idx, "cid": cid, "reason": reason,
                            "config": c.model_dump()})
            continue

        seen[config_signature(c)] = cid
        r = execute_backtest(c)
        results.append({
            "cid": cid,
            "params": {
                "lowerPrice": c.lowerPrice,
                "upperPrice": c.upperPrice,
                "gridCount": c.gridCount,
                "capitalPerGrid": c.capitalPerGrid,
                "initialCapital": c.initialCapital,
            },
            "returnRate": r["returnRate"],
            "maxDrawdown": r["maxDrawdown"],
            "sharpeRatio": r["sharpeRatio"],
            "tradeCount": len([o for o in r["orders"] if o["side"] == "SELL"]),
            "totalProfit": r["totalProfit"],
            "winRate": r["winRate"],
        })

    return {
        "results": results,
        "skipped": skipped,
        "total": len(req.configs),
        "executed": len(results),
        "skippedCount": len(skipped),
    }


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ACTIVE_CLIENTS.append(ws)
    try:
        while True: await ws.receive_text()
    except: 
        if ws in ACTIVE_CLIENTS: ACTIVE_CLIENTS.remove(ws)