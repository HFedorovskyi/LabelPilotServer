import requests
import os

class BaserowApiExchange():


    BASE_URL = os.getenv('BASEROW_API_URL_BASE', 'http://baserow:80/api/')
    BASEROW_API_KEY = 'G3fSTL9bi6vQ5WrA3RIUACfDCGEFomRp'



    def get_fields(self):
        url = f'{self.BASE_URL}database/fields/table/581/'
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}' }
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:

                return response.json()
            response.raise_for_status()
        except Exception as e:
            return e

    def new_field(self, field_name: dict) -> dict|str:
        jwt_token = self.get_jwt_token()

        url = f'{self.BASE_URL}database/fields/table/581/'

        headers = {
            'Authorization': f'JWT {jwt_token['token']}',
            'Content-Type': 'application/json'
        }

        data = {
            'name': field_name,
            'type': 'text'
        }

        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            return f'"Ошибка добавления поля в БД: {str(e)}'



    def update_field(self, data: dict) -> dict|str:
        id_nomenclature = int(data['id'])
        url = f'{self.BASE_URL}database/rows/table/581/{id_nomenclature}/?user_field_names=true'
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}',
                   'Content-Type': 'application/json'}
        article = data.get('article')
        jwt_token = self.get_jwt_token()
        response = requests.get(
            f'{self.BASE_URL}database/rows/table/581/'
                f"?user_field_names=true"
                f"&filter__field_5527__equal={article}",
            headers={'Authorization': f'JWT {jwt_token['token']}'})
        if response.status_code == 200:
            results = response.json().get('results', [])
            for item in results:
                if item['id'] != id_nomenclature:
                    return 'Ошибка: Запись с таким артикулом уже существует.'


        try:
            response = requests.patch(url, headers=headers, json=data)

            if response.status_code == 200 :
                return response.json()
        except requests.exceptions.RequestException as e:
            return f'"Ошибка добавления номенклатуры в БД: {str(e)}'

    def delete_field_nomenclature_api(self, field_id):
        jwt_token = self.get_jwt_token()
        url = f'{self.BASE_URL}database/fields/{field_id}/'

        headers = {
            'Authorization': f'JWT {jwt_token['token']}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.delete(url, headers=headers)
            result = response.json()
            return result
        except requests.exceptions.RequestException as e:
            return f'"Ошибка удаления поля с БД: {str(e)}'


    def get_rows(self):
        url = f'{self.BASE_URL}database/rows/table/581/?user_field_names=true'
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}' }
        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            response.raise_for_status()
        except Exception as e:
            return e



    def new_row(self, data: dict) -> dict|str:
        url = f'{self.BASE_URL}database/rows/table/581/?user_field_names=true'
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}',
                   'Content-Type': 'application/json'}
        article = data.get('article')


        response = requests.get(f'{self.BASE_URL}database/rows/table/581/?user_field_names=true&filter__field_5527__equal={article}',
                                headers={'Authorization': f'Token {self.BASEROW_API_KEY}'})


        if response.status_code == 200 and response.json().get('count') > 0:
            return 'Ошибка: Запись с таким артикулом уже существует.'

        try:

            response = requests.post(url, headers=headers, json=data)
            print(response.json())
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            return f'"Ошибка добавления номенклатуры в БД: {str(e)}'





    def get_nomenclature_table(self):

        url = f"{self.BASE_URL}database/fields/table/581/"

        headers = {
            'Authorization': f'Token {self.BASEROW_API_KEY}'
        }

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return f'Ошибка получения таблицы "{str(e)}"'

    def delete_row_nomnenclature(self, id_nomenclature):
        jwt_token = self.get_jwt_token()
        row_id = id_nomenclature.get('nomenclatureId', None)
        url = f'{self.BASE_URL}database/rows/table/581/{row_id}/'


        headers = {
            'Authorization': f'JWT {jwt_token['token']}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.delete(url, headers=headers)
            result = response.json()
            return result
        except requests.exceptions.RequestException as e:
            return f'"Ошибка удаления поля с БД: {str(e)}'




    def get_jwt_token(self):
        url = f'{self.BASE_URL}user/token-auth/'

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