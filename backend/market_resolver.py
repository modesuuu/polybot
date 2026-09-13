import requests
import json
import time

GAMMA_API_BASE = "https://gamma-api.polymarket.com/events"
CLOB_PRICE_URL = "https://clob.polymarket.com/price"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"


def get_current_5m_slug():
    """
    Menghitung slug window 5-menit Polymarket yang sedang aktif berdasarkan UTC timestamp.
    
    Format slug yang ditemukan dari API Polymarket:
        btc-updown-5m-{timestamp}
    
    Returns:
        str: slug untuk window 5-menit saat ini
    """
    now_ts = int(time.time())
    current_window_ts = (now_ts // 300) * 300
    return f"btc-updown-5m-{current_window_ts}"


def get_next_5m_slug():
    """
    Menghitung slug window 5-menit Polymarket berikutnya.
    
    Returns:
        str: slug untuk window 5-menit berikutnya
    """
    now_ts = int(time.time())
    current_window_ts = (now_ts // 300) * 300
    next_window_ts = current_window_ts + 300
    return f"btc-updown-5m-{next_window_ts}"


def get_active_tokens():
    """
    Fetches the active clobTokenIds for Polymarket Bitcoin 5-minute event.
    
    Pasar Polymarket "BTC Up or Down 5m" berganti token ID setiap 5 menit.
    Fungsi ini menghitung slug window 5-menit aktif berdasarkan UTC timestamp
    saat ini, lalu mengambil token_id (UP & DOWN) yang valid dari Gamma API.
    
    Returns:
        dict: {'UP': 'clob_token_id_up', 'DOWN': 'clob_token_id_down'}
        atau None jika belum ditemukan.
    """
    now_ts = int(time.time())
    current_window_ts = (now_ts // 300) * 300
    
    # Daftar kandidat slug yang diperiksa secara berurutan
    # Prioritas: window saat ini, window berikutnya, slug statis
    candidate_slugs = [
        get_current_5m_slug(),
        get_next_5m_slug(),
        f"btc-updown-5m-{current_window_ts + 300}",
        "btc-up-or-down-5-minutes",
        f"btc-up-or-down-5m-{current_window_ts}",
        f"will-btc-go-up-or-down-in-the-next-5-minutes-{current_window_ts}",
        f"will-btc-go-up-or-down-in-the-next-5-minutes-{current_window_ts + 300}",
    ]

    for slug in candidate_slugs:
        try:
            url = f"{GAMMA_API_BASE}?slug={slug}"
            try:
                response = requests.get(url, timeout=5, verify=False)
            except Exception:
                response = requests.get(url, timeout=5)
            if response.status_code != 200:
                continue

            events = response.json()
            if not events or not isinstance(events, list) or len(events) == 0:
                continue

            event = events[0]
            markets = event.get('markets', [])
            if not markets:
                continue

            market = markets[0]
            clob_token_ids = market.get('clobTokenIds')
            if isinstance(clob_token_ids, str):
                clob_token_ids = json.loads(clob_token_ids)

            if not clob_token_ids or len(clob_token_ids) < 2:
                continue

            # Parsing outcomes jika tersedia
            outcomes = market.get('outcomes', [])
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)

            up_token = clob_token_ids[0]
            down_token = clob_token_ids[1]

            # Jika outcomes tersedia, pastikan mapping benar
            if len(outcomes) >= 2:
                if str(outcomes[0]).strip().lower() in ['down', 'no']:
                    up_token, down_token = clob_token_ids[1], clob_token_ids[0]

            print(f"[MarketResolver] Market ditemukan (slug: {slug}) | UP Token: {up_token[:16]}... | DOWN Token: {down_token[:16]}...")
            return {
                'UP': str(up_token),
                'DOWN': str(down_token)
            }
        except (requests.exceptions.SSLError, requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_err:
            print(f"[NETWORK BLOCKED / VPN REQUIRED] Koneksi ke Polymarket diblokir/timeout: {net_err}. NYALAKAN VPN SEKARANG!")
            return None
        except Exception as e:
            # Lanjut ke kandidat slug berikutnya jika terjadi error
            continue

    print("[MarketResolver] Tidak ada market aktif 5-min yang ditemukan di Gamma API saat ini.")
    return None


def get_polymarket_orderbook(token_id: str) -> dict:
    """
    Mengambil orderbook live dari Polymarket CLOB Book API.
    
    Endpoint: https://clob.polymarket.com/book?token_id={token_id}
    
    IMPORTANT: Bids dan asks dari API TIDAK selalu terurut.
    Fungsi ini melakukan sorting:
      - Bids: descending (harga tertinggi di depan)
      - Asks: ascending (harga terendah di depan)
    
    Returns:
        dict: {
            'best_bid': float | None,      # Harga jual nyata (sorted bids[0].price)
            'best_ask': float | None,      # Harga beli nyata (sorted asks[0].price)
            'mid_price': float | None,     # (best_bid + best_ask) / 2
            'spread': float | None,        # best_ask - best_bid
            'bids': list,                  # Raw bids array
            'asks': list,                  # Raw asks array
            'timestamp': float             # Unix timestamp fetch
        }
        atau None jika gagal.
    """
    if not token_id:
        print("[ORDERBOOK ERROR] token_id kosong.")
        return None

    try:
        url = f"{CLOB_BOOK_URL}?token_id={token_id}"
        try:
            response = requests.get(url, timeout=8, verify=False)
        except Exception:
            response = requests.get(url, timeout=8)

        if response.status_code != 200:
            print(f"[ORDERBOOK ERROR] HTTP {response.status_code}: {response.text[:200]}")
            return None

        data = response.json()
        raw_bids = data.get("bids", [])
        raw_asks = data.get("asks", [])

        # === SORTING: Bids descending, Asks ascending ===
        # Bids: descending (harga tertinggi di depan)
        bids = sorted(raw_bids, key=lambda x: float(x.get("price", 0)), reverse=True)
        # Asks: ascending (harga terendah di depan)
        asks = sorted(raw_asks, key=lambda x: float(x.get("price", 0)))

        best_bid = None
        best_ask = None
        mid_price = None
        spread = None

        # Best bid = bid dengan harga TERTINGGI (setelah sort, index 0)
        if bids and len(bids) > 0:
            try:
                best_bid = float(bids[0].get("price", 0))
            except (ValueError, TypeError, AttributeError):
                best_bid = None

        # Best ask = ask dengan harga TERENDAH (setelah sort, index 0)
        if asks and len(asks) > 0:
            try:
                best_ask = float(asks[0].get("price", 0))
            except (ValueError, TypeError, AttributeError):
                best_ask = None

        # Hitung mid_price dan spread jika keduanya tersedia
        if best_bid is not None and best_ask is not None:
            mid_price = round((best_bid + best_ask) / 2, 6)
            spread = round(best_ask - best_bid, 6)

        result = {
            'best_bid': best_bid,
            'best_ask': best_ask,
            'mid_price': mid_price,
            'spread': spread,
            'bids': bids,
            'asks': asks,
            'timestamp': time.time()
        }

        print(f"[ORDERBOOK FETCH] Token: {token_id[:16]}... | Best Bid: ${best_bid} | Best Ask: ${best_ask} | Mid: ${mid_price} | Spread: ${spread}")
        return result

    except requests.exceptions.Timeout:
        print(f"[ORDERBOOK ERROR] Timeout fetching orderbook for token {token_id[:16]}...")
        return None
    except Exception as e:
        print(f"[ORDERBOOK ERROR] Exception fetching orderbook: {e}")
        return None


def get_current_token_price(token_id: str) -> float:
    """
    Mengambil harga live best ask/bid dari Polymarket CLOB:
    https://clob.polymarket.com/price?token_id={token_id}&side=buy
    Mengembalikan float harga aktual jika berhasil.
    
    Catatan: Fungsi ini digunakan sebagai FALLBACK ketika orderbook tidak tersedia.
    """
    if not token_id:
        return None

    try:
        url = f"{CLOB_PRICE_URL}?token_id={token_id}&side=buy"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            raw_price = data.get("price")
            if raw_price is not None:
                try:
                    price = float(raw_price)
                    print(f"[LIVE PRICE FETCH] Token ID: {token_id[:10]}... | Price Received: ${price:.4f} | Status Code: 200")
                    return price
                except (ValueError, TypeError) as parse_err:
                    print(f"[LIVE PRICE ERROR] Parsing error for price '{raw_price}': {parse_err}")
                    return None

        print(f"[LIVE PRICE ERROR] Failed to fetch price: {response.text} | Status Code: {response.status_code}")
        return None

    except Exception as e:
        print(f"[LIVE PRICE ERROR] Exception fetching token price: {e}")
        return None


# Alias untuk backward-compatibility
get_live_token_price = get_current_token_price
