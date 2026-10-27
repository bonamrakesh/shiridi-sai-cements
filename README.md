# Shiridi Sai Cements – Online Cement & Iron Booking

Customers book cement and iron without signing in. The admin logs in, enters the
prices and approves the bill. Until then the customer sees
**"Wait please! Prices are calculated by the admin"**. All data is stored in a
SQLite database (`instance/shiridi_sai.db`).

## Folder structure

```
shiridi-sai-cements/
├── app.py                  Backend: pages, database, admin login, pricing
├── shop_config.py          Business details + cement brands + iron sizes (edit here)
├── requirements.txt        Python packages (Flask)
├── instance/               Created automatically: database + secret key
├── static/
│   ├── css/style.css       All styling
│   ├── js/main.js          Customer booking page
│   ├── js/order.js         Bill page (auto-updates when admin approves)
│   ├── js/admin.js         Admin pricing, approve/reject
│   ├── js/splash.js        Opening logo screen
│   └── images/             logo.png, favicon.png
├── templates/              HTML pages (Jinja)
│   ├── base.html  index.html  order.html  _bill.html  _footer.html  error.html
│   └── admin_base.html  admin_login.html  admin_dashboard.html
│       admin_order.html  admin_settings.html
└── .vscode/                Recommended extensions and debug settings
```

## Run it (Windows, VS Code terminal)

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000  
Admin: http://127.0.0.1:5000/admin/login

**First login:** username `admin`, password `admin@123`.
Change it straight away under **Admin → Settings**.

To open it on a phone on the same Wi-Fi: `set HOST=0.0.0.0` then `python app.py`,
and visit `http://<your-computer-ip>:5000`.

## VS Code extensions

Install the Python and Jinja ones at least (VS Code will also suggest them when you open the folder):

| Extension | Why |
|---|---|
| Python (ms-python.python) | Run and debug the app |
| Pylance (ms-python.vscode-pylance) | Code hints |
| Better Jinja (samuelcolvin.jinjahtml) | Colours the `templates/*.html` files |
| SQLite Viewer (qwtel.sqlite-viewer) | Open `instance/shiridi_sai.db` and see stored orders |
| Prettier (esbenp.prettier-vscode) | Optional, tidy formatting |

## Product pictures

The Cement and Iron cards show drawings by default. To use your own photos, put them in
`static/images/products/` named after the product (for example `ultratech.jpg`, `tmt-bar-12-mm.jpg`);
see the `README.txt` in that folder for all the names. Photos for the big Cement / Iron cards go in
`static/images/` as `cement.jpg` and `iron.jpg`. No code change is needed. After uploading, press Reload
on PythonAnywhere and Ctrl+F5 in your browser.

## Changing things

* Brands, iron sizes, shop name, address, phone: edit `shop_config.py`, restart.
* Logo: replace `static/images/logo.png` (and `favicon.png`).
* Colours: top of `static/css/style.css`.

## Going live (so customers can use it from anywhere)

Run it on a host such as PythonAnywhere, Render or a VPS. For a real server:
set `SECRET_KEY`, `HTTPS_ONLY=1`, run with `gunicorn app:app`, and keep the
`instance/` folder backed up (it holds all orders). The "Send link on WhatsApp"
button in the admin order page lets you tell a customer their bill is ready.
