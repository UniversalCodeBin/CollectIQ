"""Statement parser contract. Parsers read bytes into rows; they never touch the database."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

Direction = Literal["CREDIT", "DEBIT"]


class MappingError(Exception):
    """A mapped column is not in the file."""


@dataclass(frozen=True)
class StatementMapping:
    date: str
    description: str
    amount: str | None = None
    credit: str | None = None
    debit: str | None = None
    currency: str | None = None
    balance: str | None = None
    reference: str | None = None

    def columns(self) -> list[str]:
        named = [self.date, self.description, self.amount, self.credit, self.debit]
        named += [self.currency, self.balance, self.reference]
        return [c for c in named if c]

    def is_usable(self) -> bool:
        return bool(self.amount) != bool(self.credit or self.debit)


@dataclass(frozen=True)
class RawRow:
    number: int
    description: str = ""
    reference: str | None = None
    direction: Direction | None = None
    amount_minor: int | None = None
    value_date: date | None = None
    currency: str | None = None
    balance_minor: int | None = None
    error: str | None = None
    error_field: str | None = None


class StatementParser(Protocol):
    def sniff(self, data: bytes) -> bool: ...

    def parse(
        self, data: bytes, mapping: StatementMapping, date_format: str | None, currency: str
    ) -> Iterator[RawRow]: ...
