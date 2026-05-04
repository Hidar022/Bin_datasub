import requests
import logging
from django.conf import settings
from datetime import datetime

logger = logging.getLogger(__name__)

class VTUApiService:
    """Main Service - Smeplug Primary, VTpass Backup"""

    def __init__(self):
        self.smeplug_key = settings.SMEPLUG_API_KEY
        self.smeplug_url = settings.SMEPLUG_BASE_URL

        self.vtpass_key = settings.VTPASS_API_KEY
        self.vtpass_secret = settings.VTPASS_SECRET_KEY
        self.vtpass_url = settings.VTPASS_BASE_URL

    # ===================== SMEPLUG =====================
    def _smeplug_post(self, endpoint, payload):
        url = f"{self.smeplug_url}/{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.smeplug_key}',
            'Content-Type': 'application/json'
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            logger.info(f"Smeplug {endpoint} -> {resp.status_code}")
            return resp.json() if resp.text else None
        except Exception as e:
            logger.error(f"Smeplug Error: {e}")
            return None

    # ===================== VTPASS (Backup) =====================
    def _vtpass_post(self, endpoint, payload):
        if not self.vtpass_key:
            return None
        url = f"{self.vtpass_url}/{endpoint}"
        headers = {
            'api-key': self.vtpass_key,
            'secret-key': self.vtpass_secret,
            'Content-Type': 'application/json'
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            return resp.json()
        except Exception as e:
            logger.error(f"VTpass Error: {e}")
            return None

    # ===================== MAIN BUY DATA =====================
    def buy_data(self, network, phone, plan_code, amount):
        payload = {
            "network": network.lower(),
            "phone": phone,
            "plan": plan_code,
            "amount": str(amount)
        }

        # Try Smeplug First
        result = self._smeplug_post("data", payload)

        if result and result.get('status') == 'success':
            return {
                'success': True,
                'provider': 'smeplug',
                'transaction_id': result.get('transaction_id'),
                'message': 'Data purchase successful'
            }

        # If Smeplug fails, try VTpass (if keys exist)
        if self.vtpass_key:
            logger.warning("Smeplug failed → Trying VTpass backup")
            vt_payload = {
                "serviceID": network.lower(),
                "phone": phone,
                "amount": str(amount),
                "request_id": f"VTU{int(datetime.now().timestamp())}"
            }
            vt_result = self._vtpass_post("pay", vt_payload)
            if vt_result and vt_result.get('response_code') == "0000":
                return {
                    'success': True,
                    'provider': 'vtpass',
                    'transaction_id': vt_result.get('request_id'),
                    'message': 'Data purchase successful (VTpass)'
                }

        return {
            'success': False,
            'message': 'Service temporarily unavailable. Please try again shortly.'
        }