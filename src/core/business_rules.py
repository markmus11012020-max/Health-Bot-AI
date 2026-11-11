"""Deterministic business rules for pricing, delivery and upsell fallback.

LLMs occasionally omit or truncate the manager block.  These rules provide a
safe, explainable fallback so the manager still receives the correct next step.
They are also useful for exact arithmetic: the model must not invent prices.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[\s\u00a0]\d{3})+|\d{4,6})(?!\d)")


@dataclass(frozen=True)
class UpsellRecommendation:
    text: str
    needs_upsell: bool


class UpsellAdvisor:
    """Rule-based upsell and delivery advisor for the OCX product line."""

    DETOX_PRICE = 4500
    VITAMIN_PRICE = 2100
    VITAMIN_DISCOUNT = 0.20
    FREE_DELIVERY_FROM = 5000
    DELIVERY_PRICE = 300

    def recommend(
        self,
        *,
        crm_context: str = "",
        client_message: str = "",
        manager_tip: str = "",
    ) -> UpsellRecommendation:
        # If the model produced a meaningful manager block, keep it.
        if manager_tip and "не сформирована" not in manager_tip.lower():
            return UpsellRecommendation(
                text=manager_tip,
                needs_upsell="допродажа не требуется" not in manager_tip.lower(),
            )

        text = f"{crm_context}\n{client_message}".lower()
        amount = self._extract_amount(text)
        detox_context = "детокс" in text or (
            amount is not None and amount <= self.DETOX_PRICE and "комплекс" in text
        )

        if detox_context:
            discounted = int(self.VITAMIN_PRICE * (1 - self.VITAMIN_DISCOUNT))
            total = self.DETOX_PRICE + discounted
            return UpsellRecommendation(
                text=(
                    "Предложите «О-комплекс Витамин-Буст» со скидкой 20% — "
                    f"{self._money(discounted)}. Итог заказа: {self._money(total)}, "
                    f"доставка бесплатная (порог {self._money(self.FREE_DELIVERY_FROM)})."
                ),
                needs_upsell=True,
            )

        if "доставка" in text and amount is not None and amount < self.FREE_DELIVERY_FROM:
            return UpsellRecommendation(
                text=(
                    f"Доставка составит {self._money(self.DELIVERY_PRICE)}. "
                    f"Предложите добрать заказ до {self._money(self.FREE_DELIVERY_FROM)} "
                    f"— например, «Витамин-Буст» {self._money(self.VITAMIN_PRICE)}."
                ),
                needs_upsell=True,
            )

        return UpsellRecommendation(text="Допродажа не требуется", needs_upsell=False)

    @staticmethod
    def _money(value: int) -> str:
        return f"{value:,}".replace(",", " ") + " ₽"

    @staticmethod
    def _extract_amount(text: str) -> int | None:
        match = _AMOUNT_RE.search(text)
        if not match:
            return None
        try:
            return int(match.group(1).replace(" ", "").replace("\u00a0", ""))
        except ValueError:
            return None
