"""
shared — общие компоненты, переиспользуемые несколькими модулями АСД.

GOSTStampGenerator — используется IS Generator и ППР Generator.
"""
from src.core.services.shared.gost_stamp import GOSTStampGenerator

__all__ = ["GOSTStampGenerator"]
