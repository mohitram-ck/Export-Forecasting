from typing import List, Dict, Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense


def _create_sequences(data, look_back: int = 12):
    X, y = [], []
    for i in range(len(data) - look_back):
        X.append(data[i : i + look_back])
        y.append(data[i + look_back])
    return np.array(X), np.array(y)


def _compute_metrics(true_vals: List[float], pred_vals: List[float]) -> Dict[str, float]:
    true_arr = np.array(true_vals)
    pred_arr = np.array(pred_vals)
    mae = float(mean_absolute_error(true_arr, pred_arr))
    rmse = float(np.sqrt(mean_squared_error(true_arr, pred_arr)))
    mape = float(np.mean(np.abs((true_arr - pred_arr) / np.maximum(true_arr, 1e-6))) * 100)
    accuracy = float(max(0.0, 100.0 - mape))
    return {"mae": mae, "rmse": rmse, "mape": mape, "accuracy": accuracy}


def run_lstm_forecast(
    dates: List[str],
    values: List[float],
    steps: int,
) -> Dict[str, Any]:
    """
    Lightweight LSTM model for educational/demo purposes.
    Not heavily tuned to keep Render build/run fast.
    """
    series = np.array(values, dtype="float32").reshape(-1, 1)
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(series)

    look_back = 12
    if len(scaled) <= look_back + steps:
        # Fallback: if not enough data, just repeat last value
        last_val = float(series[-1][0])
        forecast_values = [last_val] * steps
        metrics = {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "accuracy": 0.0}
    else:
        X, y = _create_sequences(scaled, look_back=look_back)
        # Use last part of sequences as a validation window
        split_idx = max(len(X) - steps, 1)
        X_train, y_train = X[:split_idx], y[:split_idx]
        X_test, y_test = X[split_idx:], y[split_idx:]

        X_train = X_train.reshape((X_train.shape[0], X_train.shape[1], 1))
        X_test = X_test.reshape((X_test.shape[0], X_test.shape[1], 1))

        model = Sequential()
        model.add(LSTM(32, input_shape=(look_back, 1)))
        model.add(Dense(1))
        model.compile(loss="mse", optimizer="adam")
        model.fit(
            X_train,
            y_train,
            epochs=10,
            batch_size=8,
            verbose=0,
        )

        # Backtest metrics
        if len(X_test) > 0:
            y_pred_test = model.predict(X_test, verbose=0)
            y_test_inv = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()
            y_pred_inv = scaler.inverse_transform(y_pred_test).flatten()
            metrics = _compute_metrics(y_test_inv.tolist(), y_pred_inv.tolist())
        else:
            metrics = {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "accuracy": 0.0}

        # Multi-step forecast using last look_back window
        last_window = scaled[-look_back:].reshape((1, look_back, 1))
        forecast_scaled = []
        current_window = last_window.copy()
        for _ in range(steps):
            next_scaled = model.predict(current_window, verbose=0)[0, 0]
            forecast_scaled.append(next_scaled)
            current_window = np.roll(current_window, -1, axis=1)
            current_window[0, -1, 0] = next_scaled

        forecast_scaled = np.array(forecast_scaled).reshape(-1, 1)
        forecast_values = scaler.inverse_transform(forecast_scaled).flatten().tolist()

    # Dummy bounds as +/- 10% for chart purposes
    forecast_arr = np.array(forecast_values)
    lower = (forecast_arr * 0.9).tolist()
    upper = (forecast_arr * 1.1).tolist()

    start_date = pd.to_datetime(dates[-1])
    forecast_idx = pd.date_range(start_date, periods=steps + 1, freq="ME")[1:]
    forecast_dates = [d.strftime("%Y-%m-%d") for d in forecast_idx]

    return {
        "forecast_dates": forecast_dates,
        "forecast_values": forecast_values,
        "lower": lower,
        "upper": upper,
        **metrics,
    }

