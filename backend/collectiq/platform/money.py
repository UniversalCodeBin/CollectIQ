"""Money is BIGINT minor units plus an ISO 4217 code. Never a float, never rounded, no FX."""
import re
from dataclasses import dataclass
from decimal import Decimal

_BIGINT_MIN, _BIGINT_MAX = -(2**63), 2**63 - 1
_CURRENCY = re.compile(r"[A-Z]{3}")
_AMOUNT = re.compile(r"-?\d+(\.\d+)?")

# ISO 4217 Table A.1: the codes whose minor unit is not the usual two digits.
_EXPONENT_EXCEPTIONS = {
    **dict.fromkeys(
        "BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF".split(), 0
    ),
    **dict.fromkeys("BHD IQD JOD KWD LYD OMR TND".split(), 3),
    **dict.fromkeys("CLF UYW".split(), 4),
}


# ISO 4217 Table A.1: the active alphabetic codes, including funds codes and XAU-style units.
ISO_4217_CODES = frozenset(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD
    CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL
    GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD
    KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO
    NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD
    SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV
    WST XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG
    """.split()
)


def currency_exponent(currency: str) -> int:
    return _EXPONENT_EXCEPTIONS.get(currency, 2)


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if type(self.amount_minor) is not int:
            raise TypeError("amount_minor must be an int")
        if not _BIGINT_MIN <= self.amount_minor <= _BIGINT_MAX:
            raise ValueError("amount_minor is outside the BIGINT range")
        if not _CURRENCY.fullmatch(self.currency):
            raise ValueError("currency must be three capital letters")

    @classmethod
    def from_decimal_text(cls, text: str, currency: str) -> "Money":
        """Parse plain decimal text. Too many fractional digits is an error, never a rounding."""
        if not _AMOUNT.fullmatch(text):
            raise ValueError(f"amount is not a plain decimal number: {text!r}")
        exponent = currency_exponent(currency)
        fraction = text.partition(".")[2]
        if len(fraction) > exponent:
            raise ValueError(f"{currency} allows {exponent} fractional digits, got {len(fraction)}")
        return cls(int(Decimal(text).scaleb(exponent)), currency)

    def _same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(f"cross-currency arithmetic is forbidden: {self.currency}, {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)
