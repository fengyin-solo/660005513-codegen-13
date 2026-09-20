export interface Tick { time: string; price: number; bid: number; ask: number; volume: number }
export interface OrderBook { bids: [number,number][]; asks: [number,number][]; midPrice: number; spread: number }
export interface GridConfig { lowerPrice: number; upperPrice: number; gridCount: number; capitalPerGrid: number; initialCapital: number }
export interface GridOrder { id: number; price: number; side: string; quantity: number; status: string; profit: number }
export interface GridResult { orders: GridOrder[]; totalProfit: number; returnRate: number; sharpeRatio: number; maxDrawdown: number; winRate: number; equityCurve: number[] }

export interface BatchMetrics {
  returnRate: number
  maxDrawdown: number
  sharpeRatio: number
  tradeCount: number
  totalProfit: number
  winRate: number
}
export interface BatchResult { index: number; config: GridConfig; metrics: BatchMetrics }
export interface BatchSkipped { index: number | null; config: GridConfig | Record<string, unknown> | null; reason: string }
export interface BatchResponse { results: BatchResult[]; skipped: BatchSkipped[] }
export type SortOrder = 'ascending' | 'descending' | null

/** 组合的唯一标识（参与批量对比的四要素） */
export function comboKey(c: Pick<GridConfig, 'lowerPrice' | 'upperPrice' | 'gridCount' | 'capitalPerGrid'>): string {
  return `${c.lowerPrice}|${c.upperPrice}|${c.gridCount}|${c.capitalPerGrid}`
}
