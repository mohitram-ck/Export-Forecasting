from typing import List, Optional, Dict, Any

from .db import get_db_connection


def insert_user(username: str, email: str, password_hash: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, password_hash),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def insert_dataset(
    user_id: int, filename: str, filepath: str, row_count: int, date_range: str
) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO datasets (user_id, filename, filepath, row_count, date_range)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, filename, filepath, row_count, date_range),
    )
    conn.commit()
    dataset_id = cursor.lastrowid
    conn.close()
    return dataset_id


def get_user_datasets(user_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, filename, row_count, date_range, uploaded_at
        FROM datasets
        WHERE user_id = ?
        ORDER BY uploaded_at DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dataset_by_id(dataset_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM datasets
        WHERE id = ? AND user_id = ?
        """,
        (dataset_id, user_id),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_dataset_by_id(dataset_id: int, user_id: int) -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT filepath FROM datasets WHERE id = ? AND user_id = ?",
        (dataset_id, user_id),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    filepath = row["filepath"]
    cursor.execute(
        "DELETE FROM datasets WHERE id = ? AND user_id = ?",
        (dataset_id, user_id),
    )
    conn.commit()
    conn.close()
    return filepath


def insert_forecast_history(
    user_id: int,
    dataset_id: int,
    model_used: str,
    steps: int,
    mae: float,
    rmse: float,
    mape: float,
    accuracy: float,
    forecast_json: str,
) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO forecast_history
        (user_id, dataset_id, model_used, steps, mae, rmse, mape, accuracy, forecast_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, dataset_id, model_used, steps, mae, rmse, mape, accuracy, forecast_json),
    )
    conn.commit()
    history_id = cursor.lastrowid
    conn.close()
    return history_id


def get_user_history(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT fh.id,
               fh.model_used,
               fh.steps,
               fh.mae,
               fh.rmse,
               fh.mape,
               fh.accuracy,
               fh.created_at,
               d.filename AS dataset_name
        FROM forecast_history fh
        LEFT JOIN datasets d ON fh.dataset_id = d.id
        WHERE fh.user_id = ?
        ORDER BY fh.created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_forecast_by_id(history_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT fh.*, d.filename AS dataset_name
        FROM forecast_history fh
        LEFT JOIN datasets d ON fh.dataset_id = d.id
        WHERE fh.id = ? AND fh.user_id = ?
        """,
        (history_id, user_id),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_forecast_by_id(history_id: int, user_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM forecast_history WHERE id = ? AND user_id = ?",
        (history_id, user_id),
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

