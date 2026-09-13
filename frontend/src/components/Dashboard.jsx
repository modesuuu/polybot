import React, { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import gsap from 'gsap';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

// ============================================
// POLYBOT DASHBOARD v2.1
// Theme: Neumorphic Clean + Authentic Polymarket
// 100% Dynamic Live Data Binding
// ============================================

const COLORS = {
  bg: '#ECECEA',
  bgWarm: '#F2F1ED',
  card: '#FFFFFF',
  sage: '#2F4F4F',
  sageLight: '#3A5A40',
  green: '#2E7D32',
  greenLight: '#E8F5E9',
  red: '#C62828',
  redLight: '#FFEBEE',
  orange: '#F7931A',
  gray: '#6B7280',
  grayLight: '#9CA3AF',
  border: 'rgba(0,0,0,0.05)',
};

const INITIAL_BALANCE = 10;
const POLL_INTERVAL_MS = 2000; // 2 detik
const COUNTDOWN_INTERVAL_MS = 1000; // 1 detik
const TRADE_WINDOW_MS = 5 * 60 * 1000; // 5 menit

// --- Icons (inline SVG, zero-dependency) ---
const BitcoinIcon = ({ className = 'w-6 h-6' }) => (
  <svg className={className} viewBox="0 0 32 32" fill="none">
    <circle cx="16" cy="16" r="15" fill={COLORS.orange} />
    <path d="M21.7 14.4c.3-2-1.2-3.1-3.3-3.8l.7-2.7-1.6-.4-.6 2.6c-.4-.1-.9-.2-1.3-.3l.7-2.6-1.6-.4-.7 2.7c-.3-.1-.7-.2-1-.3l-2.2-.5-.5 1.8s1.2.3 1.2.3c.7.2.8.6.8 1l-.8 3.2c0 .1.1.1.1.1s-.1 0-.1-.1l-1.1 4.5c-.1.3-.3.7-.9.5 0 0-1.2-.3-1.2-.3l-.9 2 2.1.5c.4.1.8.2 1.1.3l-.7 2.8 1.6.4.7-2.7c.4.1.9.2 1.3.3l-.7 2.7 1.6.4.7-2.8c2.8.5 5-.3 5.9-2.4.7-1.7 0-2.7-1.2-3.4 1-.2 1.7-.9 1.9-2.2zm-3.4 4.8c-.5 2-4 .9-5.1.7l.9-3.7c1.1.3 4.7.9 4.2 3zm.5-4.9c-.5 1.8-3.4.9-4.3.7l.8-3.3c.9.2 3.9.7 3.5 2.6z" fill="white"/>
  </svg>
);

const ArrowUpIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 19V5M5 12l7-7 7 7"/>
  </svg>
);

const ArrowDownIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 5v14M5 12l7 7 7-7"/>
  </svg>
);

const LiveDot = () => (
  <span className="relative flex h-2.5 w-2.5">
    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
  </span>
);

import { TerminalAuditor } from './TerminalAuditor';

// --- Utility Components ---

/**
 * CountdownTimer - Timer countdown lokal per 1 detik
 * Menghitung sisa waktu 5 menit dari trade.timestamp (created_at dari backend)
 * Format tampilan: MM:SS
 */
const CountdownTimer = ({ createdAt }) => {
  const [timeLeft, setTimeLeft] = useState(0);

  useEffect(() => {
    // Parse timestamp dari backend (ISO format string)
    const entryTime = new Date(createdAt + 'Z').getTime();
    const targetTime = entryTime + TRADE_WINDOW_MS;

    const calculateDiff = () => Math.max(0, targetTime - Date.now());
    setTimeLeft(calculateDiff());

    // Timer lokal per 1 detik
    const interval = setInterval(() => {
      setTimeLeft(calculateDiff());
    }, COUNTDOWN_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [createdAt]);

  if (timeLeft <= 0) {
    return <span className="text-xs font-semibold text-amber-600">Closing...</span>;
  }

  const minutes = Math.floor((timeLeft / 1000 / 60) % 60);
  const seconds = Math.floor((timeLeft / 1000) % 60);

  return (
    <span className="font-mono text-sm font-bold text-amber-700 tabular-nums">
      {minutes.toString().padStart(2, '0')}:{seconds.toString().padStart(2, '0')}
    </span>
  );
};

const StatusBadge = ({ status, pnl }) => {
  const configs = {
    OPEN:  { bg: 'bg-amber-50',  text: 'text-amber-700',  border: 'border-amber-200',  label: 'OPEN' },
    WIN:   { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', label: 'WIN' },
    LOSS:  { bg: 'bg-rose-50',    text: 'text-rose-700',    border: 'border-rose-200',    label: 'LOSS' },
  };
  const c = configs[status] || configs.OPEN;
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-bold tracking-wide border ${c.bg} ${c.text} ${c.border}`}>
      {status === 'OPEN' ? <><LiveDot /> <span className="ml-1.5">{c.label}</span></>
        : <><span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${pnl >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}`}></span>{c.label}</>}
    </span>
  );
};

const StatCard = ({ title, value, prefix = '', suffix = '', icon, delay = 0 }) => {
  const cardRef = useRef(null);
  useEffect(() => {
    if (cardRef.current) {
      gsap.fromTo(cardRef.current,
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.5, delay: delay * 0.08, ease: 'power2.out' }
      );
    }
  }, [delay]);

  return (
    <div ref={cardRef} className="bg-white rounded-3xl p-5 border border-black/[0.04] shadow-[0_2px_12px_-2px_rgba(0,0,0,0.04)] hover:shadow-[0_8px_24px_-4px_rgba(0,0,0,0.08)] transition-all duration-300">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-widest">{title}</p>
        {icon && <span className="text-gray-300">{icon}</span>}
      </div>
      <span className="text-2xl font-bold tracking-tight" style={{ color: COLORS.sage }}>
        {prefix}{value}{suffix}
      </span>
    </div>
  );
};

// --- Polymarket-Style Active Trade Card ---
// SEMUA nilai 100% dinamis dari payload API, no hardcoded/mock
const PolymarketActiveCard = ({ trade }) => {
  const isUp = trade.direction === 'UP';

  // === DYNAMIC DATA BINDING (no hardcoded values) ===

  // Price To Beat: BTC entry price dari backend (field: btc_entry_price atau entry_price)
  const btcEntryPrice = trade.btc_entry_price != null ? trade.btc_entry_price : trade.entry_price;

  // Entry share price (harga token Polymarket saat entry, best_ask)
  const entrySharePrice = trade.entry_price_share != null ? trade.entry_price_share : null;

  // Current token price (live best_bid dari MTM worker, updated setiap 3s)
  // Prioritas: up_price (sudah dihitung dari best_bid di backend) > current_token_price > entry_price_share
  const currentTokenPrice = trade.up_price != null
    ? trade.up_price
    : (trade.current_token_price != null ? trade.current_token_price : null);

  // Up price & Down price: langsung dari API response (sudah dihitung di backend)
  const upPrice = trade.up_price != null
    ? trade.up_price
    : currentTokenPrice;
  const downPrice = trade.down_price != null
    ? trade.down_price
    : (upPrice != null ? (1 - upPrice) : null);

  // Position size (modal yang dimasukkan, e.g. $5) - prioritas: position_size dari API
  const positionSize = trade.position_size != null ? trade.position_size : trade.quantity;

  // Shares bought (dari backend: quantity / entry_price_share)
  const sharesBought = trade.shares_bought != null ? trade.shares_bought :
    (positionSize != null && entrySharePrice != null && entrySharePrice > 0
      ? positionSize / entrySharePrice : null);

  // Potential Win: dari API response (dihitung di backend: shares * 1.0 - position)
  const potentialWin = trade.potential_win != null
    ? trade.potential_win
    : ((positionSize != null && sharesBought != null) ? (sharesBought * 1.00) - positionSize : null);

  // Unrealized PnL Live: langsung dari API response (sudah dihitung di backend)
  // Backend: (current_best_bid - entry_price) * shares
  const unrealizedPnL = trade.unrealized_pnl != null ? trade.unrealized_pnl : null;

  const isPositivePnL = unrealizedPnL != null && unrealizedPnL >= 0;

  // Format helpers
  const formatCents = (price) => price != null ? `${Math.round(price * 100)}¢` : 'N/A';
  const formatUSD = (val) => val != null ? `$${val.toFixed(2)}` : 'N/A';
  const formatBTC = (val) => val != null ? `$${val.toFixed(2)}` : 'N/A';

  return (
    <div className="bg-white rounded-3xl border border-black/[0.04] shadow-[0_4px_20px_-4px_rgba(0,0,0,0.06)] overflow-hidden">
      {/* Header: Bitcoin icon + Title + Countdown Timer */}
      <div className="px-5 pt-5 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BitcoinIcon className="w-8 h-8" />
            <div>
              <h3 className="text-sm font-bold" style={{ color: COLORS.sage }}>BTC Up or Down 5m</h3>
              <p className="text-[11px] text-gray-400">Bitcoin 5-Minute Options</p>
            </div>
          </div>
          <div className="text-right">
            <div className="flex items-center gap-1.5 text-[11px] text-gray-400">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
              <CountdownTimer createdAt={trade.timestamp} />
            </div>
            <p className="text-[10px] text-gray-400 mt-0.5">Mins Left</p>
          </div>
        </div>
      </div>

      {/* Price To Beat: Harga BTC acuan saat entry */}
      <div className="px-5 py-3 bg-gray-50/60 border-y border-gray-100">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-gray-400 uppercase tracking-wider">Price To Beat</span>
          <span className="text-lg font-bold font-mono" style={{ color: COLORS.sage }}>
            {formatBTC(btcEntryPrice)}
          </span>
        </div>
      </div>

      {/* Option Buttons: Up & Down dengan harga dinamis */}
      <div className="px-5 py-4">
        <div className="grid grid-cols-2 gap-3">
          {/* UP Button */}
          <div className={`relative rounded-2xl p-3 border-2 transition-all ${isUp ? 'border-emerald-400 bg-emerald-50/50' : 'border-gray-100 bg-gray-50/50'}`}>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center">
                <ArrowUpIcon className="w-3 h-3 text-emerald-600" />
              </div>
              <span className="text-xs font-bold text-emerald-700">Up</span>
            </div>
            <span className="text-lg font-bold text-emerald-600">{formatCents(upPrice)}</span>
            {isUp && (
              <div className="absolute -top-1.5 -right-1.5">
                <span className="flex h-4 w-4">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-4 w-4 bg-emerald-500 items-center justify-center">
                    <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
                  </span>
                </span>
              </div>
            )}
          </div>

          {/* DOWN Button */}
          <div className={`relative rounded-2xl p-3 border-2 transition-all ${!isUp ? 'border-rose-400 bg-rose-50/50' : 'border-gray-100 bg-gray-50/50'}`}>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-6 h-6 rounded-full bg-rose-100 flex items-center justify-center">
                <ArrowDownIcon className="w-3 h-3 text-rose-600" />
              </div>
              <span className="text-xs font-bold text-rose-700">Down</span>
            </div>
            <span className="text-lg font-bold text-rose-600">{formatCents(downPrice)}</span>
            {!isUp && (
              <div className="absolute -top-1.5 -right-1.5">
                <span className="flex h-4 w-4">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-4 w-4 bg-rose-500 items-center justify-center">
                    <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
                  </span>
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Transaction Size Badge: Position $X | Win $Y (dinamis) */}
        <div className="mt-4 flex items-center justify-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gray-100 border border-gray-200">
            <span className="text-[11px] font-medium text-gray-500">Position</span>
            <span className="text-sm font-bold" style={{ color: COLORS.sage }}>{formatUSD(positionSize)}</span>
            <span className="text-[10px] text-gray-400">|</span>
            <span className="text-[11px] font-medium text-gray-500">Win</span>
            <span className="text-sm font-bold text-emerald-600">{formatUSD(potentialWin)}</span>
          </div>
        </div>

        {/* Unrealized PnL Live: dari API response, dihitung di backend */}
        {unrealizedPnL != null && (
          <div className="mt-3 text-center">
            <span className={`text-xs font-bold ${isPositivePnL ? 'text-emerald-600' : 'text-rose-600'}`}>
              {isPositivePnL ? '+' : ''}{formatUSD(unrealizedPnL)} unrealized
            </span>
            <p className="text-[10px] text-gray-400 mt-0.5">
              ({formatCents(currentTokenPrice)} bid - {formatCents(entrySharePrice)} entry) × {sharesBought != null ? sharesBought.toFixed(2) : 'N/A'} shares
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

// --- Empty State: No Active Trade ---
const EmptyTradeCard = () => (
  <div className="bg-white rounded-3xl p-6 border border-black/[0.04] shadow-[0_2px_12px_-2px_rgba(0,0,0,0.04)]">
    <div className="flex items-center gap-3 mb-4">
      <BitcoinIcon className="w-8 h-8 opacity-30" />
      <div>
        <h3 className="text-sm font-bold text-gray-300">BTC Up or Down 5m</h3>
        <p className="text-[11px] text-gray-300">Bitcoin 5-Minute Options</p>
      </div>
    </div>
    <div className="text-center py-12">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gray-100 mb-3">
        <span className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-300 opacity-60"></span>
          <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-400"></span>
        </span>
      </div>
      <p className="text-sm font-medium text-gray-500 animate-pulse">Waiting for Next Signal Window...</p>
      <p className="text-xs text-gray-400 mt-1">System will auto-open position at next 5-min cycle</p>
    </div>
  </div>
);

// --- Semi-Circle Gauge ---
const SemiCircleGauge = ({ value, label, sublabel, color = COLORS.sage }) => {
  const percentage = Math.min(Math.max(value, 0), 100);
  const radius = 45;
  const strokeWidth = 8;
  const normalizedRadius = radius - strokeWidth / 2;
  const circumference = normalizedRadius * Math.PI;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center">
      <div className="relative w-32 h-16">
        <svg height="64" width="128" viewBox="0 0 100 50">
          <circle stroke="#E5E7EB" fill="transparent" strokeWidth={strokeWidth} strokeLinecap="round"
            r={normalizedRadius} cx="50" cy="50" strokeDasharray={`${circumference} ${circumference}`} transform="rotate(180 50 50)" />
          <circle stroke={color} fill="transparent" strokeWidth={strokeWidth} strokeLinecap="round"
            r={normalizedRadius} cx="50" cy="50" strokeDasharray={`${circumference} ${circumference}`}
            strokeDashoffset={strokeDashoffset} transform="rotate(180 50 50)"
            style={{ transition: 'stroke-dashoffset 0.5s ease-in-out' }} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
          <span className="text-2xl font-bold" style={{ color: COLORS.sage }}>{percentage.toFixed(0)}%</span>
        </div>
      </div>
      <p className="text-xs font-medium text-gray-500 mt-2">{label}</p>
      {sublabel && <p className="text-[10px] text-gray-400">{sublabel}</p>}
    </div>
  );
};

// --- Main Dashboard ---
export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('trading');

  // sessionSince: persist across refresh via localStorage
  const [sessionSince, setSessionSince] = useState(() => {
    try { return localStorage.getItem('polybot_session_since') || null; }
    catch { return null; }
  });

  const handleNewSession = () => {
    const now = new Date().toISOString();
    try { localStorage.setItem('polybot_session_since', now); } catch {}
    setSessionSince(now);
  };
  const [metrics, setMetrics] = useState({
    total_pnl: 0, unrealized_pnl: 0, win_rate: 0, total_trades: 0, open_trades: 0
  });
  const [mlStats, setMlStats] = useState({ total_records: 0, with_target: 0, win_count: 0, loss_count: 0 });
  const [history, setHistory] = useState([]);
  const [wsStatus, setWsStatus] = useState('connected');
  const containerRef = useRef(null);

  // Stable fetch function with anti-flicker JSON comparison
  const fetchData = useCallback(async () => {
    try {
      const s = sessionSince;
      const suffix = s ? `?since=${encodeURIComponent(s)}` : '';
      const [metricsRes, historyRes, mlRes] = await Promise.all([
        fetch(`http://localhost:8000/metrics${suffix}`),
        fetch(`http://localhost:8000/api/signals${suffix}`),
        fetch('http://localhost:8000/api/ml/dataset-count').catch(() =>
          new Response(JSON.stringify({ total_records: 0, with_target: 0, win_count: 0, loss_count: 0 }))
        )
      ]);

      if (!metricsRes.ok || !historyRes.ok) throw new Error('API error');

      const [metricsData, historyData, mlData] = await Promise.all([
        metricsRes.json(), historyRes.json(), mlRes.json()
      ]);

      // Anti-flicker: only update if data actually changed
      setMetrics(prev => {
        if (JSON.stringify(prev) === JSON.stringify(metricsData)) return prev;
        return metricsData;
      });
      setHistory(prev => {
        if (JSON.stringify(prev) === JSON.stringify(historyData)) return prev;
        return historyData;
      });
      setMlStats(prev => {
        if (JSON.stringify(prev) === JSON.stringify(mlData)) return prev;
        return mlData;
      });
      setWsStatus('connected');
    } catch (error) {
      console.error('Failed to fetch data:', error);
      setWsStatus('disconnected');
    }
  }, [sessionSince]); // dependency added so it updates when sessionSince changes

  // Polling API setiap 2 detik
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  // GSAP entrance animation
  useEffect(() => {
    if (containerRef.current) {
      const elements = containerRef.current.querySelectorAll('.animate-me');
      gsap.fromTo(elements,
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.5, stagger: 0.06, ease: 'power2.out', delay: 0.15 }
      );
    }
  }, []);

  // Balance History: $10 initial + cumulative PnL
  const balanceHistory = useMemo(() => {
    const closed = [...history].filter(t => t.status !== 'OPEN' && t.pnl != null).reverse();
    let balance = INITIAL_BALANCE;
    return closed.map((t, i) => {
      balance += t.pnl;
      return {
        name: `#${t.id}`,
        balance: Math.round(balance * 100) / 100,
        pnl: t.pnl,
        index: i,
      };
    });
  }, [history]);

  // ML confidence calculation
  const mlConfidence = useMemo(() => {
    if (mlStats.total_records === 0) return 0;
    const ratio = mlStats.with_target / mlStats.total_records;
    return Math.min(ratio * 100 + 20, 95);
  }, [mlStats]);

  // Active trade: ambil yang paling baru berstatus OPEN
  const activeSignal = useMemo(() => {
    const openTrades = history.filter(t => t.status === 'OPEN');
    return openTrades.length > 0 ? openTrades[0] : null;
  }, [history]);

  // Closed trades for history display
  const closedTrades = useMemo(() => history.filter(t => t.status !== 'OPEN').slice(0, 10), [history]);

  return (
    <div ref={containerRef} className="min-h-screen p-4 md:p-6 lg:p-8 font-sans" style={{ backgroundColor: COLORS.bg }}>
      <div className="max-w-7xl mx-auto space-y-6">

        {/* HEADER */}
        <header className="animate-me flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight" style={{ color: COLORS.sage }}>
              Hello, Raka!
            </h1>
            <p className="text-sm text-gray-500 mt-1">Polybot Quant Engine</p>
          </div>
          <div className="flex items-center gap-3">
            {/* Tab Switcher */}
            <div className="flex bg-gray-200/80 p-1 rounded-full">
              <button
                onClick={() => setActiveTab('trading')}
                className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${activeTab === 'trading' ? 'bg-white shadow-sm text-gray-800' : 'text-gray-500 hover:text-gray-800'}`}>
                Trading Bot
              </button>
              <button
                onClick={() => setActiveTab('terminal')}
                className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all ${activeTab === 'terminal' ? 'bg-black text-green-400 shadow-sm' : 'text-gray-500 hover:text-gray-800'}`}>
                AI Terminal
              </button>
            </div>
            {/* NEW SESSION Button */}
            <button
              onClick={handleNewSession}
              className="px-3 py-1.5 rounded-full text-xs font-bold bg-amber-500 text-white shadow-sm hover:bg-amber-600 transition-all">
              NEW SESSION
            </button>
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border ${wsStatus === 'connected' ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700'}`}>
              <LiveDot />
              {wsStatus === 'connected' ? 'Live' : 'Disconnected'}
            </div>
          </div>
        </header>

        {activeTab === 'terminal' ? (
          <TerminalAuditor />
        ) : (
          <>
            {/* TOP STAT CARDS */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard title="Realized PnL" value={`$${metrics.total_pnl.toFixed(2)}`} delay={0} />
          <StatCard title="Unrealized PnL" value={`${metrics.unrealized_pnl >= 0 ? '+' : ''}$${metrics.unrealized_pnl.toFixed(2)}`} delay={1} />
          <StatCard title="Win Rate" value={`${metrics.win_rate.toFixed(1)}`} suffix="%" delay={2} />
          <StatCard title="Total Trades" value={metrics.total_trades} delay={3} />
        </div>

        {/* MIDDLE BENTO */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* Balance History Chart (60%) */}
          <div className="animate-me lg:col-span-3 bg-white rounded-3xl p-6 border border-black/[0.04] shadow-[0_2px_12px_-2px_rgba(0,0,0,0.04)]">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-sm font-bold" style={{ color: COLORS.sage }}>Balance History</h3>
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.sage }}></span>
                Starting $10
              </div>
            </div>
            <div className="h-64 w-full">
              {balanceHistory.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={balanceHistory}>
                    <defs>
                      <linearGradient id="balanceGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.sage} stopOpacity={0.12}/>
                        <stop offset="95%" stopColor={COLORS.sage} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: COLORS.grayLight, fontSize: 11 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: COLORS.grayLight, fontSize: 11 }} domain={['auto', 'auto']} tickFormatter={(v) => `$${v}`} />
                    <Tooltip
                      contentStyle={{ backgroundColor: 'white', border: `1px solid ${COLORS.border}`, borderRadius: '14px', boxShadow: '0 8px 24px -4px rgba(0,0,0,0.08)', fontSize: '12px' }}
                      formatter={(val, name) => [`$${Number(val).toFixed(2)}`, name === 'balance' ? 'Balance' : 'PnL']}
                    />
                    <Area type="monotone" dataKey="balance" stroke={COLORS.sage} strokeWidth={2.5} fillOpacity={1} fill="url(#balanceGrad)" dot={{ r: 3, fill: COLORS.sage, strokeWidth: 2, stroke: '#fff' }} activeDot={{ r: 5, strokeWidth: 3, stroke: '#fff' }} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-gray-400">
                  <p className="text-sm">No balance data yet</p>
                  <p className="text-xs mt-1">Waiting for completed trades...</p>
                </div>
              )}
            </div>
          </div>

          {/* ML Confidence + Orderbook (40%) */}
          <div className="animate-me lg:col-span-2 bg-white rounded-3xl p-6 border border-black/[0.04] shadow-[0_2px_12px_-2px_rgba(0,0,0,0.04)]">
            <h3 className="text-sm font-bold mb-4" style={{ color: COLORS.sage }}>ML Confidence Score</h3>
            <div className="flex flex-col items-center justify-center py-2">
              <SemiCircleGauge
                value={mlConfidence}
                label="XGBoost Model Confidence"
                sublabel={`${mlStats.with_target} labeled / ${mlStats.total_records} total`}
                color={mlConfidence > 70 ? COLORS.green : mlConfidence > 40 ? '#F59E0B' : COLORS.red}
              />
            </div>
            <div className="mt-5 pt-4 border-t border-gray-100 space-y-2.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-400">Orderbook Spread</span>
                <span className="font-semibold" style={{ color: COLORS.sage }}>
                  {activeSignal?.spread != null ? `$${activeSignal.spread.toFixed(4)}` : 'N/A'}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-400">Best Bid</span>
                <span className="font-semibold" style={{ color: COLORS.sage }}>
                  {activeSignal?.current_token_price != null ? `$${activeSignal.current_token_price.toFixed(3)}` : 'N/A'}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-400">Entry Share</span>
                <span className="font-semibold" style={{ color: COLORS.sage }}>
                  {activeSignal?.entry_price_share != null ? `$${activeSignal.entry_price_share.toFixed(3)}` : 'N/A'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* BOTTOM BENTO */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Polymarket-Style Active Trade Card (100% Dynamic) */}
          <div className="animate-me">
            {activeSignal ? (
              <PolymarketActiveCard key={activeSignal.id} trade={activeSignal} />
            ) : (
              <EmptyTradeCard />
            )}
          </div>

          {/* Recent History */}
          <div className="animate-me bg-white rounded-3xl p-6 border border-black/[0.04] shadow-[0_2px_12px_-2px_rgba(0,0,0,0.04)]">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold" style={{ color: COLORS.sage }}>Recent History</h3>
              <span className="text-xs text-gray-400">Last {closedTrades.length} trades</span>
            </div>
            {closedTrades.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <p className="text-sm">No completed trades yet</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {closedTrades.map((trade) => (
                  <div key={trade.id} className="flex items-center justify-between p-3 rounded-2xl hover:bg-gray-50/80 transition-colors">
                    <div className="flex items-center gap-3">
                      <div className={`flex items-center justify-center w-9 h-9 rounded-xl font-bold text-xs ${trade.direction === 'UP' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                        {trade.direction === 'UP' ? <ArrowUpIcon className="w-3.5 h-3.5" /> : <ArrowDownIcon className="w-3.5 h-3.5" />}
                      </div>
                      <div>
                        <p className="text-sm font-semibold" style={{ color: COLORS.sage }}>Trade #{trade.id}</p>
                        <p className="text-[11px] text-gray-400">
                          {trade.timestamp ? new Date(trade.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'N/A'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <StatusBadge status={trade.status} pnl={trade.pnl} />
                      <span className={`text-sm font-bold tabular-nums ${trade.pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                        {trade.pnl != null ? `${trade.pnl >= 0 ? '+' : ''}$${trade.pnl.toFixed(2)}` : 'N/A'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* FOOTER */}
        <footer className="animate-me text-center py-4">
          <p className="text-xs text-gray-400">
            Polybot Quant Engine • Auto-trading 5-min BTC options • v2.1
          </p>
        </footer>
          </>
        )}
      </div>
    </div>
  );
}
