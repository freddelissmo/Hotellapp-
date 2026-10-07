from flask import Flask, render_template_string, request
from datetime import datetime

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hotellappen</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
            background: #f4f6f8;
            color: #17202a;
        }

        .header {
            background: #111827;
            color: white;
            padding: 28px 20px;
        }

        .header h1 {
            margin: 0;
            font-size: 30px;
        }

        .header p {
            margin: 7px 0 0;
            color: #d1d5db;
        }

        .container {
            max-width: 1000px;
            margin: auto;
            padding: 20px;
        }

        .searchbox {
            background: white;
            padding: 20px;
            border-radius: 16px;
            box-shadow: 0 4px 18px rgba(0,0,0,.08);
            margin-top: -10px;
        }

        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 5px;
        }

        input {
            width: 100%;
            padding: 13px;
            border: 1px solid #d1d5db;
            border-radius: 10px;
            font-size: 16px;
            margin-bottom: 13px;
        }

        button {
            width: 100%;
            background: #2563eb;
            color: white;
            border: 0;
            padding: 15px;
            border-radius: 10px;
            font-size: 17px;
            font-weight: 700;
        }

        .results-title {
            margin-top: 28px;
            margin-bottom: 14px;
        }

        .hotel {
            background: white;
            border-radius: 15px;
            padding: 17px;
            margin-bottom: 14px;
            box-shadow: 0 2px 10px rgba(0,0,0,.06);
        }

        .hotel-top {
            display: flex;
            justify-content: space-between;
            gap: 10px;
        }

        .hotel h3 {
            margin: 0 0 5px;
        }

        .location {
            color: #6b7280;
            font-size: 14px;
        }

        .rating {
            background: #166534;
            color: white;
            padding: 7px 9px;
            height: fit-content;
            border-radius: 8px;
            font-weight: bold;
        }

        .prices {
            margin-top: 15px;
            border-top: 1px solid #eee;
            padding-top: 10px;
        }

        .price-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
        }

        .best {
            color: #15803d;
            font-weight: 700;
        }

        .map {
            margin-top: 25px;
            background: #dbeafe;
            height: 210px;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 20px;
        }

        .info {
            margin-top: 20px;
            color: #6b7280;
            font-size: 13px;
            line-height: 1.5;
        }

        @media (min-width: 700px) {
            .form-grid {
                display: grid;
                grid-template-columns: 2fr 1fr 1fr 1fr;
                gap: 10px;
                align-items: end;
            }

            input {
                margin-bottom: 0;
            }
        }
    </style>
</head>

<body>

<div class="header">
    <div class="container">
        <h1>🏨 Hotellappen</h1>
        <p>Jämför hotell och priser på ett ställe</p>
    </div>
</div>

<div class="container">

    <form class="searchbox" method="POST">

        <div class="form-grid">

            <div>
                <label>Destination</label>
                <input
                    name="destination"
                    placeholder="T.ex. Mallorca"
                    value="{{ destination }}"
                    required>
            </div>

            <div>
                <label>Incheckning</label>
                <input type="date" name="checkin" value="{{ checkin }}">
            </div>

            <div>
                <label>Utcheckning</label>
                <input type="date" name="checkout" value="{{ checkout }}">
            </div>

            <div>
                <label>Gäster</label>
                <input
                    type="number"
                    name="guests"
                    min="1"
                    value="{{ guests }}">
            </div>

        </div>

        <br>

        <button type="submit">Sök hotell</button>

    </form>

    {% if searched %}

    <h2 class="results-title">
        Hotell i {{ destination }}
    </h2>

    {% for hotel in hotels %}

    <div class="hotel">

        <div class="hotel-top">

            <div>
                <h3>{{ hotel.name }}</h3>
                <div class="location">
                    📍 {{ destination }}
                </div>
            </div>

            <div class="rating">
                {{ hotel.rating }}
            </div>

        </div>

        <div class="prices">

            {% for price in hotel.prices %}

            <div class="price-row">
                <span>{{ price.site }}</span>

                <span class="{% if loop.first %}best{% endif %}">
                    {{ price.price }} kr
                </span>
            </div>

            {% endfor %}

        </div>

    </div>

    {% endfor %}

    <div class="map">
        🗺️<br><br>
        Karta för hotell i {{ destination }}<br>
        kommer i nästa version
    </div>

    <div class="info">
        Detta är första liveversionen av Hotellappen.
        Priserna är demonstrationsdata.
        Nästa steg är att koppla riktiga hotell- och prisdata
        från externa tjänster.
    </div>

    {% endif %}

</div>

</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():

    destination = ""
    checkin = ""
    checkout = ""
    guests = 2
    searched = False

    hotels = []

    if request.method == "POST":

        searched = True

        destination = request.form.get("destination", "")
        checkin = request.form.get("checkin", "")
        checkout = request.form.get("checkout", "")
        guests = request.form.get("guests", 2)

        hotels = [
            {
                "name": "Grand Hotel",
                "rating": "9.1",
                "prices": [
                    {"site": "Booking.com", "price": "2 190"},
                    {"site": "Hotels.com", "price": "2 290"},
                    {"site": "Expedia", "price": "2 350"},
                    {"site": "Trivago", "price": "2 410"}
                ]
            },
            {
                "name": "Seaside Resort",
                "rating": "8.8",
                "prices": [
                    {"site": "Expedia", "price": "1 790"},
                    {"site": "Booking.com", "price": "1 850"},
                    {"site": "Hotels.com", "price": "1 920"},
                    {"site": "Trivago", "price": "1 990"}
                ]
            },
            {
                "name": "Boutique Hotel",
                "rating": "8.6",
                "prices": [
                    {"site": "Trivago", "price": "1 590"},
                    {"site": "Booking.com", "price": "1 650"},
                    {"site": "Expedia", "price": "1 690"},
                    {"site": "Hotels.com", "price": "1 750"}
                ]
            }
        ]

    return render_template_string(
        HTML,
        destination=destination,
        checkin=checkin,
        checkout=checkout,
        guests=guests,
        searched=searched,
        hotels=hotels
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
