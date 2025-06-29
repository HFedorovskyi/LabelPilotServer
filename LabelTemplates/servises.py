import requests
import os



class BaserowApiExchangeLabelTemplate:


    BASE_URL = os.getenv('BASEROW_API_URL_BASE', 'http://baserow:80/api/')
    BASEROW_API_KEY = 'G3fSTL9bi6vQ5WrA3RIUACfDCGEFomRp'

    def get_rows_label(self):
        url = f"{self.BASE_URL}database/rows/table/582/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}'}
        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            response.raise_for_status()
        except Exception as e:
            return e

    def get_row_label(self, row_id):

        url = f"{self.BASE_URL}database/rows/table/582/{row_id}/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}'}

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.json()
            response.raise_for_status()
        except Exception as e:
            return e

    def new_row_label(self, data: dict) -> dict | str:
        url = f"{self.BASE_URL}database/rows/table/582/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}',
                   'Content-Type': 'application/json'}

        try:

            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            return f'"Ошибка добавления номенклатуры в БД: {str(e)}'

    def del_row_label(self, label_id):
        url = f"{self.BASE_URL}database/rows/table/582/{label_id}/"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}'}


        try:
            response = requests.delete(url, headers=headers)
            return response
        except requests.exceptions.RequestException as e:
            print(f'{e}')
            return f'"Ошибка удаления поля с БД: {str(e)}'

    def update_row(self, label_id:str, name:str, structure: dict) -> dict | str:

        url = f"{self.BASE_URL}database/rows/table/582/{label_id}/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}',
                   'Content-Type': 'application/json'}
        json = {
            'name': name,
            'structure': structure
        }
        try:

            response = requests.patch(url, headers=headers, json=json)
            print(response.status_code)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            return f'"Ошибка добавления номенклатуры в БД: {str(e)}'




    def get_jwt_token(self):
        url = f"{self.BASE_URL}user/token-auth/"

        headers = {
            'Content-Type': 'application/json'
        }

        data = {
            "email": os.getenv('BASEROW_EMAIL'),
            "password": os.getenv('BASEROW_PASSWORD')
        }

        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()