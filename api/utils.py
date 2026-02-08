import treepoem
import io
import base64
import json
from datetime import datetime

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

    def generate_image_base64(self, structure_data):
        # Handle stringified JSON
        if isinstance(structure_data, str):
            try:
                import json
                structure_data = json.loads(structure_data)
            except:
                pass

        if isinstance(structure_data, list):
            # Fallback if structure_data is just the fields list
            barcode_type = 'ean13'
            fields_barcode = structure_data
        elif isinstance(structure_data, dict):
            barcode_type = structure_data.get('barcode_type', 'ean13')
            fields_barcode = structure_data.get('fields', [])
        else:
            # Last resort fallback
            barcode_type = 'ean13'
            fields_barcode = []

        if 'databar' in barcode_type or 'gs1' in barcode_type:
            self.AI_presence = True
        
        try:
            barcode_data = self.decode_structure_barcode(fields_barcode)
            
            # If it's EAN-13 and we have 12 or 13 digits, ensure checksum is correct
            if barcode_type == 'ean13':
                if len(barcode_data) == 12:
                    barcode_data = self.calculate_ean13_checksum(barcode_data)
                elif len(barcode_data) == 13:
                    # Verify/Fix checksum if it's already 13
                    barcode_data = self.calculate_ean13_checksum(barcode_data[:12])
            
            barcode_image = treepoem.generate_barcode(
                barcode_type=barcode_type,
                data=barcode_data,
                options={
                    'dpi': '203',
                    'includetext': True,
                    'textfont': 'Helvetica',
                    'textsize': '10',
                    'textyoffset': '-10',
                    'width': '5'
                }
            )
            
            buffer = io.BytesIO()
            barcode_image.save(buffer, format='PNG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return image_base64
        except Exception as e:
            raise e

    def decode_structure_barcode(self, structure):
        if isinstance(structure, str):
            try:
                import json
                structure = json.loads(structure)
            except:
                return str(structure) # Return raw string if not JSON

        if not isinstance(structure, list):
            return ""

        string_for_generation = ''

        for item in structure:
            # Safety check for item type
            if not isinstance(item, dict):
                continue
                
            f_type = item.get('field_type')
            if f_type == 'constanta':
                string_for_generation += item.get('value', '')
            elif f_type == 'ai':
                string_for_generation += '(' + item.get('value', '') + ')'
            elif f_type in self.weight_types:
                string_for_generation += self.format_weight_types(
                    '99.999', 
                    item.get('length', '6'), 
                    item.get('decimalPlaces', '3')
                )
            elif f_type in self.date_types:
                string_for_generation += self.format_date_types(
                    datetime.today(), 
                    item.get('dateFormat', 'ddMMyy'), 
                    item.get('length', '6')
                )
            elif f_type in self.another_types:
                string_for_generation += self.format_another_types(
                    f_type, 
                    item.get('length', '12')
                )
                if self.AI_presence:
                    self.AI_presence = False

        return string_for_generation

    def format_weight_types(self, value, length, decimal_places):
        try:
            scaled_value = round(float(value) * (10 ** int(decimal_places)))
            scaled_str = str(int(scaled_value))

            if len(scaled_str) > int(length):
                return scaled_str[:int(length)]

            return scaled_str.zfill(int(length))
        except:
            return '0'.zfill(int(length))

    def format_date_types(self, date_value, date_format, length, padding_char='0'):
        format_mappings = {
            'dd': '%d',
            'MM': '%m',
            'yyyy': '%Y',
            'yy': '%y'
        }

        strftime_format = date_format
        for key, val in format_mappings.items():
            strftime_format = strftime_format.replace(key, val)

        try:
            formatted_date = date_value.strftime(strftime_format)
        except:
            formatted_date = date_value.strftime('%d%m%y')

        if len(formatted_date) > int(length):
            return formatted_date[:int(length)]
        
        return formatted_date.zfill(int(length))

    def format_another_types(self, field_type, length):
        if field_type == 'article' or field_type == 'batch_number':
            if self.AI_presence:
                data_for_barcode = (int(length) - 1) * '9'
                return self.calculate_gtin14_checksum(data_for_barcode)
            else:
                return (int(length) * '9')
        return self.another_types.get(field_type, '').zfill(int(length))

    def calculate_gtin14_checksum(self, gtin14_partial):
        if not gtin14_partial.isdigit() or len(gtin14_partial) != 13:
            # Fallback if length is not 13 for GTIN14
            if len(gtin14_partial) < 13:
                gtin14_partial = gtin14_partial.zfill(13)
            else:
                gtin14_partial = gtin14_partial[:13]

        total = 0
        for position, digit in enumerate(gtin14_partial, start=1):
            num = int(digit)
            if position % 2 == 0:
                total += num * 1
            else:
                total += num * 3

        nearest_ten = ((total + 9) // 10) * 10
        checksum = nearest_ten - total
        if checksum == 10:
            checksum = 0

        return gtin14_partial + str(checksum)

    def calculate_ean13_checksum(self, ean12_partial):
        if not ean12_partial.isdigit():
            # If it contains placeholders like {{article}}, return a valid dummy for preview
            return "4600000000008"
        
        if len(ean12_partial) < 12:
            ean12_partial = ean12_partial.zfill(12)
        elif len(ean12_partial) > 12:
            ean12_partial = ean12_partial[:12]

        total = 0
        for position, digit in enumerate(ean12_partial, start=1):
            num = int(digit)
            # Position 1,3,5 (odd) -> multiplier 1
            # Position 2,4,6 (even) -> multiplier 3
            if position % 2 == 0:
                total += num * 3
            else:
                total += num * 1

        nearest_ten = ((total + 9) // 10) * 10
        checksum = nearest_ten - total
        if checksum == 10:
            checksum = 0

        return ean12_partial + str(checksum)
