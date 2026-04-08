# Export Forecasting using ARIMA and LSTM

A full-stack Flask web application for **export time series forecasting** using **ARIMA**, **LSTM**, and a **Hybrid ARIMA+LSTM** model.  
Users can register/login, upload monthly export CSV files, run forecasts, view interactive charts (Chart.js), and inspect forecast history.

## Features

- **User Authentication**
  - Register/login/logout using bcrypt-hashed passwords
  - Server-side sessions (Flask-Session)

- **Dataset Management**
  - Upload CSV files (max 5MB) with a date column and one numeric series
  - Automatic date column detection and basic validation
  - Stores metadata: row count and date range

- **Forecasting Models**
  - **ARIMA**: classical time series forecasting
  - **LSTM**: recurrent neural network for sequence prediction
  - **Hybrid**: average of ARIMA and LSTM forecasts and metrics

- **Metrics & Visualisation**
  - MAE, RMSE, MAPE, and Accuracy
  - Main Chart.js line chart with historical vs forecast values
  - Model comparison view with RMSE bar chart

- **Forecast History**
  - Stores latest forecasts per user in SQLite
  - History table with model, dataset, horizon, and metrics
  - Reload forecast chart from stored JSON
  - Delete individual history records

## Project Structure

See the `export_forecasting/` structure in this repository (matches the specification: `app.py`, `wsgi.py`, `database/`, `auth/`, `model/`, `templates/`, `static/`, `uploads/`, `saved_models/`, etc.).

## Local Setup

1. **Clone and create virtual environment (recommended)**:

```bash
cd export_forecasting
python -m venv venv
venv\Scripts\activate  # on Windows
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Run the app locally**:

```bash
python wsgi.py
```

4. Open the app in your browser:

- Navigate to `http://localhost:5000`
- Register a new user, login, upload CSVs, and start forecasting.

## Deploying on Render.com

1. **Push to GitHub**
   - Create a new GitHub repository and push this project.

2. **Create a new Web Service**
   - Go to [Render](https://render.com) and click **New &rarr; Web Service**.
   - Connect your GitHub repository.

3. **Configure build and start commands**
   - Build command:

     ```bash
     pip install -r requirements.txt
     ```

   - Start command:

     ```bash
     gunicorn wsgi:app
     ```

   (These are already set in `render.yaml`, which Render can auto-detect.)

4. **Environment variables**
   - Add `SECRET_KEY` (any strong random string) in the Render **Environment** tab,
     or let Render generate it based on `render.yaml`.

5. **Deploy**
   - Click **Create Web Service**. Render will install dependencies, build, and start the app.
   - Once live, open the public URL and use it directly in any browser (no localhost references).

> **Note:** On the Render free tier, **cold starts** may take **30–60 seconds** for the first request after idle time.  
> The UI includes a small message (“Server is waking up...”) when the `/api/health` endpoint responds slowly.

## Persistence Notes (Render Free Tier)

- SQLite database (`database/app.db`) is stored on **ephemeral disk**.
  - **Data (users, datasets, history) will reset on redeploy** or container restart.
  - The dashboard also displays a notice: “Data resets on server redeploy.”
- For production-ready persistence:
  - Use **Render PostgreSQL** (free for 90 days), and adapt the DB layer to use PostgreSQL instead of SQLite.

## Academic Presentation Notes

- **Backend Stack**: Python 3.10, Flask, Gunicorn, SQLite.
- **Frontend Stack**: HTML5, CSS3, vanilla JavaScript, Chart.js.
- **Machine Learning**:
  - ARIMA via `statsmodels`
  - LSTM via `tensorflow-cpu` + `keras`
  - Hybrid model combining ARIMA and LSTM forecasts.
- **Security**:
  - Bcrypt password hashing (`flask-bcrypt`)
  - Server-side session management (`flask-session`)
  - Per-user access control for datasets and forecast history.

