# """Forecast service utilities"""
import datetime
import psycopg
from database.db_connection import get_connection
from .guard import ensure_test_db

class StaleForecastError(RuntimeError):
    """Raised when the latest sales data is older than the allowed freshness period."""
    pass

def generate_forecast(forecast_horizon_days: int = 30) -> dict:
    """Generate a simple demand forecast.

    The implementation is placeholder: it returns the total quantity sold in the
    most recent sales period and projects it forward. The key requirement is the
    freshness check – if the latest sales date is more than 30 days old the
    function raises :class:`StaleForecastError`.
    """
    conn = get_connection()
    ensure_test_db(conn)
    with conn.cursor() as cur:
        # Find the most recent sales date
        cur.execute("SELECT MAX(date) FROM sales")
        latest_date = cur.fetchone()[0]
        if latest_date is None:
            raise RuntimeError("No sales data available for forecasting")
        today = datetime.date.today()
        if (today - latest_date).days > 30:
            raise StaleForecastError(
                f"Latest sales date {latest_date} is older than 30 days"
            )
        # Simple total quantity as a naive forecast
        cur.execute("SELECT SUM(quantity) FROM sales")
        total_qty = cur.fetchone()[0] or 0
        forecast_date = today + datetime.timedelta(days=forecast_horizon_days)
        result = {
            "forecast_date": forecast_date.isoformat(),
            "projected_quantity": total_qty,
            "latest_sales_date": latest_date.isoformat(),
        }
    conn.commit()
    conn.close()
    return result
