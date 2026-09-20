export interface Tick { time: string; price: number; bid: number; ask: number; volume: number }
export interface OrderBook { bids: [number,number][]; asks: [number,number][]; midPrice: number; spread: number }
export interface GridConfig { lowerPrice: number; upperPrice: number; gridCount: number; capitalPerGrid: number; initialCapital: number }
export interface GridOrder { id: number; price: number; side: string; quantity: number; status: string; profit: number }
export interface GridResult { orders: GridOrder[]; totalProfit: number; returnRate: number; sharpeRatio: number; maxDrawdown: number; winRate: number; equityCurve: number[] }

export interface BatchParams { lowerPrice: number; upperPrice: number; gridCount: number; capitalPerGrid: number; initialCapital: number }
export interface BatchResultItem {
  id: number
  params: BatchParams
  returnRate: number
  maxDrawdown: number
  sharpeRatio: number
  tradeCount: number
  totalProfit: number
  winRate: number
  createdAt: number
}
export interface BatchSkipped { index: number; cid: number; reason: string; config: Partial<BatchParams> }
export interface BatchBacktestResponse {
  results: Array<Omit<BatchResultItem, 'id' | 'createdAt'> & { cid: number }>
  skipped: BatchSkipped[]
  total: number
  executed: number
  skippedCount: number
}
export interface BatchDraftRow { key: number; lowerPrice: number; upperPrice: number; gridCount: number; capitalPerGrid: number }
