import logging
import asyncio
import websockets
import json
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from tinkoff.invest import (
    Client, CandleInterval, HistoricCandle,
    Quotation, InstrumentStatus, OrderBook
)
from tinkoff.invest.utils import now
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class MarketDataService:
    """Сервис для работы с рыночными данными"""

    def __init__(self):
        self.client = Client(Config.TINKOFF_TOKEN)
        self.orderbooks = {}
        self.candles_cache = {}
        self.subscriptions = set()
        self.lock = asyncio.Lock()
        self.ws = None

    async def start_streaming(self):
        """Запуск потоковых данных"""
        while True:
            try:
                async with websockets.connect(
                        Config.STREAMING["ws_url"],
                        extra_headers={"Authorization": f"Bearer {Config.TINKOFF_TOKEN}"}
                ) as ws:
                    self.ws = ws
                    await self._resubscribe()
                    await self._stream_handler()
            except Exception as e:
                logger.error(f"Ошибка подключения: {str(e)}")
                await asyncio.sleep(Config.STREAMING["reconnect_timeout"])

    async def _resubscribe(self):
        """Восстановление подписок"""
        for figi in self.subscriptions:
            await self.ws.send(json.dumps({
                "event": "orderbook:subscribe",
                "figi": figi,
                "depth": Config.STREAMING["depth"]
            }))

    async def _stream_handler(self):
        """Обработчик потоковых данных"""
        async for message in self.ws:
            data = json.loads(message)
            if data["event"] == "orderbook":
                await self._process_orderbook(data["payload"])

    async def _process_orderbook(self, data: dict):
        """Обновление стакана котировок"""
        async with self.lock:
            self.orderbooks[data["figi"]] = {
                "bids": [(l.price.units + l.price.nano / 1e9, l.quantity)
                         for l in data["bids"]],
                "asks": [(l.price.units + l.price.nano / 1e9, l.quantity)
                         for l in data["asks"]],
                "timestamp": datetime.now()
            }

    async def subscribe(self, figi: str):
        """Подписка на инструмент"""
        if figi not in self.subscriptions:
            self.subscriptions.add(figi)
            if self.ws:
                await self.ws.send(json.dumps({
                    "event": "orderbook:subscribe",
                    "figi": figi,
                    "depth": Config.STREAMING["depth"]
                }))

    async def get_historical_candles(self, figi: str, days: int, interval: CandleInterval) -> List[HistoricCandle]:
        """Получение исторических свечей"""
        return self.client.market_data.get_candles(
            figi=figi,
            from_=now() - timedelta(days=days),
            to=now(),
            interval=interval
        ).candles

    async def get_instruments(self) -> List[Dict]:
        """Получение списка инструментов"""
        shares = self.client.instruments.shares(instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE).instruments
        return [{
            "figi": item.figi,
            "ticker": item.ticker,
            "name": item.name,
            "type": "акция"
        } for item in shares]


class TradingEngine:
    """Движок торговой логики"""

    def __init__(self):
        self.market = MarketDataService()
        self.ml_model = None
        self.last_trained = None
        self.positions = {}
        asyncio.create_task(self._init_ml())

    async def _init_ml(self):
        """Инициализация ML-модели"""
        await self.train_model()
        while True:
            await asyncio.sleep(Config.ML_SETTINGS["retrain_hours"] * 3600)
            await self.train_model()

    async def train_model(self):
        """Обучение ML-модели"""
        try:
            logger.info("🔄 Начало обучения модели...")
            instruments = await self.market.get_instruments()[:5]
            data = []

            for instr in instruments:
                candles = await self.market.get_historical_candles(
                    instr["figi"],
                    Config.ML_SETTINGS["training_days"],
                    Config.ML_SETTINGS["training_interval"]
                )
                df = self._prepare_training_data(candles)
                data.append(df)

            full_data = pd.concat(data)
            X = full_data[Config.ML_SETTINGS["features"]]
            y = full_data["target"]

            self.ml_model = Config.ML_SETTINGS["model_class"](
                **Config.ML_SETTINGS["model_params"]
            )
            self.ml_model.fit(X, y)
            self.last_trained = datetime.now()
            logger.info(f"✅ Модель обучена. Точность: {self.ml_model.score(X, y):.2%}")

        except Exception as e:
            logger.error(f"❌ Ошибка обучения: {str(e)}")

    def _prepare_training_data(self, candles: List[HistoricCandle]) -> pd.DataFrame:
        """Подготовка данных для обучения"""
        df = pd.DataFrame([{
            "open": self._convert_quotation(c.open),
            "high": self._convert_quotation(c.high),
            "low": self._convert_quotation(c.low),
            "close": self._convert_quotation(c.close),
            "volume": c.volume
        } for c in candles])

        df["ema"] = ta.ema(df["close"], length=9)
        df["rsi"] = ta.rsi(df["close"], length=14)
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["target"] = (df["close"].shift(-1) > df["close"]).astype(int)
        df.dropna(inplace=True)
        return df

    async def analyze(self, ticker: str, mode: str = "short_term") -> Dict:
        """Полный анализ инструмента"""
        try:
            # Поиск инструмента по тикеру
            instruments = await self.market.get_instruments()
            instrument = next(i for i in instruments if i["ticker"] == ticker.upper())

            # Получение данных
            params = Config.STRATEGY_PARAMS[mode]
            candles = await self.market.get_historical_candles(
                instrument["figi"],
                params["days"],
                params["interval"]
            )

            if len(candles) < params["min_candles"]:
                raise ValueError("Недостаточно данных")

            # Технический анализ
            analysis = self._technical_analysis(candles, params)

            # ML-анализ
            if self.ml_model:
                features = {
                    "ema": analysis["ema"],
                    "rsi": analysis["rsi"],
                    "atr": analysis["atr"],
                    "volume": candles[-1].volume
                }
                ml_pred = self.ml_model.predict([[features[k] for k in Config.ML_SETTINGS["features"]]])[0]
                analysis["ml_confidence"] = \
                self.ml_model.predict_proba([[features[k] for k in Config.ML_SETTINGS["features"]]])[0][1] * 100
                analysis["decision"] = "Покупать" if ml_pred == 1 else "Продавать"

            # Формирование результата
            return {
                "ticker": ticker.upper(),
                "decision": analysis["decision"],
                "confidence": analysis.get("ml_confidence", 0),
                "price": self._convert_quotation(candles[-1].close),
                "stop_loss": analysis["stop_loss"],
                "take_profit": analysis["take_profit"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
            }

        except Exception as e:
            logger.error(f"Ошибка анализа: {str(e)}")
            return {"error": str(e)}

    def _technical_analysis(self, candles: List[HistoricCandle], params: Dict) -> Dict:
        """Технический анализ"""
        closes = [self._convert_quotation(c.close) for c in candles]
        highs = [self._convert_quotation(c.high) for c in candles]
        lows = [self._convert_quotation(c.low) for c in candles]

        analysis = {
            "ema": ta.ema(pd.Series(closes), length=params["ema"]).iloc[-1],
            "rsi": ta.rsi(pd.Series(closes), length=params["rsi"]).iloc[-1],
            "atr": ta.atr(pd.Series(highs), pd.Series(lows), pd.Series(closes), length=params["atr"]).iloc[-1],
            "decision": "Держать",
            "stop_loss": 0.0,
            "take_profit": 0.0
        }

        # Расчет уровней
        last_price = closes[-1]
        analysis["stop_loss"] = last_price - analysis["atr"] * Config.RISK_MANAGEMENT["stop_loss_multiplier"]
        analysis["take_profit"] = last_price + analysis["atr"] * Config.RISK_MANAGEMENT["take_profit_multiplier"]

        return analysis

    async def get_top_instruments(self) -> List[Dict]:
        """Топ-5 инструментов по объему"""
        instruments = await self.market.get_instruments()
        return sorted(
            instruments,
            key=lambda x: x.get("volume", 0),
            reverse=True
        )[:5]

    def _convert_quotation(self, q: Quotation) -> float:
        """Конвертация Quotation в float"""
        return q.units + q.nano / 1e9