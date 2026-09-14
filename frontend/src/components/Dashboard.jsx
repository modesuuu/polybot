import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bot,
  BrainCircuit,
  CandlestickChart,
  CircleDollarSign,
  Clock3,
  Gauge,
  LineChart,
  Newspaper,
  RefreshCcw,
  ShieldCheck,
  Table2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { createChart, CandlestickSeries } from 'lightweight-charts';
import { TerminalAuditor } from './TerminalAuditor';

const API_BASE = 'http://localhost:8000';
const INITIAL_BALANCE = 10;
const POLL_INTERVAL_MS = 2000;
const TRADE_WINDOW_MS = 5 * 60 * 1000;

function cx(...parts) {
  return parts.filter(Boolean).join(' ');
}

function fmtUsd(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  return `${n >= 0 ? '+' : '-'}$${Math.abs(n).toFixed(digits)}`;
}

function fmtPlainUsd(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `$${Number(value).toFixed(digits)}`;
}

function fmtPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(1)}%`;
}

function safeTime(ts) {
  if (!ts) return '—';
  const d = new Date(`${ts}${String(ts).endsWith('Z') ? '' : 'Z'}`);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function Card({ className = '', children }) {
  return <section className={cx('rounded-xl border border-zinc-800/80 bg-zinc-950/80 shadow-[0_0_0_1px_rgba(255,255,255,0.02)]', className)}>{children}</section>;
}

function Button({ active, className = '', children, ...props }) {
  return (
    <button
      className={cx(
        'inline-flex min-h-10 items-center justify-center gap-2 rounded-md border px-3 text-xs font-medium tracking-wide transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/70',
        active
          ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200'
          : 'border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function StatusPill({ online, label }) {
  return (
    <span className={cx('inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium', online ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : 'border-rose-400/30 bg-rose-400/10 text-rose-200')}>
      <span className={cx('h-1.5 w-1.5 rounded-full', online ? 'bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,.75)]' : 'bg-rose-400')} />
      {label}
    </span>
  );
}

function TradingViewChart() {
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#09090b' },
        textColor: '#71717a',
      },
      grid: {
        vertLines: { color: '#18181b' },
        horzLines: { color: '#18181b' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      timeScale: {
        borderColor: '#27272a',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    chartRef.current = chart;

    fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=100')
      .then(res => res.json())
      .then(data => {
        const formattedData = data.map(d => ({
          time: d[0] / 1000,
          open: parseFloat(d[1]),
          high: parseFloat(d[2]),
          low: parseFloat(d[3]),
          close: parseFloat(d[4]),
        }));
        candlestickSeries.setData(formattedData);
      });

    const ws = new WebSocket('wss://stream.binance.com:9443/ws/btcusdt@kline_1m');
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      const k = message.k;
      candlestickSeries.update({
        time: k.t / 1000,
        open: parseFloat(k.o),
        high: parseFloat(k.h),
        low: parseFloat(k.l),
        close: parseFloat(k.c),
      });
    };

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      ws.close();
    };
  }, []);

  return (
    <Card className="p-4 bg-zinc-950 border-zinc-800 rounded-xl">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <CandlestickChart className="w-4 h-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-zinc-100">BTCUSDT Real-time</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Binance Live</span>
        </div>
      </div>
      <div ref={chartContainerRef} className="w-full h-[300px] relative overflow-hidden" />
    </Card>
  );
}

function MetricCard({ title, value, sub, icon: Icon, tone = 'neutral' }) {
  const toneMap = {
    green: 'text-emerald-300 border-emerald-400/20 bg-emerald-400/5',
    red: 'text-rose-300 border-rose-400/20 bg-rose-400/5',
    amber: 'text-amber-300 border-amber-400/20 bg-amber-400/5',
    cyan: 'text-cyan-300 border-cyan-400/20 bg-cyan-400/5',
    neutral: 'text-zinc-100 border-zinc-800 bg-zinc-900/40',
  };
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-zinc-500">{title}</p>
          <p className="mt-3 font-mono text-2xl font-semibold tracking-tight text-zinc-50 tabular-nums">{value}</p>
        </div>
        <div className={cx('rounded-lg border p-2', toneMap[tone])}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      {sub && <p className="mt-3 text-xs text-zinc-500">{sub}</p>}
    </Card>
  );
}

function Countdown({ createdAt }) {
  const [left, setLeft] = useState(0);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
    if (!createdAt) return;
    const entry = new Date(`${createdAt}${String(createdAt).endsWith('Z') ? '' : 'Z'}`).getTime();
    const target = entry + TRADE_WINDOW_MS;
    const tick = () => setLeft(Math.max(0, target - Date.now()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [createdAt]);
  const mm = Math.floor(left / 60000).toString().padStart(2, '0');
  const ss = Math.floor((left % 60000) / 1000).toString().padStart(2, '0');
  return <span className="font-mono text-sm text-amber-200 tabular-nums" suppressHydrationWarning>{mounted && left > 0 ? `${mm}:${ss}` : mounted ? 'closing' : ''}</span>;
}

function ActivePosition({ trade }) {
  if (!trade) {
    return (
      <Card className="flex min-h-[320px] flex-col justify-between p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Active position</p>
            <h2 className="mt-2 text-xl font-semibold text-zinc-100">No open trade</h2>
          </div>
          <StatusPill online={false} label="SKIP / IDLE" />
        </div>
        <div className="rounded-lg border border-dashed border-zinc-800 p-6 text-sm text-zinc-500">
          Bot standby. Entry muncul saat signal gate lolos, OBI fresh, dan news blackout tidak aktif.
        </div>
      </Card>
    );
  }

  const isUp = trade.direction === 'UP';
  const current = trade.current_token_price ?? trade.up_price;
  const entryShare = trade.entry_price_share;
  return (
    <Card className="min-h-[320px] overflow-hidden">
      <div className="border-b border-zinc-800 p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Active position</p>
            <div className="mt-2 flex items-center gap-3">
              <span className={cx('inline-flex h-9 w-9 items-center justify-center rounded-lg border', isUp ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-rose-400/30 bg-rose-400/10 text-rose-300')}>
                {isUp ? <ArrowUp className="h-5 w-5" /> : <ArrowDown className="h-5 w-5" />}
              </span>
              <div>
                <h2 className="text-xl font-semibold text-zinc-50">BTC {trade.direction} / 5m</h2>
                <p className="text-xs text-zinc-500" suppressHydrationWarning>Trade #{trade.id} · {safeTime(trade.timestamp)}</p>
              </div>
            </div>
          </div>
          <Countdown createdAt={trade.timestamp} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-px bg-zinc-800">
        {[
          ['BTC Entry', fmtPlainUsd(trade.btc_entry_price ?? trade.entry_price, 2)],
          ['Position Size', fmtPlainUsd(trade.position_size ?? trade.quantity, 2)],
          ['Entry Share', entryShare != null ? `${Math.round(entryShare * 100)}¢` : '—'],
          ['Live Bid', current != null ? `${Math.round(current * 100)}¢` : '—'],
          ['Potential Win', fmtUsd(trade.potential_win, 2)],
          ['Unrealized', fmtUsd(trade.unrealized_pnl, 2)],
        ].map(([label, value]) => (
          <div key={label} className="bg-zinc-950 p-4">
            <p className="text-[11px] uppercase tracking-[0.16em] text-zinc-600">{label}</p>
            <p className="mt-1 font-mono text-lg text-zinc-100 tabular-nums">{value}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function BalanceChart({ rows }) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Equity curve</p>
          <h2 className="mt-1 text-lg font-semibold text-zinc-100">$10 session balance</h2>
        </div>
        <LineChart className="h-5 w-5 text-zinc-500" />
      </div>
      <div className="h-72">
        {rows.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={rows} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="equityFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#34d399" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ background: '#09090b', border: '1px solid #27272a', borderRadius: 10, color: '#e4e4e7' }}
                formatter={(v) => [fmtPlainUsd(v, 2), 'Balance']}
              />
              <Area type="monotone" dataKey="balance" stroke="#34d399" strokeWidth={2} fill="url(#equityFill)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-zinc-800 text-sm text-zinc-500">Waiting for closed trades</div>
        )}
      </div>
    </Card>
  );
}

function SignalTape({ activeTrade, history }) {
  const source = activeTrade || history[0];
  const [feed, setFeed] = useState({ obi: 0, cvd: 0, fresh: false, source: 'CLIENT WS' });

  useEffect(() => {
    let closed = false;
    let cvd = 0;

    const depthWs = new WebSocket('wss://data-stream.binance.vision/ws/btcusdt@depth10@100ms');
    depthWs.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const bids = msg.bids || msg.b || [];
        const asks = msg.asks || msg.a || [];
        const bidVol = bids.reduce((sum, row) => sum + Number(row[1] || 0), 0);
        const askVol = asks.reduce((sum, row) => sum + Number(row[1] || 0), 0);
        const total = bidVol + askVol;
        const obi = total > 0 ? bidVol / total : 0;
        if (!closed) setFeed(prev => ({ ...prev, obi, fresh: true }));
      } catch {}
    };

    const tradeWs = new WebSocket('wss://data-stream.binance.vision/ws/btcusdt@aggTrade');
    tradeWs.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const qty = Number(msg.q || 0);
        cvd += msg.m ? -qty : qty;
        if (!closed) setFeed(prev => ({ ...prev, cvd }));
      } catch {}
    };

    const markStale = setInterval(() => {
      if (!closed) setFeed(prev => ({ ...prev, fresh: depthWs.readyState === WebSocket.OPEN }));
    }, 5000);

    return () => {
      closed = true;
      clearInterval(markStale);
      depthWs.close();
      tradeWs.close();
    };
  }, []);

  const apiObi = source?.obi ?? source?.orderbook_imbalance_ratio ?? source?.orderbook_imbalance ?? source?.imbalance;
  const apiCvd = source?.cvd_momentum ?? source?.net_delta ?? source?.cvd;
  const obi = Number(apiObi ?? feed.obi ?? 0);
  const cvd = Number(apiCvd ?? feed.cvd ?? 0);
  const fresh = feed.fresh || source?.obi_fresh === true || source?.obi_stale === false || source?.fresh === true;

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Microstructure</p>
          <h2 className="mt-1 text-lg font-semibold text-zinc-100">OBI / CVD feed</h2>
        </div>
        <StatusPill online={fresh} label={fresh ? 'CLIENT WS LIVE' : 'WAITING WS'} />
      </div>
      <div className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <p className="text-xs text-zinc-500">OBI</p>
          <p className="mt-2 font-mono text-2xl text-zinc-100 tabular-nums">{obi.toFixed(3)}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <p className="text-xs text-zinc-500">CVD / Delta</p>
          <p className="mt-2 font-mono text-2xl text-zinc-100 tabular-nums">{cvd.toFixed(2)}</p>
        </div>
      </div>
      <div className="mt-4 rounded-lg border border-zinc-800 bg-black/30 p-3 font-mono text-xs text-zinc-500" suppressHydrationWarning>
        {source ? `last signal #${source.id} · ${source.direction ?? '—'} · ${source.status ?? '—'} · ${feed.source}` : `${feed.source} · no backend signal payload`}
      </div>
    </Card>
  );
}

function NewsWidget({ audit }) {
  const reasoning = audit?.[0]?.ai_reasoning;
  const [upcoming, setUpcoming] = useState([]);
  const [blackout, setBlackout] = useState({ active: false, next_event: null, next_minutes: null });

  useEffect(() => {
    let closed = false;
    const load = async () => {
      try {
        const [uRes, bRes] = await Promise.all([
          fetch(`${API_BASE}/api/news/upcoming`),
          fetch(`${API_BASE}/api/news/blackout`),
        ]);
        if (!uRes.ok || !bRes.ok) return;
        const u = await uRes.json();
        const b = await bRes.json();
        if (!closed) {
          setUpcoming(Array.isArray(u.upcoming) ? u.upcoming : []);
          setBlackout(b);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 30000);
    return () => { closed = true; clearInterval(id); };
  }, []);

  const fmtEvent = (ev) => {
    if (!ev || !ev.start_ts) return '—';
    const d = new Date(ev.start_ts * 1000);
    const mins = ev.minutes != null ? ` · ${ev.minutes}m` : '';
    return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}${mins}`;
  };

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Economic News Filter</p>
          <h2 className="mt-1 text-lg font-semibold text-zinc-100">USD High Impact guard</h2>
        </div>
        <StatusPill online={!blackout.active} label={blackout.active ? 'BLACKOUT ACTIVE' : 'NO BLACKOUT'} />
      </div>
      <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-500">
        <span className="text-zinc-400">Auto-sync:</span> {blackout.next_event ? `${blackout.next_event} (${blackout.next_minutes}m)` : 'no upcoming'}
      </div>
      <div className="mt-2 space-y-2">
        {upcoming.length === 0 ? (
          <div className="rounded-lg border border-dashed border-zinc-800 p-3 text-xs text-zinc-600">No upcoming USD High events scheduled.</div>
        ) : (
          upcoming.slice(0, 4).map((ev, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-xs">
              <span className="text-zinc-300">{ev.event_name}</span>
              <span className="font-mono text-zinc-500">{fmtEvent(ev)}</span>
            </div>
          ))
        )}
      </div>
      <div className="mt-4 rounded-lg border border-zinc-800 bg-black/30 p-3 text-xs text-zinc-500">
        Latest AI audit: {reasoning ? reasoning.slice(0, 110) : 'no audit log yet'}
      </div>
    </Card>
  );
}

function HistoryTable({ rows }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-zinc-800 p-5">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Trade ledger</p>
          <h2 className="mt-1 text-lg font-semibold text-zinc-100">Recent history</h2>
        </div>
        <Table2 className="h-5 w-5 text-zinc-500" />
      </div>
      <div className="max-h-[420px] overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-zinc-950 text-[11px] uppercase tracking-[0.16em] text-zinc-500">
            <tr className="border-b border-zinc-800">
              <th className="px-5 py-3 font-medium">ID</th>
              <th className="px-5 py-3 font-medium">Time</th>
              <th className="px-5 py-3 font-medium">Side</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 text-right font-medium">PnL</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((t) => (
              <tr key={t.id} className="border-b border-zinc-900 text-zinc-300 hover:bg-zinc-900/50">
                <td className="px-5 py-3 font-mono text-zinc-500">#{t.id}</td>
                <td className="px-5 py-3 font-mono text-xs text-zinc-500" suppressHydrationWarning>{safeTime(t.timestamp)}</td>
                <td className="px-5 py-3"><span className={cx('inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs', t.direction === 'UP' ? 'border-emerald-400/20 text-emerald-300' : 'border-rose-400/20 text-rose-300')}>{t.direction === 'UP' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}{t.direction}</span></td>
                <td className="px-5 py-3"><span className={cx('rounded-md px-2 py-1 text-xs', t.status === 'WIN' ? 'bg-emerald-400/10 text-emerald-300' : t.status === 'LOSS' ? 'bg-rose-400/10 text-rose-300' : 'bg-amber-400/10 text-amber-300')}>{t.status}</span></td>
                <td className={cx('px-5 py-3 text-right font-mono tabular-nums', Number(t.pnl ?? t.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-300' : 'text-rose-300')}>{t.status === 'OPEN' ? fmtUsd(t.unrealized_pnl) : fmtUsd(t.pnl)}</td>
              </tr>
            )) : (
              <tr><td colSpan="5" className="px-5 py-10 text-center text-zinc-500">No trades yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function Dashboard() {
  const [tab, setTab] = useState('trading');
  const [sessionSince, setSessionSince] = useState(null);
  const [metrics, setMetrics] = useState({ total_pnl: 0, balance: INITIAL_BALANCE, unrealized_pnl: 0, win_rate: 0, total_trades: 0, open_trades: 0 });
  const [history, setHistory] = useState([]);
  const [activeTrade, setActiveTrade] = useState(null);
  const [mlStats, setMlStats] = useState({ total_records: 0, with_target: 0, win_count: 0, loss_count: 0 });
  const [auditHistory, setAuditHistory] = useState([]);
  const [apiState, setApiState] = useState({ ok: false, last: null, error: null });
  const [wsProbe, setWsProbe] = useState('checking');
  const [mounted, setMounted] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    setMounted(true);
    try { setSessionSince(localStorage.getItem('polybot_session_since') || null); } catch {}
  }, []);

  const resetSession = () => {
    const now = new Date().toISOString();
    try { localStorage.setItem('polybot_session_since', now); } catch {}
    setSessionSince(now);
  };

  const fetchJson = async (path) => {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
    return res.json();
  };

  const fetchData = useCallback(async () => {
    try {
      const suffix = sessionSince ? `?since=${encodeURIComponent(sessionSince)}` : '';
      const [m, h, a, ml, audits] = await Promise.all([
        fetchJson(`/metrics${suffix}`),
        fetchJson(`/api/signals${suffix}`),
        fetchJson('/api/active-trade').catch(() => null),
        fetchJson('/api/ml/dataset-count').catch(() => ({ total_records: 0, with_target: 0, win_count: 0, loss_count: 0 })),
        fetchJson('/api/ml/audit-history').catch(() => []),
      ]);
      setMetrics(m);
      setHistory(Array.isArray(h) ? h : []);
      setActiveTrade(a);
      setMlStats(ml);
      setAuditHistory(Array.isArray(audits) ? audits : []);
      setApiState({ ok: true, last: new Date().toLocaleTimeString(), error: null });
    } catch (error) {
      setApiState({ ok: false, last: new Date().toLocaleTimeString(), error: error.message });
    }
  }, [sessionSince]);

  useEffect(() => {
    fetchData();
    pollRef.current = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => clearInterval(pollRef.current);
  }, [fetchData]);

  useEffect(() => {
    let closed = false;
    const ws = new WebSocket('wss://data-stream.binance.vision/ws/btcusdt@aggTrade');
    const timeout = setTimeout(() => !closed && setWsProbe('slow'), 4000);
    ws.onopen = () => { if (!closed) setWsProbe('connected'); };
    ws.onerror = () => { if (!closed) setWsProbe('error'); };
    ws.onclose = () => { if (!closed && wsProbe !== 'connected') setWsProbe('closed'); };
    return () => { closed = true; clearTimeout(timeout); ws.close(); };
  }, []);

  const closedTrades = useMemo(() => history.filter((t) => t.status !== 'OPEN'), [history]);
  const balanceRows = useMemo(() => {
    let balance = INITIAL_BALANCE;
    return [...closedTrades].reverse().map((t) => {
      balance += Number(t.pnl || 0);
      return { name: `#${t.id}`, balance: Math.round(balance * 100) / 100 };
    });
  }, [closedTrades]);
  
  if (!mounted) return null;

  if (tab === 'terminal') {
    return (
      <main className="min-h-screen bg-zinc-950 p-4 text-zinc-100 md:p-6">
        <div className="mx-auto max-w-7xl space-y-4">
          <Button onClick={() => setTab('trading')}><ArrowDown className="h-4 w-4" /> Back to Command Center</Button>
          <TerminalAuditor />
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto max-w-[1600px] space-y-5 p-4 md:p-6">
        <header className="grid gap-4 rounded-xl border border-zinc-800 bg-zinc-950/90 p-4 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill online={apiState.ok} label={apiState.ok ? (activeTrade ? 'LIVE POSITION' : 'LIVE / WAITING') : 'API OFFLINE'} />
              <StatusPill online={wsProbe === 'connected'} label={wsProbe === 'connected' ? 'BINANCE WS OK' : `WS ${wsProbe.toUpperCase()}`} />
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-50 md:text-5xl">Polybot Command Center</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">Monitor surface. Dense, dark, API-bound.</p>
          </div>
          <div className="flex flex-wrap gap-2 md:justify-end">
            <Button active={tab === 'trading'} onClick={() => setTab('trading')}><Activity className="h-4 w-4" /> Trading</Button>
            <Button onClick={() => setTab('terminal')}><BrainCircuit className="h-4 w-4" /> AI Terminal</Button>
            <Button onClick={fetchData}><RefreshCcw className="h-4 w-4" /> Refresh</Button>
            <Button className="border-amber-400/30 text-amber-200 hover:border-amber-300" onClick={resetSession}><Clock3 className="h-4 w-4" /> New Session</Button>
          </div>
        </header>

        {apiState.error && (
          <div className="rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-200">API error: {apiState.error}</div>
        )}

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <MetricCard title="Realized PnL" value={fmtUsd(metrics.total_pnl)} sub={`Balance ${fmtPlainUsd(metrics.balance ?? INITIAL_BALANCE)}`} icon={CircleDollarSign} tone={Number(metrics.total_pnl) >= 0 ? 'green' : 'red'} />
          <MetricCard title="Unrealized" value={fmtUsd(metrics.unrealized_pnl)} sub={`${metrics.open_trades ?? 0} open trade`} icon={Gauge} tone={Number(metrics.unrealized_pnl) >= 0 ? 'green' : 'red'} />
          <MetricCard title="Win Rate" value={fmtPct(metrics.win_rate)} sub={`${metrics.total_trades ?? 0} closed trades`} icon={ShieldCheck} tone="cyan" />
          <MetricCard title="ML Dataset" value={mlStats.total_records ?? 0} sub={`${mlStats.with_target ?? 0} labeled`} icon={Bot} tone="neutral" />
          <MetricCard title="API Heartbeat" value={apiState.last ?? '—'} sub="polling every 2s" icon={apiState.ok ? Wifi : WifiOff} tone={apiState.ok ? 'green' : 'red'} />
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.35fr_.9fr_.75fr]">
          <div className="flex flex-col gap-5">
            <BalanceChart rows={balanceRows} />
            <TradingViewChart />
          </div>
          <ActivePosition trade={activeTrade} />
          <div className="space-y-5">
            <SignalTape activeTrade={activeTrade} history={history} />
            <NewsWidget audit={auditHistory} />
          </div>
        </section>

        <HistoryTable rows={history.slice(0, 30)} />

        <footer className="flex flex-wrap items-center justify-between gap-3 pb-3 text-xs text-zinc-600">
          <span>Polybot UI v3 · shadcn-style dark command dashboard</span>
          <span suppressHydrationWarning>Session filter: {sessionSince ? new Date(sessionSince).toLocaleString() : 'full history'}</span>
        </footer>
      </div>
    </main>
  );
}
