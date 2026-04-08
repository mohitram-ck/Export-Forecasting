import os
from datetime import timedelta

from flask import Flask, render_template, session, redirect, url_for, jsonify, request
from flask_session import Session
from flask_cors import CORS

from auth import auth_bp, bcrypt
from database.db import init_db, get_db_connection
from database.models import (
    get_user_datasets,
    insert_dataset,
    get_dataset_by_id,
    insert_forecast_history,
    get_user_history,
    get_forecast_by_id,
    delete_forecast_by_id,
    delete_dataset_by_id,
)
from model.arima_model import run_arima_forecast
from model.lstm_model import run_lstm_forecast
from model.hybrid_model import run_hybrid_forecast

from werkzeug.utils import secure_filename
import pandas as pd
import json
import time


ALLOWED_EXTENSIONS = {"csv"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", "dev-secret-key-change-in-prod"
    )
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB upload limit
    app.config["UPLOAD_FOLDER"] = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "uploads"
    )

    # Session configuration (server-side)
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_PERMANENT"] = True
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
    Session(app)

    # Initialize bcrypt with this app
    bcrypt.init_app(app)

    # Basic CORS (kept simple; only same-origin calls expected in production)
    CORS(app, supports_credentials=True)

    # Initialise database
    init_db()

    # Blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")

    # ----------------------
    # Helpers
    # ----------------------

    def login_required(f):
        from functools import wraps

        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            return f(*args, **kwargs)

        return decorated

    app.login_required = login_required  # expose for blueprints if needed

    # ----------------------
    # Routes
    # ----------------------

    @app.route("/")
    def index():
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        notice = (
            "Note: Data resets on server redeploy. "
            "For persistent storage, use a managed database such as Render PostgreSQL."
        )
        return render_template(
            "dashboard.html", username=session.get("username"), notice=notice
        )

    @app.route("/api/health")
    def health():
        # Very small delay to help UI distinguish cold start vs live
        start = time.time()
        try:
            conn = get_db_connection()
            conn.execute("SELECT 1")
            conn.close()
            status = "ok"
        except Exception:
            status = "error"
        duration_ms = int((time.time() - start) * 1000)
        return jsonify({"status": status, "responseTimeMs": duration_ms})

    # --------- DATASETS ----------

    @app.route("/api/upload", methods=["POST"])
    @login_required
    def upload_dataset():
        if "file" not in request.files:
            return jsonify({"error": "No file part in request"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "Only .csv files are allowed"}), 400

        filename = secure_filename(file.filename)
        user_id = session["user_id"]

        # Save to uploads/{user_id}_{timestamp}_{filename}
        timestamp = int(time.time())
        stored_name = f"{user_id}_{timestamp}_{filename}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
        try:
            file.save(save_path)
        except Exception as e:
            return jsonify({"error": f"Could not save file: {e}"}), 500

        # Validate CSV with pandas
        try:
            df = pd.read_csv(save_path)
        except Exception:
            return jsonify({"error": "Unable to read CSV file. Check format."}), 400

        if df.shape[1] < 2:
            return (
                jsonify(
                    {
                        "error": "CSV must contain at least 2 columns: a date column and a numeric series."
                    }
                ),
                400,
            )

        if df.shape[0] < 24:
            return (
                jsonify({"error": "CSV must have at least 24 rows (2 years of data)."}),
                400,
            )

        # Try to detect a date column automatically
        date_col = None
        for col in df.columns:
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                non_null_ratio = parsed.notnull().mean()
                if non_null_ratio > 0.9:
                    date_col = col
                    df[col] = parsed
                    break
            except Exception:
                continue

        if date_col is None:
            return (
                jsonify({"error": "Could not automatically detect a date column."}),
                400,
            )

        # Choose first numeric column other than date
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        if not numeric_cols:
            return jsonify({"error": "No numeric value column detected in CSV."}), 400

        # Filter rows with valid dates
        df = df[df[date_col].notnull()]
        if df.empty:
            return jsonify({"error": "No valid date rows in CSV after parsing."}), 400

        row_count = int(len(df))
        min_date = df[date_col].min()
        max_date = df[date_col].max()
        date_range = f"{min_date.strftime('%b %Y')} - {max_date.strftime('%b %Y')}"

        dataset_id = insert_dataset(
            user_id=user_id,
            filename=filename,
            filepath=save_path,
            row_count=row_count,
            date_range=date_range,
        )

        return jsonify(
            {
                "dataset_id": dataset_id,
                "filename": filename,
                "row_count": row_count,
                "date_range": date_range,
                "message": "Upload successful",
            }
        )

    @app.route("/api/datasets", methods=["GET"])
    @login_required
    def list_datasets():
        user_id = session["user_id"]
        datasets = get_user_datasets(user_id)
        return jsonify(datasets)

    @app.route("/api/datasets/<int:dataset_id>", methods=["DELETE"])
    @login_required
    def delete_dataset(dataset_id):
        user_id = session["user_id"]
        filepath = delete_dataset_by_id(dataset_id, user_id)
        if filepath is None:
            return jsonify({"error": "Dataset not found"}), 404
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            # Ignore filesystem cleanup failures to keep DB state consistent.
            pass
        return jsonify({"message": "Dataset deleted"})

    # --------- FORECASTING ----------

    def _load_series_from_dataset(dataset_row):
        """Load a univariate time series from a dataset row, for forecasting."""
        df = pd.read_csv(dataset_row["filepath"])

        # detect date column again and sort
        date_col = None
        for col in df.columns:
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notnull().mean() > 0.9:
                    df[col] = parsed
                    date_col = col
                    break
            except Exception:
                continue

        if date_col is None:
            raise ValueError("Could not detect date column when loading dataset.")

        df = df[df[date_col].notnull()]
        df = df.sort_values(by=date_col)

        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        if not numeric_cols:
            raise ValueError("No numeric column found when loading dataset.")

        value_col = numeric_cols[0]
        dates = df[date_col].dt.strftime("%Y-%m-%d").tolist()
        values = df[value_col].astype(float).tolist()
        return dates, values, value_col

    def _default_sample_series():
        """Provide a default simple increasing monthly series."""
        import numpy as np
        from pandas import date_range

        idx = date_range("2014-01-01", periods=60, freq="ME")
        values = (np.linspace(100, 200, len(idx)) + np.random.normal(0, 3, len(idx)))
        dates = [d.strftime("%Y-%m-%d") for d in idx]
        return dates, values.tolist(), "SampleValue"

    @app.route("/forecast", methods=["POST"])
    @app.route("/api/forecast", methods=["POST"])
    @login_required
    def run_forecast():
        data = request.get_json() or {}
        model_name = (data.get("model") or "arima").lower()
        steps = int(data.get("steps") or 12)
        dataset_id = data.get("dataset_id")

        if steps < 3 or steps > 24:
            return jsonify({"error": "Steps must be between 3 and 24"}), 400

        try:
            if dataset_id:
                dataset = get_dataset_by_id(dataset_id, session["user_id"])
                if not dataset:
                    return jsonify({"error": "Dataset not found"}), 404
                dates, values, value_col = _load_series_from_dataset(dataset)
            else:
                dates, values, value_col = _default_sample_series()
        except Exception as e:
            return jsonify({"error": f"Failed to load dataset: {e}"}), 400

        # Run the chosen model
        try:
            if model_name == "lstm":
                result = run_lstm_forecast(dates, values, steps)
            elif model_name == "hybrid":
                result = run_hybrid_forecast(dates, values, steps)
            else:
                model_name = "arima"
                result = run_arima_forecast(dates, values, steps)
        except Exception as e:
            return jsonify({"error": f"Model failed: {e}"}), 500

        history_json = json.dumps(
            {"dates": result["forecast_dates"], "predicted": result["forecast_values"]}
        )

        history_id = insert_forecast_history(
            user_id=session["user_id"],
            dataset_id=dataset_id,
            model_used=model_name,
            steps=steps,
            mae=result["mae"],
            rmse=result["rmse"],
            mape=result["mape"],
            accuracy=result["accuracy"],
            forecast_json=history_json,
        )

        payload = {
            "history_id": history_id,
            "model": model_name,
            "steps": steps,
            "metric": {
                "mae": result["mae"],
                "rmse": result["rmse"],
                "mape": result["mape"],
                "accuracy": result["accuracy"],
            },
            "series": {
                "dates": dates,
                "values": values,
            },
            "forecast": {
                "dates": result["forecast_dates"],
                "values": result["forecast_values"],
                "lower": result.get("lower"),
                "upper": result.get("upper"),
            },
        }
        return jsonify(payload)

    @app.route("/api/history", methods=["GET"])
    @login_required
    def history_list():
        user_id = session["user_id"]
        records = get_user_history(user_id, limit=20)
        return jsonify(records)

    @app.route("/api/history/<int:history_id>", methods=["GET"])
    @login_required
    def history_detail(history_id):
        user_id = session["user_id"]
        record = get_forecast_by_id(history_id, user_id)
        if not record:
            return jsonify({"error": "Forecast history not found"}), 404
        try:
            record["forecast"] = json.loads(record["forecast_json"])
        except Exception:
            record["forecast"] = None
        return jsonify(record)

    @app.route("/api/history/<int:history_id>", methods=["DELETE"])
    @login_required
    def history_delete(history_id):
        user_id = session["user_id"]
        deleted = delete_forecast_by_id(history_id, user_id)
        if not deleted:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"message": "Deleted"})

    @app.route("/api/compare", methods=["GET"])
    @login_required
    def compare_models():
        dataset_id = request.args.get("dataset_id")
        steps = int(request.args.get("steps", 12))

        if steps < 3 or steps > 24:
            return jsonify({"error": "Steps must be between 3 and 24"}), 400

        try:
            if dataset_id:
                dataset = get_dataset_by_id(dataset_id, session["user_id"])
                if not dataset:
                    return jsonify({"error": "Dataset not found"}), 404
                dates, values, _ = _load_series_from_dataset(dataset)
            else:
                dates, values, _ = _default_sample_series()
        except Exception as e:
            return jsonify({"error": f"Failed to load dataset: {e}"}), 400

        results = {}
        try:
            results["arima"] = run_arima_forecast(dates, values, steps)
        except Exception as e:
            results["arima"] = {"error": str(e)}
        try:
            results["lstm"] = run_lstm_forecast(dates, values, steps)
        except Exception as e:
            results["lstm"] = {"error": str(e)}
        try:
            results["hybrid"] = run_hybrid_forecast(dates, values, steps)
        except Exception as e:
            results["hybrid"] = {"error": str(e)}

        summary = {}
        for name, res in results.items():
            if "error" in res:
                summary[name] = {"error": res["error"]}
            else:
                summary[name] = {
                    "mae": res["mae"],
                    "rmse": res["rmse"],
                    "mape": res["mape"],
                    "accuracy": res["accuracy"],
                }

        # Determine best model by lowest RMSE (if available)
        best_model = None
        best_rmse = None
        for name, res in summary.items():
            rmse = res.get("rmse")
            if rmse is not None:
                if best_rmse is None or rmse < best_rmse:
                    best_rmse = rmse
                    best_model = name

        return jsonify({"summary": summary, "best_model": best_model})

    @app.route("/api/data", methods=["GET"])
    @login_required
    def get_data():
        dataset_id = request.args.get("dataset_id")
        try:
            if dataset_id:
                dataset = get_dataset_by_id(dataset_id, session["user_id"])
                if not dataset:
                    return jsonify({"error": "Dataset not found"}), 404
                dates, values, value_col = _load_series_from_dataset(dataset)
                return jsonify(
                    {
                        "source": "dataset",
                        "dataset_id": int(dataset_id),
                        "series_name": value_col,
                        "dates": dates,
                        "values": values,
                    }
                )
            dates, values, value_col = _default_sample_series()
            return jsonify(
                {
                    "source": "sample",
                    "series_name": value_col,
                    "dates": dates,
                    "values": values,
                }
            )
        except Exception as e:
            return jsonify({"error": f"Failed to load data: {e}"}), 400

    return app

# Expose module-level app for WSGI servers that import `app:app`.
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

