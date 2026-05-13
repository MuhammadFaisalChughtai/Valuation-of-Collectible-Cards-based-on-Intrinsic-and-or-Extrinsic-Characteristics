# Valuation of collectible cards based on intrinsic and or extrinsic characteristics

## Run

From the project root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install pandas pytrends playwright mysql-connector-python
python -m playwright install chromium
```

Run one of these scripts:

```bash
python trends_extractor.py
python data_scraper.py
```

`data_scraper.py` expects MySQL to be running.

## Database setup (Docker)

Before starting Docker, rename the env example file to `.env`.

From the project root:

```bash
mv .env..example .env
```

Then start the database from the `docker` folder:

```bash
cd docker
docker compose up -d
```
