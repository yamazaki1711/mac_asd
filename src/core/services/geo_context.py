"""
ASD v12.0 — Geo Context Service.

Контекстное обогащение строительного объекта:
  1. Геокодинг адреса → координаты (Nominatim / OpenStreetMap, полностью бесплатно)
  2. Погода на период строительства (Open-Meteo, полностью бесплатно)
  3. Часовой пояс (расчётный по координатам)
  4. Климатический район по СП 131.13330.2020
  5. Карта объекта (URL OpenStreetMap / Nominatim)

API keys:
  - Ни одного! Всё работает на открытых данных.

Usage:
    from src.core.services.geo_context import GeoContextService

    svc = GeoContextService()
    ctx = await svc.enrich("г. Новосибирск, ул. Станционная, 30а")
    # ctx.lat, ctx.lon, ctx.weather_summary, ctx.timezone, ctx.climate_zone
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Nominatim требует User-Agent (политика использования)
NOMINATIM_HEADERS = {
    "User-Agent": "MAC_ASD/12.0 (construction document automation; oleg@asd.local)",
}

# Rate limit: Nominatim просит не больше 1 запроса в секунду
_LAST_NOMINATIM_CALL = 0.0


# ══════════════════════════════════════════════════════════════════
# Climate zones (СП 131.13330.2020 — приложение А)
# Approximated by latitude bands for European Russia / Siberia
# ══════════════════════════════════════════════════════════════════

CLIMATE_ZONES = [
    # (lat_min, lat_max, lon_min, lon_max, zone_code, description)
    (66.0, 90.0, 20.0, 180.0, "IA", "Особый (арктическое побережье)"),
    (62.0, 66.0, 20.0, 180.0, "IБ", "IБ (север Якутии, север Красноярского края)"),
    (58.0, 62.0, 30.0, 180.0, "IВ", "IВ (средняя полоса Сибири)"),
    (56.0, 58.0, 30.0, 180.0, "IГ", "IГ (юг Сибири, север Урала)"),
    (54.0, 56.0, 30.0, 120.0, "IД", "IД (Омск, Новосибирск, Красноярск)"),
    (52.0, 54.0, 30.0, 120.0, "IIА", "IIА (юг Западной Сибири)"),
    (50.0, 52.0, 30.0, 60.0, "IIБ", "IIБ (Саратов, Оренбург)"),
    (48.0, 50.0, 30.0, 60.0, "IIВ", "IIВ (Волгоград, Ростов-на-Дону)"),
    (44.0, 48.0, 30.0, 60.0, "IIIА", "IIIА (Краснодар, Ставрополь)"),
    (42.0, 44.0, 30.0, 60.0, "IIIБ", "IIIБ (юг Краснодарского края)"),
    (54.0, 60.0, 20.0, 30.0, "IIБ", "IIБ (Москва, Санкт-Петербург)"),
]


# ══════════════════════════════════════════════════════════════════
# Data classes
# ══════════════════════════════════════════════════════════════════

@dataclass
class GeoLocation:
    """Результат геокодинга."""
    address: str
    lat: float
    lon: float
    precision: str = ""            # exact, street, city, etc.
    country: str = ""
    region: str = ""               # Субъект РФ
    city: str = ""
    street: str = ""
    house: str = ""
    postal_code: str = ""
    raw_response: Dict = field(default_factory=dict)


@dataclass
class WeatherDay:
    """Погода за один день."""
    date: date
    temp_min_c: float = None
    temp_max_c: float = None
    temp_avg_c: float = None
    precipitation_mm: float = 0
    wind_speed_max_ms: float = 0
    wind_direction_dominant: int = 0
    snow_depth_cm: float = 0


@dataclass
class WeatherSummary:
    """Сводка погоды за период строительства."""
    start_date: date
    end_date: date
    days_total: int
    days_with_precipitation: int = 0
    days_below_minus_5: int = 0    # Дни с t < -5°C (зимнее бетонирование)
    days_above_25: int = 0          # Дни с t > +25°C (жара)
    temp_min: float = 100
    temp_max: float = -100
    total_precipitation_mm: float = 0
    max_wind_ms: float = 0
    days_strong_wind: int = 0       # Ветер > 12 м/с (ограничение крановых работ)
    daily: List[WeatherDay] = field(default_factory=list)
    summary_text: str = ""


@dataclass
class GeoContext:
    """Полный гео-контекст объекта."""
    location: GeoLocation
    weather: Optional[WeatherSummary] = None
    timezone: str = "Asia/Novosibirsk"
    climate_zone_code: str = ""
    climate_zone_desc: str = ""
    osm_map_url: str = ""
    sunrise_sunset_note: str = ""    # для заполнения ОЖР


# ══════════════════════════════════════════════════════════════════
# Geo Context Service
# ══════════════════════════════════════════════════════════════════

class GeoContextService:
    """
    Сервис гео-контекстного обогащения строительного объекта.

    Полностью бесплатные источники (ни одного API-ключа):
      - Nominatim / OpenStreetMap: адрес → координаты
      - Open-Meteo: погода историческая + прогноз
    """

    def __init__(self):
        pass

    # ── Public API ───────────────────────────────────────────

    async def enrich(
        self,
        address: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> GeoContext:
        """
        Получить полный гео-контекст объекта по адресу.

        Args:
            address: Адрес объекта (например, «г. Новосибирск, ул. Станционная, 30а»)
            start_date: Начало строительства (для погоды)
            end_date: Окончание строительства

        Returns:
            GeoContext с координатами, погодой, часовым поясом, климатическим районом
        """
        # 1. Геокодинг
        location = await self.geocode(address)

        # 2. Часовой пояс
        timezone = self._approx_timezone(location.lat, location.lon)

        # 3. Климатический район
        zone_code, zone_desc = self._climate_zone(location.lat, location.lon)

        # 4. Карта
        map_url = f"https://www.openstreetmap.org/?mlat={location.lat}&mlon={location.lon}&zoom=16&layers=M"

        # 5. Погода (если заданы даты)
        weather = None
        if start_date and end_date:
            weather = await self.get_weather(
                location.lat, location.lon,
                start_date, end_date,
            )

        # 6. Восход/заход (приблизительно)
        sunrise_note = self._sunrise_sunset_note(location.lat, start_date or date.today())

        return GeoContext(
            location=location,
            weather=weather,
            timezone=timezone,
            climate_zone_code=zone_code,
            climate_zone_desc=zone_desc,
            osm_map_url=map_url,
            sunrise_sunset_note=sunrise_note,
        )

    # ── Geocoding ────────────────────────────────────────────

    async def geocode(self, address: str) -> GeoLocation:
        """
        Геокодировать адрес через Nominatim (OpenStreetMap).

        Полностью бесплатно, без API-ключа.
        Политика использования: макс 1 запрос/сек, обязательный User-Agent.

        Точность для РФ: отличная — города, улицы, дома.
        """
        # Rate limiting — не чаще 1 запроса в секунду
        global _LAST_NOMINATIM_CALL
        elapsed = time.time() - _LAST_NOMINATIM_CALL
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        _LAST_NOMINATIM_CALL = time.time()

        try:
            async with httpx.AsyncClient(timeout=10, headers=NOMINATIM_HEADERS) as client:
                resp = await client.get(
                    NOMINATIM_URL,
                    params={
                        "q": address,
                        "format": "json",
                        "limit": 1,
                        "accept-language": "ru",
                        "addressdetails": 1,
                    },
                )

            if resp.status_code != 200:
                logger.error("Nominatim error: %d — %s", resp.status_code, resp.text[:200])
                return GeoLocation(address=address, lat=0, lon=0, precision="api_error")

            data = resp.json()
            if not data:
                logger.warning("Nominatim: address not found — %s", address)
                return GeoLocation(address=address, lat=0, lon=0, precision="not_found")

            item = data[0]
            lat = round(float(item["lat"]), 6)
            lon = round(float(item["lon"]), 6)

            # Parse address components from Nominatim
            addr = item.get("address", {})
            precision = item.get("type", "unknown")  # house, street, city, etc.

            # Map Nominatim keys to our fields
            region = addr.get("state", "") or addr.get("region", "")
            city = addr.get("city", "") or addr.get("town", "") or addr.get("village", "")
            street = addr.get("road", "") or addr.get("street", "")
            house = addr.get("house_number", "")

            loc = GeoLocation(
                address=address,
                lat=lat,
                lon=lon,
                precision=precision,
                country=addr.get("country", ""),
                region=region,
                city=city,
                street=street,
                house=house,
                postal_code=addr.get("postcode", ""),
                raw_response=item,
            )

            logger.info(
                "Geocoded (OSM): %s → %.4f, %.4f (%s)",
                address, loc.lat, loc.lon, precision,
            )
            return loc

        except Exception as e:
            logger.error("Geocoding failed: %s", e)
            return GeoLocation(address=address, lat=0, lon=0, precision="error")

    # ── Weather ──────────────────────────────────────────────

    async def get_weather(
        self,
        lat: float,
        lon: float,
        start: date,
        end: date,
    ) -> WeatherSummary:
        """
        Получить погоду на период строительства через Open-Meteo.

        Open-Meteo — полностью бесплатный сервис, без API-ключа.
        Источник данных: ERA5 (глобальный климатический реанализ).
        """
        summary = WeatherSummary(start_date=start, end_date=end, days_total=0)
        daily: List[WeatherDay] = []

        # Если даты в будущем — используем forecast, иначе archive
        today = date.today()
        use_forecast = start > today

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    OPEN_METEO_FORECAST_URL if use_forecast else OPEN_METEO_ARCHIVE_URL,
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "start_date": start.isoformat(),
                        "end_date": min(end, today).isoformat() if not use_forecast else end.isoformat(),
                        "daily": [
                            "temperature_2m_min",
                            "temperature_2m_max",
                            "temperature_2m_mean",
                            "precipitation_sum",
                            "wind_speed_10m_max",
                            "wind_direction_10m_dominant",
                            "snow_depth_mean",
                        ],
                        "timezone": "auto",
                        "wind_speed_unit": "ms",
                    },
                )

            if resp.status_code != 200:
                logger.error("Open-Meteo error: %d", resp.status_code)
                return summary

            data = resp.json()
            daily_data = data.get("daily", {})

            times = daily_data.get("time", [])
            temps_min = daily_data.get("temperature_2m_min", [])
            temps_max = daily_data.get("temperature_2m_max", [])
            temps_mean = daily_data.get("temperature_2m_mean", [])
            precip = daily_data.get("precipitation_sum", [])
            wind_max = daily_data.get("wind_speed_10m_max", [])
            wind_dir = daily_data.get("wind_direction_10m_dominant", [])
            snow = daily_data.get("snow_depth_mean", [])

            summary.days_total = len(times)

            for i, t in enumerate(times):
                day = WeatherDay(
                    date=date.fromisoformat(t),
                    temp_min_c=temps_min[i] if i < len(temps_min) else None,
                    temp_max_c=temps_max[i] if i < len(temps_max) else None,
                    temp_avg_c=temps_mean[i] if i < len(temps_mean) else None,
                    precipitation_mm=precip[i] if i < len(precip) else 0,
                    wind_speed_max_ms=wind_max[i] if i < len(wind_max) else 0,
                    wind_direction_dominant=wind_dir[i] if i < len(wind_dir) else 0,
                    snow_depth_cm=snow[i] if i < len(snow) else 0,
                )
                daily.append(day)

                if day.temp_min_c and day.temp_min_c < -5:
                    summary.days_below_minus_5 += 1
                if day.temp_max_c and day.temp_max_c > 25:
                    summary.days_above_25 += 1
                if day.precipitation_mm and day.precipitation_mm > 0:
                    summary.days_with_precipitation += 1
                    summary.total_precipitation_mm += day.precipitation_mm
                if day.wind_speed_max_ms and day.wind_speed_max_ms > 12:
                    summary.days_strong_wind += 1

                if day.temp_min_c is not None:
                    summary.temp_min = min(summary.temp_min, day.temp_min_c)
                if day.temp_max_c is not None:
                    summary.temp_max = max(summary.temp_max, day.temp_max_c)
                if day.wind_speed_max_ms:
                    summary.max_wind_ms = max(summary.max_wind_ms, day.wind_speed_max_ms)

            summary.daily = daily
            summary.summary_text = self._weather_text(summary)

            logger.info(
                "Weather: %s–%s: %d days, t=[%.0f..%.0f]°C, precip=%.0fmm, wind>12m/s: %d days",
                start, end, summary.days_total,
                summary.temp_min if summary.temp_min != 100 else 0,
                summary.temp_max if summary.temp_max != -100 else 0,
                summary.total_precipitation_mm,
                summary.days_strong_wind,
            )

        except Exception as e:
            logger.error("Weather fetch failed: %s", e)

        return summary

    def _weather_text(self, s: WeatherSummary) -> str:
        """Человекочитаемая сводка погоды для ОЖР."""
        lines = [
            f"Период: {s.start_date} – {s.end_date} ({s.days_total} дней)",
            f"Температура: от {s.temp_min:.0f}°C до {s.temp_max:.0f}°C",
            f"Осадки: {s.total_precipitation_mm:.0f} мм за период ({s.days_with_precipitation} дней с осадками)",
            f"Сильный ветер (>12 м/с): {s.days_strong_wind} дней",
            f"Дни с t < -5°C (зимнее бетонирование): {s.days_below_minus_5}",
            f"Дни с t > +25°C (жара): {s.days_above_25}",
            f"Максимальный ветер: {s.max_wind_ms:.1f} м/с",
            f"Снежный покров: данные в daily",
        ]
        return "\n".join(lines)

    # ── Timezone ─────────────────────────────────────────────

    @staticmethod
    def _approx_timezone(lat: float, lon: float) -> str:
        """Приблизительный часовой пояс по координатам (для РФ)."""
        # Map longitude offset to IANA timezone
        offset_hours = round(lon / 15)

        tz_map = {
            2: "Europe/Kaliningrad",
            3: "Europe/Moscow",
            4: "Europe/Samara",
            5: "Asia/Yekaterinburg",
            6: "Asia/Omsk",
            7: "Asia/Krasnoyarsk",
            8: "Asia/Irkutsk",
            9: "Asia/Yakutsk",
            10: "Asia/Vladivostok",
            11: "Asia/Magadan",
            12: "Asia/Kamchatka",
        }

        return tz_map.get(offset_hours, "Europe/Moscow")

    # ── Climate zone (СП 131.13330.2020) ────────────────────

    @staticmethod
    def _climate_zone(lat: float, lon: float) -> Tuple[str, str]:
        """Определить климатический район по координатам."""
        for lat_min, lat_max, lon_min, lon_max, code, desc in CLIMATE_ZONES:
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                return code, desc

        # Fallback: approximate by latitude only
        if lat >= 65:
            return "IБ", "IБ (северные районы)"
        elif lat >= 60:
            return "IВ", "IВ (север европейской части)"
        elif lat >= 55:
            return "IД", "IД (центральные районы)"
        elif lat >= 50:
            return "IIБ", "IIБ (южные районы средней полосы)"
        elif lat >= 44:
            return "IIIА", "IIIА (южные районы)"
        else:
            return "IIIБ", "IIIБ (субтропики)"

    # ── Sunrise/sunset ───────────────────────────────────────

    @staticmethod
    def _sunrise_sunset_note(lat: float, d: date) -> str:
        """Приблизительное время восхода/захода для ОЖР."""
        import math

        # Day of year
        doy = d.timetuple().tm_yday

        # Approximate declination
        decl = 23.45 * math.sin(math.radians((360 / 365) * (doy - 81)))

        # Hour angle at sunrise
        lat_rad = math.radians(lat)
        decl_rad = math.radians(decl)
        cos_ha = -math.tan(lat_rad) * math.tan(decl_rad)
        cos_ha = max(-1, min(1, cos_ha))
        ha = math.degrees(math.acos(cos_ha))

        # Convert to hours
        sunrise_h = 12 - ha / 15
        sunset_h = 12 + ha / 15

        # Adjust for Moscow time (+3)
        sunrise_local = sunrise_h + 3
        sunset_local = sunset_h + 3

        return (
            f"Восход: ~{int(sunrise_local):02d}:{int((sunrise_local%1)*60):02d}, "
            f"Заход: ~{int(sunset_local):02d}:{int((sunset_local%1)*60):02d} (МСК)"
        )
