"""Shop details and product list.

Edit this file to change the business details shown on every page and bill,
or to add / remove cement brands and iron sizes. Restart the app afterwards.
"""

BUSINESS = {
    "name": "SHIRIDI SAI",
    "caption_words": ["Trust", "Quality", "Reasonable Price"],
    "admin_name": "Bonam Kota Viswanadham",
    "location": "Kadali, Razole Mandal, Dr. B.R. Ambedkar Konaseema",
    "phone": "9849859417",
}

# Each category lists the products a customer can pick and the units they
# may order in. The first unit is the default.
CATALOG = {
    "cement": {
        "title": "Cement",
        "units": ["Bags"],
        "items": [
            "Maha",
            "Maha HD",
            "UltraTech",
            "Anjani Cement",
            "Ramco Cement",
        ],
    },
    "iron": {
        "title": "Iron",
        "units": ["Pieces", "Tons"],
        "items": [
            "TMT Bar 8 mm",
            "TMT Bar 10 mm",
            "TMT Bar 12 mm",
            "TMT Bar 16 mm",
            "TMT Bar 20 mm",
            "TMT Bar 25 mm",
        ],
    },
}
