# ============================================================
# PERSONAL HOTEL DEAL HUNTER – VERSION 5
# Mobile-first / iPhone-first
# ============================================================

from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import math
from datetime import datetime, date, timedelta
from statistics import median

app = Flask(__name__)

DB_FILE = os.environ.get("HOTEL_DB", "hotel_deals.db")

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS hotels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        city TEXT,
        country TEXT,
        latitude REAL,
        longitude REAL,
        stars REAL DEFAULT 0,
        image TEXT,
        booking_url TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS price_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hotel_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        check_in TEXT NOT NULL,
        check_out TEXT NOT NULL,
        adults INTEGER DEFAULT 2,
        child_ages TEXT DEFAULT '14,16',
        room_type TEXT,
        total_price REAL NOT NULL,
        currency TEXT DEFAULT 'SEK',
        verified INTEGER DEFAULT 0,
        observed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(hotel_id) REFERENCES hotels(id)
    );

    CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hotel_id INTEGER NOT NULL UNIQUE,
        target_price REAL,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(hotel_id) REFERENCES hotels(id)
    );

    CREATE TABLE IF NOT EXISTS radars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        destination TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()


init_db()

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

SOURCES = ["Booking.com", "Expedia", "Agoda", "Hotelbeds"]


def nights_between(check_in, check_out):
    try:
        a = datetime.strptime(check_in, "%Y-%m-%d").date()
        b = datetime.strptime(check_out, "%Y-%m-%d").date()
        return max((b - a).days, 1)
    except Exception:
        return 1


def format_price(value):
    try:
        return f"{float(value):,.0f}".replace(",", " ") + " kr"
    except Exception:
        return "–"


def calculate_deal_score(current_price, history, verified, source_count):
    """
    Deal Score V5 – 0 to 100

    Weighting:
    30 = discount vs historical median
    25 = proximity to historical low
    15 = multiple-source confirmation
    10 = verified price
    10 = historical depth
    10 = exceptional-price signal
    """

    if not history:
        return 50, {}

    prices = [float(x) for x in history if x and float(x) > 0]

    if not prices:
        return 50, {}

    med = median(prices)
    low = min(prices)

    # 1. Discount vs median – max 30
    if med > 0:
        discount = (med - current_price) / med
    else:
        discount = 0

    median_score = max(0, min(30, discount * 100))

    # 2. Near historical low – max 25
    if current_price <= low:
        low_score = 25
    elif low > 0:
        ratio = low / current_price
        low_score = max(0, min(25, 25 * ratio))
    else:
        low_score = 0

    # 3. Multiple sources – max 15
    source_score = min(15, max(0, source_count - 1) * 7.5)

    # 4. Verified – max 10
    verified_score = 10 if verified else 2

    # 5. Historical depth – max 10
    history_score = min(10, len(prices) / 2)

    # 6. Exceptional price signal – max 10
    if discount >= 0.30:
        exceptional_score = 10
    elif discount >= 0.20:
        exceptional_score = 8
    elif discount >= 0.10:
        exceptional_score = 5
    elif discount > 0:
        exceptional_score = 2
    else:
        exceptional_score = 0

    score = (
        median_score +
        low_score +
        source_score +
        verified_score +
        history_score +
        exceptional_score
    )

    score = int(round(max(0, min(100, score))))

    detail = {
        "historical_median": med,
        "historical_low": low,
        "discount_pct": round(discount * 100, 1),
        "median_score": round(median_score, 1),
        "low_score": round(low_score, 1),
        "source_score": round(source_score, 1),
        "verified_score": verified_score,
        "history_score": round(history_score, 1),
        "exceptional_score": exceptional_score
    }

    return score, detail


def deal_label(score):
    if score >= 90:
        return "EXTREMT FYND", "deal-red"
    if score >= 80:
        return "SUPERDEAL", "deal-orange"
    if score >= 70:
        return "MYCKET BRA", "deal-green"
    if score >= 60:
        return "BRA DEAL", "deal-blue"
    return "NORMALPRIS", "deal-grey"


def get_deals():
    conn = db()

    rows = conn.execute("""
        SELECT
            p.*,
            h.name,
            h.city,
            h.country,
            h.stars,
            h.image,
            h.booking_url
        FROM price_observations p
        JOIN hotels h ON h.id = p.hotel_id
        ORDER BY p.observed_at DESC
    """).fetchall()

    deals = []

    # Only newest observation per hotel/source/stay
    seen = set()

    for row in rows:
        key = (
            row["hotel_id"],
            row["source"],
            row["check_in"],
            row["check_out"]
        )

        if key in seen:
            continue

        seen.add(key)

        history_rows = conn.execute("""
            SELECT total_price
            FROM price_observations
            WHERE hotel_id = ?
              AND check_in = ?
              AND check_out = ?
            ORDER BY observed_at
        """, (
            row["hotel_id"],
            row["check_in"],
            row["check_out"]
        )).fetchall()

        history = [x["total_price"] for x in history_rows]

        sources = conn.execute("""
            SELECT COUNT(DISTINCT source) AS c
            FROM price_observations
            WHERE hotel_id = ?
              AND check_in = ?
              AND check_out = ?
        """, (
            row["hotel_id"],
            row["check_in"],
            row["check_out"]
        )).fetchone()["c"]

        score, score_detail = calculate_deal_score(
            float(row["total_price"]),
            history,
            bool(row["verified"]),
            sources
        )

        label, css = deal_label(score)

        nights = nights_between(
            row["check_in"],
            row["check_out"]
        )

        deals.append({
            "id": row["id"],
            "hotel_id": row["hotel_id"],
            "name": row["name"],
            "city": row["city"] or "",
            "country": row["country"] or "",
            "stars": row["stars"] or 0,
            "image": row["image"] or "",
            "booking_url": row["booking_url"] or "",
            "source": row["source"],
            "check_in": row["check_in"],
            "check_out": row["check_out"],
            "nights": nights,
            "price": float(row["total_price"]),
            "price_text": format_price(row["total_price"]),
            "night_price": float(row["total_price"]) / nights,
            "night_price_text": format_price(float(row["total_price"]) / nights),
            "verified": bool(row["verified"]),
            "score": score,
            "label": label,
            "css": css,
            "score_detail": score_detail
        })

    conn.close()

    deals.sort(key=lambda x: x["score"], reverse=True)
    return deals


# ------------------------------------------------------------
# DEMO / START DATA
# ------------------------------------------------------------

def seed_demo():
    conn = db()

    count = conn.execute(
        "SELECT COUNT(*) AS c FROM hotels"
    ).fetchone()["c"]

    if count > 0:
        conn.close()
        return

    hotels = [
        ("Hotel d'Angleterre", "Copenhagen", "Denmark", 5),
        ("Grand Hôtel Stockholm", "Stockholm", "Sweden", 5),
        ("Hotel Schweizerhof Zürich", "Zürich", "Switzerland", 5),
        ("The Balmoral", "Edinburgh", "United Kingdom", 5),
        ("Cap Rocat", "Mallorca", "Spain", 5)
    ]

    for name, city, country, stars in hotels:
        conn.execute("""
            INSERT INTO hotels(name, city, country, stars)
            VALUES (?, ?, ?, ?)
        """, (name, city, country, stars))

    conn.commit()
    conn.close()


seed_demo()

# ------------------------------------------------------------
# HTML
# ------------------------------------------------------------

HTML = """
<!doctype html>
<html lang="sv">
<head>

<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1, viewport-fit=cover">

<meta name="theme-color" content="#07111f">

<title>Personal Hotel Deal Hunter</title>

<style>

* {
    box-sizing:border-box;
}

body {
    margin:0;
    font-family:-apple-system,BlinkMacSystemFont,
                "SF Pro Display","Segoe UI",sans-serif;
    background:#07111f;
    color:white;
}

.app {
    max-width:760px;
    margin:auto;
    min-height:100vh;
    padding-bottom:100px;
}

.header {
    padding:22px 18px 12px;
}

.logo {
    font-size:13px;
    letter-spacing:2px;
    color:#8da2bd;
    font-weight:700;
}

h1 {
    margin:5px 0 2px;
    font-size:29px;
    letter-spacing:-1px;
}

.subtitle {
    color:#93a4ba;
    font-size:14px;
}

.searchbox {
    margin:12px 14px;
    padding:15px;
    border-radius:20px;
    background:#101d2e;
    border:1px solid #1d3048;
}

.searchbox input,
.searchbox select {
    width:100%;
    background:#091522;
    border:1px solid #263a53;
    color:white;
    padding:13px;
    border-radius:12px;
    font-size:16px;
    margin-top:7px;
}

.grid {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:8px;
}

button {
    border:0;
    border-radius:12px;
    padding:13px;
    font-size:15px;
    font-weight:700;
    cursor:pointer;
}

.primary {
    width:100%;
    margin-top:10px;
    background:#fff;
    color:#07111f;
}

.section-title {
    padding:16px 16px 7px;
    font-size:20px;
    font-weight:800;
}

.card {
    margin:9px 14px;
    border-radius:20px;
    background:#101d2e;
    border:1px solid #1d3048;
    overflow:hidden;
}

.card-body {
    padding:15px;
}

.hotel-top {
    display:flex;
    justify-content:space-between;
    gap:12px;
}

.hotel-name {
    font-size:18px;
    font-weight:800;
}

.location {
    margin-top:3px;
    color:#91a3b9;
    font-size:13px;
}

.score {
    min-width:61px;
    height:61px;
    border-radius:50%;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    background:#07111f;
    border:3px solid #39d98a;
}

.score-number {
    font-size:20px;
    font-weight:900;
    line-height:20px;
}

.score-label {
    font-size:8px;
    color:#aab9ca;
}

.deal-tag {
    display:inline-block;
    margin-top:11px;
    padding:6px 9px;
    border-radius:8px;
    font-size:11px;
    font-weight:900;
}

.deal-red {
    background:#ff4057;
}

.deal-orange {
    background:#ff8b36;
}

.deal-green {
    background:#1fbd76;
}

.deal-blue {
    background:#337cf5;
}

.deal-grey {
    background:#566579;
}

.price-row {
    display:flex;
    justify-content:space-between;
    align-items:flex-end;
    margin-top:15px;
}

.price {
    font-size:26px;
    font-weight:900;
}

.per-night {
    color:#94a5b9;
    font-size:12px;
}

.source {
    text-align:right;
    font-size:13px;
}

.verified {
    color:#45df97;
    font-weight:700;
}

.uncertain {
    color:#f6ba4a;
    font-weight:700;
}

.dates {
    margin-top:12px;
    background:#091522;
    border-radius:10px;
    padding:9px 10px;
    font-size:12px;
    color:#bac7d6;
}

.empty {
    margin:20px 14px;
    padding:30px 20px;
    border-radius:20px;
    background:#101d2e;
    text-align:center;
    color:#a5b5c8;
}

.nav {
    position:fixed;
    bottom:0;
    left:0;
    right:0;
    height:75px;
    background:rgba(7,17,31,.96);
    border-top:1px solid #203149;
    display:flex;
    justify-content:center;
    z-index:20;
    padding-bottom:env(safe-area-inset-bottom);
}

.nav-inner {
    max-width:760px;
    width:100%;
    display:flex;
}

.nav a {
    flex:1;
    text-decoration:none;
    color:#8193a9;
    text-align:center;
    font-size:11px;
    padding-top:12px;
}

.nav-icon {
    font-size:22px;
    display:block;
    margin-bottom:3px;
}

.active {
    color:white !important;
}

.stats {
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:8px;
    margin:10px 14px;
}

.stat {
    background:#101d2e;
    border:1px solid #1d3048;
    padding:13px 8px;
    border-radius:15px;
    text-align:center;
}

.stat-number {
    font-size:21px;
    font-weight:900;
}

.stat-label {
    font-size:10px;
    color:#8fa1b7;
    margin-top:3px;
}

.small {
    color:#93a5ba;
    font-size:12px;
}

</style>

</head>

<body>

<div class="app">

<div class="header">
    <div class="logo">PAHLMANS</div>
    <h1>Hotel Deal Hunter</h1>
    <div class="subtitle">
        Hitta hotellpriser som sticker ut på riktigt.
    </div>
</div>

<div class="searchbox">

<form method="get">

<input
    name="destination"
    placeholder="Vart vill du åka?"
    value="{{ destination }}">

<div class="grid">

<div>
<input
    type="date"
    name="checkin"
    value="{{ checkin }}">
</div>

<div>
<input
    type="date"
    name="checkout"
    value="{{ checkout }}">
</div>

</div>

<div class="small" style="margin-top:10px">
    Standard: 2 vuxna + barn 14 och 16 år
</div>

<button class="primary">
    Sök hotell & deals
</button>

</form>

</div>

<div class="stats">

<div class="stat">
<div class="stat-number">{{ deals|length }}</div>
<div class="stat-label">DEALS</div>
</div>

<div class="stat">
<div class="stat-number">{{ verified_count }}</div>
<div class="stat-label">VERIFIERADE</div>
</div>

<div class="stat">
<div class="stat-number">{{ hot_count }}</div>
<div class="stat-label">FYND 80+</div>
</div>

</div>

<div class="section-title">
    🔥 Deal Radar
</div>

{% if deals %}

{% for d in deals %}

<div class="card">

<div class="card-body">

<div class="hotel-top">

<div>
<div class="hotel-name">
{{ d.name }}
</div>

<div class="location">
{{ d.city }}{% if d.country %}, {{ d.country }}{% endif %}
{% if d.stars %}
 · {{ d.stars|int }}★
{% endif %}
</div>
</div>

<div class="score">
<div class="score-number">
{{ d.score }}
</div>
<div class="score-label">
DEAL SCORE
</div>
</div>

</div>

<div class="deal-tag {{ d.css }}">
{{ d.label }}
</div>

<div class="price-row">

<div>
<div class="price">
{{ d.price_text }}
</div>

<div class="per-night">
{{ d.night_price_text }} / natt
</div>
</div>

<div class="source">
{{ d.source }}<br>

{% if d.verified %}
<span class="verified">
✓ Verifierat pris
</span>
{% else %}
<span class="uncertain">
● Ej verifierat
</span>
{% endif %}

</div>

</div>

<div class="dates">
{{ d.check_in }} → {{ d.check_out }}
&nbsp; · &nbsp;
{{ d.nights }} nätter
</div>

{% if d.score_detail.discount_pct is defined %}
<div class="small" style="margin-top:10px">
Historisk median:
{{ d.score_detail.historical_median|round|int }} kr
&nbsp; · &nbsp;
Skillnad:
{{ d.score_detail.discount_pct }}%
</div>
{% endif %}

</div>
</div>

{% endfor %}

{% else %}

<div class="empty">

<div style="font-size:35px">📡</div>

<h3>Radarn väntar på priser</h3>

När prisobservationer läggs in jämför V5 dem med
prishistoriken och räknar automatiskt ut Deal Score.

</div>

{% endif %}

</div>

<div class="nav">

<div class="nav-inner">

<a href="/" class="active">
<span class="nav-icon">🔥</span>
Deals
</a>

<a href="/radars">
<span class="nav-icon">📡</span>
Radars
</a>

<a href="/watchlist">
<span class="nav-icon">♡</span>
Bevakning
</a>

<a href="/history">
<span class="nav-icon">📈</span>
Historik
</a>

</div>

</div>

</body>
</html>
"""

# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------

@app.route("/")
def home():

    destination = request.args.get("destination", "").strip()
    checkin = request.args.get("checkin", "")
    checkout = request.args.get("checkout", "")

    deals = get_deals()

    if destination:
        destination_lower = destination.lower()

        deals = [
            d for d in deals
            if destination_lower in (
                d["name"] + " " +
                d["city"] + " " +
                d["country"]
            ).lower()
        ]

    if checkin:
        deals = [
            d for d in deals
            if d["check_in"] == checkin
        ]

    if checkout:
        deals = [
            d for d in deals
            if d["check_out"] == checkout
        ]

    verified_count = len([
        d for d in deals if d["verified"]
    ])

    hot_count = len([
        d for d in deals if d["score"] >= 80
    ])

    return render_template_string(
        HTML,
        deals=deals,
        destination=destination,
        checkin=checkin,
        checkout=checkout,
        verified_count=verified_count,
        hot_count=hot_count
    )


@app.route("/api/observation", methods=["POST"])
def add_observation():

    data = request.get_json(force=True)

    required = [
        "hotel_id",
        "source",
        "check_in",
        "check_out",
        "total_price"
    ]

    missing = [
        x for x in required
        if x not in data
    ]

    if missing:
        return jsonify({
            "ok": False,
            "error": "Missing: " + ", ".join(missing)
        }), 400

    conn = db()

    conn.execute("""
        INSERT INTO price_observations
        (
            hotel_id,
            source,
            check_in,
            check_out,
            adults,
            child_ages,
            room_type,
            total_price,
            currency,
            verified
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["hotel_id"],
        data["source"],
        data["check_in"],
        data["check_out"],
        data.get("adults", 2),
        data.get("child_ages", "14,16"),
        data.get("room_type", ""),
        float(data["total_price"]),
        data.get("currency", "SEK"),
        1 if data.get("verified") else 0
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True
    })


@app.route("/api/hotels", methods=["GET", "POST"])
def hotels_api():

    conn = db()

    if request.method == "POST":

        data = request.get_json(force=True)

        cursor = conn.execute("""
            INSERT INTO hotels
            (
                name,
                city,
                country,
                stars,
                latitude,
                longitude,
                image,
                booking_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("name"),
            data.get("city"),
            data.get("country"),
            data.get("stars", 0),
            data.get("latitude"),
            data.get("longitude"),
            data.get("image"),
            data.get("booking_url")
        ))

        conn.commit()

        hotel_id = cursor.lastrowid
        conn.close()

        return jsonify({
            "ok": True,
            "hotel_id": hotel_id
        })

    rows = conn.execute("""
        SELECT *
        FROM hotels
        ORDER BY name
    """).fetchall()

    conn.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


@app.route("/api/deals")
def deals_api():
    return jsonify(get_deals())


@app.route("/radars")
def radars():

    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM radars
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    body = """
    <h1>📡 Mina Radars</h1>

    <p>
    Separata hotellradars för destinationer och resor.
    </p>

    {% if rows %}
        {% for r in rows %}
        <div class="card">
            <div class="card-body">
                <div class="hotel-name">
                    {{ r.name }}
                </div>
                <div class="location">
                    {{ r.destination or "" }}
                </div>
            </div>
        </div>
        {% endfor %}
    {% else %}
        <div class="empty">
            Ingen radar skapad ännu.
        </div>
    {% endif %}
    """

    return simple_page(
        "Radars",
        body,
        rows=rows
    )


@app.route("/watchlist")
def watchlist():

    conn = db()

    rows = conn.execute("""
        SELECT
            w.*,
            h.name,
            h.city,
            h.country
        FROM watchlist w
        JOIN hotels h ON h.id = w.hotel_id
        WHERE w.active = 1
        ORDER BY w.id DESC
    """).fetchall()

    conn.close()

    body = """
    <h1>♡ Bevakning</h1>

    <p>
    Hotell du vill följa extra noga.
    </p>

    {% if rows %}
        {% for r in rows %}
        <div class="card">
            <div class="card-body">

                <div class="hotel-name">
                    {{ r.name }}
                </div>

                <div class="location">
                    {{ r.city }}, {{ r.country }}
                </div>

                {% if r.target_price %}
                <div style="margin-top:10px">
                    Målpris:
                    <strong>
                    {{ r.target_price|round|int }} kr
                    </strong>
                </div>
                {% endif %}

            </div>
        </div>
        {% endfor %}
    {% else %}
        <div class="empty">
            Inga hotell bevakas ännu.
        </div>
    {% endif %}
    """

    return simple_page(
        "Bevakning",
        body,
        rows=rows
    )


@app.route("/history")
def history():

    conn = db()

    rows = conn.execute("""
        SELECT
            p.*,
            h.name
        FROM price_observations p
        JOIN hotels h ON h.id = p.hotel_id
        ORDER BY p.observed_at DESC
        LIMIT 100
    """).fetchall()

    conn.close()

    body = """
    <h1>📈 Prishistorik</h1>

    <p>
    De senaste 100 prisobservationerna.
    </p>

    {% if rows %}

        {% for r in rows %}

        <div class="card">

            <div class="card-body">

                <div class="hotel-name">
                    {{ r.name }}
                </div>

                <div style="
                    font-size:22px;
                    font-weight:900;
                    margin-top:8px">

                    {{ r.total_price|round|int }} kr

                </div>

                <div class="location">

                    {{ r.source }}
                    ·
                    {{ r.check_in }}
                    →
                    {{ r.check_out }}

                </div>

                <div class="small"
                     style="margin-top:7px">

                    {{ r.observed_at }}

                    {% if r.verified %}
                    · ✓ verifierat
                    {% else %}
                    · ej verifierat
                    {% endif %}

                </div>

            </div>

        </div>

        {% endfor %}

    {% else %}

        <div class="empty">
            Ingen prishistorik ännu.
        </div>

    {% endif %}
    """

    return simple_page(
        "Historik",
        body,
        rows=rows
    )


def simple_page(title, body, **kwargs):

    template = """
    <!doctype html>

    <html lang="sv">

    <head>

    <meta charset="utf-8">

    <meta name="viewport"
          content="width=device-width,
                   initial-scale=1,
                   viewport-fit=cover">

    <title>{{ title }}</title>

    <style>

    * {
        box-sizing:border-box;
    }

    body {
        margin:0;
        background:#07111f;
        color:white;
        font-family:-apple-system,
                    BlinkMacSystemFont,
                    "SF Pro Display",
                    "Segoe UI",
                    sans-serif;
    }

    main {
        max-width:760px;
        margin:auto;
        padding:20px 14px 100px;
    }

    h1 {
        font-size:28px;
    }

    p {
        color:#96a8bc;
    }

    .card {
        margin:10px 0;
        border-radius:18px;
        background:#101d2e;
        border:1px solid #1d3048;
    }

    .card-body {
        padding:15px;
    }

    .hotel-name {
        font-size:18px;
        font-weight:800;
    }

    .location,
    .small {
        color:#91a3b9;
        font-size:13px;
        margin-top:4px;
    }

    .empty {
        background:#101d2e;
        padding:30px 20px;
        border-radius:18px;
        color:#9bacc0;
        text-align:center;
    }

    .back {
        display:inline-block;
        margin-bottom:10px;
        color:white;
        text-decoration:none;
    }

    </style>

    </head>

    <body>

    <main>

    <a class="back" href="/">
    ← Deal Hunter
    </a>

    """ + body + """

    </main>

    </body>

    </html>
    """

    return render_template_string(
        template,
        title=title,
        **kwargs
    )


# ------------------------------------------------------------
# HEALTH CHECK FOR RENDER
# ------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "5.0",
        "app": "Personal Hotel Deal Hunter"
    })


# ------------------------------------------------------------
# START
# ------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
