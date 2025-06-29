import json
import requests
from urllib3 import request
import os

class BaserowExchangePacks:


    BASE_URL = os.getenv('BASEROW_API_URL_BASE', 'http://baserow:80/api/')
    BASEROW_API_KEY = 'G3fSTL9bi6vQ5WrA3RIUACfDCGEFomRp'


    def get_rows_packs(self):
        url = f"{self.BASE_URL}database/rows/table/584/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}'}

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            else:
                return f'Нет ответа от БД: {response.status_code}'
        except Exception as e:
            return f'"Ошибка добавления шк в БД: {str(e)}'


    def delete_row_barcode(self, pack_id):
        url = f"{self.BASE_URL}database/rows/table/584/{pack_id}/"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}',}

        try:
            response = requests.delete(url, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                return response.text
        except Exception as e:
            return e


    def save_row_pack(self, data: dict):
        url = f"{self.BASE_URL}database/rows/table/584/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}',
                   'Content-Type': 'application/json'}

        try:
            response = requests.post(url, json=data, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                return response.text
        except Exception as e:
            return e