from typing import List, Dict, Any

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from sklearn.metrics import mean_absolute_error, mean_squared_error


def _compute_metrics(true_vals: List[float], pred_vals: List[float]) -> Dict[str, float]:
    true_arr = np.array(true_vals)
    pred_arr = np.array(pred_vals)
    mae = float(mean_absolute_error(true_arr, pred_arr))
    rmse = float(np.sqrt(mean_squared_error(true_arr, pred_arr)))
    mape = float(np.mean(np.abs((true_arr - pred_arr) / np.maximum(true_arr, 1e-6))) * 100)
    # Simple accuracy proxy based on relative error
    accuracy = float(max(0.0, 100.0 - mape))
    return {"mae": mae, "rmse": rmse, "mape": mape, "accuracy": accuracy}


def run_arima_forecast(
    dates: List[str],
    values: List[float],
    steps: int,
) -> Dict[str, Any]:
    """
    Basic ARIMA(1,1,1) forecast for demonstration.
    Uses last part of history as pseudo-test window to compute metrics.
    """
    series = pd.Series(values)

    # Simple differencing and ARIMA(1,1,1)
    model = ARIMA(series, order=(1, 1, 1))
    fitted = model.fit()

    forecast_res = fitted.get_forecast(steps=steps)
    forecast_values = forecast_res.predicted_mean.tolist()
    conf_int = forecast_res.conf_int(alpha=0.2)  # 80% interval for chart
    lower = conf_int.iloc[:, 0].tolist()
    upper = conf_int.iloc[:, 1].tolist()

    # Metrics: compare last `steps` of history vs model's one-step-ahead predictions
    if len(series) > steps:
        train = series.iloc[:-steps]
        test = series.iloc[-steps:]
        model_backtest = ARIMA(train, order=(1, 1, 1))
        fitted_backtest = model_backtest.fit()
        backtest_forecast = fitted_backtest.forecast(steps=steps).tolist()
        metrics = _compute_metrics(test.tolist(), backtest_forecast)
    else:
        metrics = {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "accuracy": 0.0}

    # Build forecast date labels extending from last history date
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

