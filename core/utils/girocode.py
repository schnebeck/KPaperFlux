"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           core/utils/girocode.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Utility to generate SEPA Credit Transfer (EPC-QR) payloads,
                commonly known as "GiroCode".
------------------------------------------------------------------------------
"""

import logging
from typing import Optional

logger = logging.getLogger("KPaperFlux.GiroCode")


class GiroCodeGenerator:
    """
    Generates the payload string for EPC-QR codes (SEPA Credit Transfer).
    Reference: https://de.wikipedia.org/wiki/EPC-QR-Code
    """

    @staticmethod
    def generate_payload(
        recipient_name: str,
        iban: str,
        amount: float,
        purpose: str = "",
        bic: str = "",
        reference: Optional[str] = None
    ) -> str:
        """
        Generates the raw text payload for a GiroCode.
        
        Args:
            recipient_name: Name of the payee (max 70 chars).
            iban: IBAN of the payee.
            amount: Amount in EUR.
            purpose: Remittance information (text, max 140 chars).
            bic: BIC of the payee (optional for SEPA, but often included).
            reference: Structured reference (RF-Standard, optional).
            
        Returns:
            The EPC-QR compliant payload string.
        """
        # 1. Validation & Formatting
        recipient_name = recipient_name.strip()[:70]
        iban = iban.replace(" ", "").upper()
        bic = bic.replace(" ", "").upper()
        amount_str = f"{float(amount):.2f}"
        purpose = purpose.strip()[:140]
        
        # 2. Construct Payload Lines
        lines = [
            "BCD",               # Service Tag
            "002",               # Version 2 (supports structured/unstructured)
            "1",                 # Character Set (UTF-8)
            "SCT",               # Identification code (SCT = SEPA Credit Transfer)
            bic,                 # BIC
            recipient_name,      # Payee Name
            iban,                # Payee IBAN
            f"EUR{amount_str}",  # Amount prefixed with currency
            "",                  # Purpose Code (optional)
            reference or "",     # Structured Reference (alternative to purpose)
            "" if reference else purpose, # Unstructured Remittance text
            ""                   # Information (optional)
        ]
        
        return "\n".join(lines)

    @staticmethod
    def get_qr_image(payload: str):
        """
        Attempts to generate a PIL Image for the QR code.
        Requires 'qrcode' and 'Pillow' packages.
        """
        try:
            import qrcode
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(payload)
            qr.make(fit=True)
            return qr.make_image(fill_color="black", back_color="white")
        except ImportError:
            logger.warning("Package 'qrcode' not found. Cannot generate image.")
            return None
