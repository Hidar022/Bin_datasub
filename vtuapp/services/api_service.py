import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class VTUApiService:
    """Smeplug Primary (VTpass later)"""

    def __init__(self):
        self.api_key = settings.SMEPLUG_API_KEY
        self.base_url = settings.SMEPLUG_BASE_URL.rstrip('/')

    def buy_data(self, network_id, plan_id, phone, amount):
        url = f"{self.base_url}/data/purchase"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        # Force international format
        if str(phone).startswith('0'):
            phone = '234' + str(phone)[1:]

        payload = {
            "network_id": int(network_id),
            "plan_id": str(plan_id),
            "phone": phone
        }

        print("=== FINAL PAYLOAD TO SMEPLUG ===")
        print(payload)
        print("================================")

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            print(f"Status Code: {response.status_code}")
            print("Full Response:", response.text)

            # 1. Safely parse JSON so 'data' always exists
            try:
                data = response.json()
            except ValueError:
                data = {}

            # 2. Check for success (200 OK and status: True)
            if response.status_code == 200:
                if data.get('status') is True:
                    # Accessing nested data dictionary safely
                    inner_data = data.get('data', {})
                    return {
                        'success': True,
                        'provider': 'smeplug',
                        'transaction_id': inner_data.get('reference'),
                        'message': inner_data.get('msg', 'Success')
                    }

            # 3. Handle failures safely
            # Smeplug usually puts errors in 'msg' or 'message'
            error_msg = data.get('msg') or data.get('message') or f"Status {response.status_code}: Purchase failed"
            return {
                'success': False, 
                'message': error_msg
            }

        except Exception as e:
            print(f"Exception in buy_data: {e}")
            return {
                'success': False, 
                'message': 'Connection error or Timeout. Check SMEPlug dashboard.'
            }

    def buy_airtime(self, network_id, phone, amount):
        url = f"{self.base_url}/airtime/purchase"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        if str(phone).startswith('0'):
            phone = '234' + str(phone)[1:]

        payload = {
            "network_id": int(network_id),
            "amount": int(amount),
            "phone": phone
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            # === THE FIX: Always initialize data ===
            try:
                data = response.json()
            except ValueError:
                data = {}

            if response.status_code == 200:
                if data.get('status') is True:
                    inner_data = data.get('data', {})
                    return {
                        'success': True,
                        'transaction_id': inner_data.get('reference'),
                        'message': inner_data.get('msg', 'Airtime successful!')
                    }

            # Safely get the error message even if status is not 200
            error_msg = data.get('msg') or data.get('message') or f"Error {response.status_code}"
            return {'success': False, 'message': error_msg}
            
        except Exception as e:
            # This is where your 'Connection Error' was coming from
            return {'success': False, 'message': f'API Error: {str(e)}'}