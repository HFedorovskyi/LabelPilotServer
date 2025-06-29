import json
import requests
import treepoem
from django.http import JsonResponse
import io
import base64
from datetime import datetime, timedelta
import ast
import os

class BaserowExchangeBarcode:


    BASE_URL = os.getenv('BASEROW_API_URL_BASE', 'http://baserow:80/api/')
    BASEROW_API_KEY = 'G3fSTL9bi6vQ5WrA3RIUACfDCGEFomRp'

    def new_row_barcode(self, name, structure):
        list_barcodes = self.get_rows_barcode()
        exists = any(name in d.values() for d in list_barcodes['results'])
        if exists:

            return 'Штрихкод с таким именем уже существует.'

        url = f"{self.BASE_URL}database/rows/table/583/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}',
                   'Content-Type': 'application/json'}

        data = {
            'name': name,
            'structure': str(structure['barcode_structure']),

        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            if response.status_code == 200:
                return response.json()
            else:
                return f'Нет ответа от БД: {response.status_code}'
        except Exception as e:
            return f'"Ошибка добавления шк в БД: {str(e)}'

    def get_rows_barcode(self):
        url = f"{self.BASE_URL}database/rows/table/583/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}'}

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            else:
                return f'Нет ответа от БД: {response.status_code}'
        except Exception as e:
            return f'"Ошибка добавления шк в БД: {str(e)}'


    def delete_row_barcode(self, name):
        url = f"{self.BASE_URL}database/rows/table/583/?user_field_names=true"
        headers = {'Authorization': f'Token {self.BASEROW_API_KEY}',}


class BarcodeGenerator:

    def __init__(self):
        self.weight_types = [
            'weight_netto_pack',
            'weight_brutto_pack',
            'weight_netto_box',
            'weight_brutto_box',
            'weight_netto_pallet',
            'weight_brutto_pallet',
            'weight_brutto_all'
        ]

        self.date_types = [
            'production_date',
            'exp_date'
        ]

        self.another_types = {
            'pack_number': '999999999999',
            'box_number': '999999999999',
            'pallet_number': '46000000000000000',
            'article': '',
            'pack_count': '99',
            'box_count': '99',
            'batch_number': '',
        }

        self.AI_presence = False



    def generate_barcode(self, request, *args, **kwargs):
        data = json.loads(request.body.decode('utf-8'))

        if not data:
            return JsonResponse({'error': 'Не переданы данные для генерации ШК'}, status=400)

        filtred_data = ast.literal_eval(data.get('structure', ''))


        barcode_type = filtred_data.get('barcode_type', 'ean13')
        if 'databar' in barcode_type or 'gs1' in barcode_type:
            self.AI_presence = True
        fields_barcode = filtred_data.get('fields', '')



        try:
            # Генерация штрихкода
            barcode_image = treepoem.generate_barcode(
                barcode_type=barcode_type,
                data=self.decode_structure_barcode(fields_barcode),
                options={'dpi': '203',
                         'includetext': True,
                         'textfont': 'Helvetica',  # Шрифт текста
                         'textsize': '10',  # Размер шрифта
                         'textyoffset': '-10',
                         'width': '5'
                         }
            )
            # Сохранение изображения в SVG формат в буфер
            buffer = io.BytesIO()
            barcode_image.save(buffer, format='PNG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return JsonResponse({'success': True, 'png': image_base64})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    def decode_structure_barcode(self, structure):
        string_for_generation = ''


        for item in structure:
            if item['field_type'] == 'constanta':
                string_for_generation += item['value']
            elif item['field_type'] == 'ai':
                string_for_generation += '(' + item['value'] + ')'
            elif item['field_type'] in self.weight_types:
                string_for_generation += self.format_weigt_types('99.999', item['length'], item['decimalPlaces'])
            elif item['field_type'] in self.date_types:
                string_for_generation += self.format_date_types(datetime.today(), item['dateFormat'], item['length'])
            elif item['field_type'] in self.another_types:
                string_for_generation += self.format_another_types(item['field_type'], item['length'])
                if self.AI_presence:
                    self.AI_presence = False

        return string_for_generation


    def format_weigt_types(self, value, length, decimal_places):
        scaled_value = round(float(value) * (10 ** int(decimal_places))) # Усечение
        scaled_str = str(int(scaled_value))


        if len(scaled_str) > int(length):
            raise ValueError("Значение слишком велико для заданной длины.")

        weight_for_barcode = scaled_str.zfill(int(length))
        return weight_for_barcode


    def format_date_types(self, date_value, date_format, length, padding_char='0'):
        format_mappings = {
            'dd': '%d',
            'MM': '%m',
            'yyyy': '%Y',
            'yy': '%y'
        }

        # Замена пользовательских маркеров на маркеры strftime
        strftime_format = date_format
        for key, value in format_mappings.items():
            strftime_format = strftime_format.replace(key, value)

        # Шаг 2: Форматирование даты
        try:
            formatted_date = date_value.strftime(strftime_format)
        except Exception as e:
            raise ValueError(f"Неверный формат даты: {date_format}. Ошибка: {e}")

        # Шаг 3: Проверка длины и дополнение
        if len(formatted_date) > int(length):
            raise ValueError(
                f"Отформатированная дата '{formatted_date}' длиной {len(formatted_date)} превышает заданную длину {length}."
            )
        elif len(formatted_date) < int(length):
            padding_length = int(length) - len(formatted_date)
            padding = padding_char * padding_length
            data_for_barcode = padding + formatted_date  # Дополнение слева
        else:
            data_for_barcode = formatted_date  # Длина соответствует требуемой

        return data_for_barcode

    def format_another_types(self, field_type, length):
        if field_type == 'article' or field_type == 'batch_number':
            if self.AI_presence:
                data_for_barcode = (int(length)) * '9'
                data_for_barcode_with_csum = self.calculate_gtin14_checksum(data_for_barcode)
                return data_for_barcode_with_csum
            else:
                data_for_barcode = int(length) * '9'
                return data_for_barcode
        return self.another_types[field_type]

    def calculate_gtin14_checksum(self, gtin14_partial):
        """
        Рассчитывает контрольную цифру для номера GTIN-14 и возвращает полный номер.

        :param gtin14_partial: Строка из первых 13 цифр GTIN-14.
        :return: Строка из 14 цифр GTIN-14 с контрольной цифрой.
        :raises ValueError: Если входные данные некорректны.
        """
        if not gtin14_partial.isdigit() or len(gtin14_partial) != 13:
            raise ValueError("Входные данные должны содержать ровно 13 цифр.")

        total = 0
        for position, digit in enumerate(gtin14_partial, start=1):
            num = int(digit)
            if position % 2 == 0:
                total += num * 1  # Чётные позиции
            else:
                total += num * 3  # Нечётные позиции

        # Определяем ближайшее большее или равное число, кратное 10
        nearest_ten = ((total + 9) // 10) * 10
        checksum = nearest_ten - total
        if checksum == 10:
            checksum = 0

        return gtin14_partial + str(checksum)