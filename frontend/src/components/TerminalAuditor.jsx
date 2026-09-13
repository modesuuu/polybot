import React, { useState, useEffect } from 'react';

export const TerminalAuditor = () => {
  const [logs, setLogs] = useState([]);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);

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

  const fetchData = async () => {
    try {
      const [resHistory, resConfig] = await Promise.all([
        fetch('http://localhost:8000/api/ml/audit-history'),
        fetch('http://localhost:8000/api/ml/meta-config')
      ]);
      if (!resHistory.ok) throw new Error(`Audit history error: ${resHistory.status}`);
      if (!resConfig.ok) throw new Error(`Meta config error: ${resConfig.status}`);

      const dataHistory = await resHistory.json();
      const dataConfig = await resConfig.json();

      setLogs(dataHistory || []);
      setConfig(dataConfig || {});
    } catch (err) {
      console.error('Error loading auditor data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, [sessionSince]);

  const handleReset = async () => {
    if (confirm("Reset konfigurasi AI ke default pabrik?")) {
      try {
        const res = await fetch('http://localhost:8000/api/ml/reset-config', { method: 'POST' });
        if (!res.ok) throw new Error(`Reset error: ${res.status}`);
        fetchData();
      } catch (err) {
        console.error('Failed to reset config', err);
        alert("Gagal mereset konfigurasi. Cek koneksi backend.");
      }
    }
  };

  if (loading) {
    return (
      <div className="bg-black text-green-500 font-mono p-6 rounded-3xl min-h-[400px] flex items-center justify-center border border-green-500/20">
        &gt; INITIALIZING QUANT TERMINAL...
      </div>
    );
  }

  return (
    <div className="bg-black text-green-400 font-mono p-6 rounded-3xl min-h-[500px] border border-green-500/20 shadow-[0_0_30px_rgba(0,255,65,0.1)]">
      {/* Header Terminal */}
      <div className="flex items-center justify-between border-b border-green-500/30 pb-4 mb-6">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
          <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
          <div className="w-3 h-3 rounded-full bg-green-500/80"></div>
          <span className="text-xs text-green-500/70 ml-2">root@neuro-optimizer:~#</span>
        </div>
        <button
                  onClick={handleReset}
                  className="text-xs px-3 py-1 bg-red-950/40 text-red-400 border border-red-500/30 rounded hover:bg-red-900/50 transition-all">
                  [RESET FACTORY CONFIG]
                </button>
                {/* NEW SESSION button */}
                <button
                  onClick={handleNewSession}
                  className="text-xs px-3 py-1 bg-amber-950/40 text-amber-400 border border-amber-500/30 rounded hover:bg-amber-900/50 transition-all ml-2">
                  [NEW SESSION]
                </button>
              </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Panel Config Aktif */}
        <div className="bg-gray-950/80 p-4 rounded-xl border border-green-500/20">
          <h4 className="text-xs font-bold text-green-300 uppercase tracking-wider mb-3">
            &gt; Live Meta Parameters
          </h4>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">OBI Threshold:</span>
              <span className="text-green-400 font-bold">{config?.obi_threshold || 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Confidence Threshold:</span>
              <span className="text-green-400 font-bold">{config?.confidence_threshold || 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Min Sentiment:</span>
              <span className="text-green-400 font-bold">{config?.min_sentiment_score || 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">RSI Period:</span>
              <span className="text-green-400 font-bold">{config?.strategy_parameters?.rsi_period || '14'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Last AI Audit:</span>
              <span className="text-green-400 font-bold">{config?.last_ai_tuning || 'Never'}</span>
            </div>
          </div>
          <div className="mt-4 pt-3 border-t border-green-500/20">
            <p className="text-[10px] text-gray-400 italic">
              "{config?.ai_recommendation || 'No recommendations yet.'}"
            </p>
          </div>
        </div>

        {/* Console Audit Logs */}
        <div className="md:col-span-2 bg-gray-950/80 p-4 rounded-xl border border-green-500/20 max-h-[350px] overflow-y-auto">
          <h4 className="text-xs font-bold text-green-300 uppercase tracking-wider mb-3">
            &gt; AI Reasoning &amp; Evolution Logs
          </h4>
          {logs.length === 0 ? (
            <p className="text-xs text-gray-500 italic">&gt; No audit logs recorded yet.</p>
          ) : (
            <div className="space-y-4">
              {logs.map((log, index) => (
                <div key={index} className="text-xs border-b border-green-500/10 pb-3">
                  <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
                    <span>{log.timestamp}</span>
                    <span className={log.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                      PnL: ${log.daily_pnl?.toFixed(2)} ({log.win_rate?.toFixed(1)}% WR)
                    </span>
                  </div>
                  <p className="text-green-300/90 leading-relaxed font-mono">
                    &gt; {log.ai_reasoning}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
