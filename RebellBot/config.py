from tinkoff.invest import CandleInterval
from sklearn.ensemble import RandomForestClassifier

class Config:
    TELEGRAM_BOT_TOKEN = "7738863885:AAGAPk6D0KNFbyJtxmfhHvzTvutNouFeXhw"
    TINKOFF_TOKEN = "t.mK-hSWqrDY7AlwlWQB77zOnCsh8tkG9iCAZPUdUYOWzmXi670muhMl-jZOohsjQsHijBWi1DNV26ht6TvwbzCA"

    ML_SETTINGS = {
        "model_class": RandomForestClassifier,
        "model_params": {
            "n_estimators": 200,
            "max_depth": 5,
            "random_state": 42
        },
        "training_interval": CandleInterval.CANDLE_INTERVAL_HOUR,
        "training_days": 30,
        "features": ["ema", "rsi", "atr", "volume"],
        "retrain_hours": 6
    }

    # Streaming API
    STREAMING = {
        "ws_url": "wss://api-invest.tinkoff.ru/openapi/md/v1/md-openapi/ws",
        "depth": 10,
        "max_subscriptions": 50,
        "reconnect_timeout": 5
    }

    # Trading Parameters
    STRATEGY = {
        "short_term": {
            "interval": CandleInterval.CANDLE_INTERVAL_5_MIN,
            "candles_needed": 72,  # 6 часов данных
            "indicators": {
                "ema": 9,
                "sma": 20,
                "rsi": 14,
                "atr": 14
            },
            "ml_features": ["ema", "rsi", "atr", "volume"],
            "risk_multiplier": 1.2
        }
    }

    RISK_MANAGEMENT = {
        "max_daily_loss": 2.0,  # Максимальный дневной убыток в %
        "position_size": 1.5,  # Размер позиции в % от депозита
        "slippage": 0.1  # Проскальзывание в %
    }

    UI_SETTINGS = {
        "default_mode": "short_term",
        "short_term_name": "Краткосрочный (1 час)",
        "long_term_name": "Долгосрочный (1 день)",
        "risk_warning": "⚠️ Внимание: Торговля на бирже связана с рисками"
    }


    # System Settings
    CACHE_TTL = 300  # 5 минут
    MODEL_RETRAIN_INTERVAL = 6 * 3600  # Каждые 6 часов