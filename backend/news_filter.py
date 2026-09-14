import requests
import json
import time
import os
import datetime

# Auto-sync high-impact USD schedule from free ForexFactory JSON mirror.
# Falls back silently to manual news_blackout.json entries when offline.
NEWS_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_blackout.json")
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SYNC_INTERVAL = 3600          # refresh schedule every 1 hour
BUFFER_BEFORE = 15 * 60       # blackout 15 minutes before event
BUFFER_AFTER = 30 * 60        # ... and 30 minutes after


class NewsFilter:
    def __init__(self):
        self.blackout_windows = []   # list of (start_ts, end_ts, event_name)
        self.upcoming = []           # list of dicts, sorted by start_ts
        self.last_sync = 0
        self._load_manual_calendar()
        self._auto_sync()            # initial pull at boot

    # --- parsing / fetching ---
    @staticmethod
    def _parse_ts(date_str):
        if not date_str:
            return None
        try:
            return datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00")).timestamp()
        except Exception:
            try:
                return datetime.datetime.fromisoformat(date_str).timestamp()
            except Exception:
                return None

    @staticmethod
    def _fetch_high_usd():
        """Fetch USD High-impact events from ForexFactory JSON mirror (free, no key)."""
        r = requests.get(FF_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        items = r.json()
        return [
            it for it in items
            if it.get("country") == "USD" and str(it.get("impact", "")).lower() == "high"
        ]

    # --- persistence ---
    def _load_manual_calendar(self):
        """Reload blackout windows from the JSON file (keeps future events only)."""
        try:
            if not os.path.exists(NEWS_CACHE_FILE):
                self._write_file({"events": [], "last_sync_utc": None})
            with open(NEWS_CACHE_FILE, "r") as f:
                data = json.load(f)
            now = time.time()
            self.blackout_windows = [
                (w["start_ts"], w["end_ts"], w["event_name"])
                for w in data.get("events", [])
                if w.get("end_ts", 0) > now
            ]
        except Exception as e:
            print(f"[NEWS FILTER] Load error: {e}")
            self.blackout_windows = []

    def _write_file(self, payload):
        with open(NEWS_CACHE_FILE, "w") as f:
            json.dump(payload, f, indent=2)

    def _merge_write(self, new_windows):
        """Keep manual entries, replace auto entries with fresh schedule."""
        manual = []
        try:
            if os.path.exists(NEWS_CACHE_FILE):
                with open(NEWS_CACHE_FILE, "r") as f:
                    data = json.load(f)
                manual = [w for w in data.get("events", []) if not w.get("auto")]
        except Exception:
            manual = []
        merged = [{**w, "auto": True} for w in new_windows] + manual
        self._write_file({
            "events": merged,
            "last_sync_utc": datetime.datetime.utcnow().isoformat(),
        })
        self._load_manual_calendar()

    # --- public API ---
    def _auto_sync(self):
        """Pull fresh USD High schedule at most once per hour; never throws."""
        if time.time() - self.last_sync < SYNC_INTERVAL:
            return
        self.last_sync = time.time()
        try:
            events = self._fetch_high_usd()
            if not events:
                return
            windows, upcoming = [], []
            now = time.time()
            for ev in events:
                ts = self._parse_ts(ev.get("date"))
                if not ts:
                    continue
                name = ev.get("title", "USD High Impact")
                start, end = int(ts - BUFFER_BEFORE), int(ts + BUFFER_AFTER)
                windows.append({"event_name": name, "start_ts": start, "end_ts": end, "auto": True})
                if end > now:
                    upcoming.append({
                        "event_name": name,
                        "start_ts": start,
                        "end_ts": end,
                        "minutes": max(0, int((start - now) / 60)),
                    })
            self.upcoming = sorted(upcoming, key=lambda x: x["start_ts"])
            self._merge_write(windows)
            print(f"[NEWS SYNC] {len(windows)} USD High events (auto) | next: {self.upcoming[0]['event_name'] if self.upcoming else 'none'}")
        except Exception as e:
            print(f"[NEWS SYNC ERROR] {e}")

    def is_blackout_active(self):
        """True if now falls inside a blackout window (auto or manual)."""
        self._auto_sync()
        self._load_manual_calendar()
        now = time.time()
        return any(s <= now <= e for s, e, _ in self.blackout_windows)

    def get_next_blackout(self):
        now = time.time()
        future = [(s, e, n) for s, e, n in self.blackout_windows if e > now]
        if not future:
            return None, None
        future.sort()
        start, _, name = future[0]
        return name, max(0, int((start - now) / 60))

    def get_upcoming_news(self, limit=8):
        """Upcoming blackout events for UI display."""
        self._auto_sync()
        self._load_manual_calendar()
        now = time.time()
        rows = []
        for s, e, n in self.blackout_windows:
            if e > now:
                rows.append({
                    "event_name": n,
                    "start_ts": int(s),
                    "end_ts": int(e),
                    "minutes": max(0, int((s - now) / 60)),
                })
        rows.sort(key=lambda x: x["start_ts"])
        return rows[:limit]


# Singleton
news_filter = NewsFilter()