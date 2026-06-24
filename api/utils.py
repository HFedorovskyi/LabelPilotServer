import treepoem
import io
import base64
import json
from datetime import datetime, timedelta
from api.i18n import tr


# --- Shared allowed sets (must mirror the frontend contract) ---

ALLOWED_BARCODE_TYPES = {
    'ean13',
    'code128',
    'qrcode',
    'databarexpandedstacked',
    'gs1qrcode',
}

GS1_BARCODE_TYPES = {'databarexpandedstacked', 'gs1qrcode'}
TWO_D_BARCODE_TYPES = {'qrcode', 'gs1qrcode'}

ALLOWED_FIELD_TYPES = {
    'constanta',
    'weight_netto_pack',
    'weight_brutto_pack',
    'weight_netto_box',
    'weight_brutto_box',
    'weight_netto_pallet',
    'weight_brutto_pallet',
    'weight_brutto_all',
    'production_date',
    'exp_date',
    'pack_number',
    'box_number',
    'pallet_number',
    'article',
    'pack_count',
    'box_count',
    'batch_number',
    'fnc1',
    'gs',
    'ai',
    'extra_data',
}

# GS1-only fields are invalid for ean13 / code128.
GS1_ONLY_FIELD_TYPES = {'ai', 'fnc1', 'gs'}

# Application Identifiers offered by the designer (kept in sync with frontend AI_OPTIONS).
ALLOWED_AI_VALUES = {'00', '01', '02', '10', '11', '17', '21', '3103'}


def safe_int(value, default=0):
    """Coerce a value to int without letting a malformed value escape via a bare except."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def validate_structure(structure):
    """Validate a barcode template structure.

    Returns a list of human-readable (Russian) error strings. An empty list means valid.
    Used both on SAVE (serializer.validate) and inside the generate endpoint before rendering.
    """
    errors = []

    if not isinstance(structure, dict):
        return [tr('barcode.structureMustBeObject')]

    barcode_type = structure.get('barcode_type')
    if barcode_type not in ALLOWED_BARCODE_TYPES:
        errors.append(
            tr('barcode.invalidType', type=barcode_type, allowed=', '.join(sorted(ALLOWED_BARCODE_TYPES)))
        )

    is_gs1 = barcode_type in GS1_BARCODE_TYPES

    fields = structure.get('fields')
    if not isinstance(fields, list) or len(fields) == 0:
        errors.append(tr('barcode.fieldsEmpty'))
        fields = []

    for index, field in enumerate(fields, start=1):
        if not isinstance(field, dict):
            errors.append(tr('barcode.fieldBadFormat', index=index))
            continue

        f_type = field.get('field_type')
        if f_type not in ALLOWED_FIELD_TYPES:
            errors.append(tr('barcode.fieldInvalidType', index=index, type=f_type))
            continue

        # GS1-only fields are not allowed on ean13/code128.
        if f_type in GS1_ONLY_FIELD_TYPES and not is_gs1:
            errors.append(
                tr('barcode.fieldGs1Only', index=index, type=f_type)
            )

        if f_type == 'constanta':
            value = field.get('value', '')
            if value is None or str(value) == '':
                errors.append(tr('barcode.constEmpty', index=index))
            elif barcode_type == 'ean13' and not str(value).isdigit():
                errors.append(
                    tr('barcode.ean13DigitsOnly', index=index)
                )

        if f_type == 'ai':
            ai_value = field.get('value', '')
            if ai_value is None or str(ai_value) == '':
                errors.append(tr('barcode.aiValueRequired', index=index))
            elif str(ai_value) not in ALLOWED_AI_VALUES:
                errors.append(
                    tr('barcode.aiInvalid', index=index, ai=ai_value, allowed=', '.join(sorted(ALLOWED_AI_VALUES)))
                )

        # length / decimalPlaces, when present and used, must be all-digits.
        for attr in ('length', 'decimalPlaces'):
            if attr in field and field.get(attr) not in (None, ''):
                if not str(field.get(attr)).isdigit():
                    errors.append(
                        tr('barcode.attrDigitsOnly', index=index, attr=attr)
                    )

        # For EAN13 every field must be digit-producing (no ai/fnc1/gs).
        if barcode_type == 'ean13' and f_type in GS1_ONLY_FIELD_TYPES:
            # Already reported above by the GS1-only check; avoid duplicate noise.
            pass

    return errors


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

        # Sample dummies kept ONLY for runtime-only fields that have no product source.
        self.runtime_dummies = {
            'pack_number': '999999999999',
            'box_number': '999999999999',
            'pallet_number': '46000000000000000',
            'pack_count': '99',
            'box_count': '99',
            'batch_number': '0000000000',
        }

        self.AI_presence = False

    def generate_image_base64(self, structure_data, product=None):
        """Render the barcode PNG.

        Returns a tuple: (image_base64, data_string, warnings).
        Raises ValueError on render-time failures (e.g. invalid EAN13 payload).
        """
        # Handle stringified JSON (legacy storage / loose callers).
        if isinstance(structure_data, str):
            try:
                structure_data = json.loads(structure_data)
            except (ValueError, TypeError):
                pass

        if isinstance(structure_data, list):
            barcode_type = 'ean13'
            fields_barcode = structure_data
        elif isinstance(structure_data, dict):
            barcode_type = structure_data.get('barcode_type', 'ean13')
            fields_barcode = structure_data.get('fields', [])
        else:
            barcode_type = 'ean13'
            fields_barcode = []

        if barcode_type in GS1_BARCODE_TYPES:
            self.AI_presence = True

        barcode_data, warnings = self.decode_structure_barcode(
            fields_barcode, product=product, barcode_type=barcode_type
        )

        if not barcode_data:
            barcode_data = "0"

        # EAN-13: payload must be exactly 12 numeric digits before the check digit.
        if barcode_type == 'ean13':
            ean_payload = barcode_data
            if len(ean_payload) == 13 and ean_payload.isdigit():
                # Already 13 digits: recompute the check digit from the first 12.
                ean_payload = ean_payload[:12]

            if not ean_payload.isdigit() or len(ean_payload) != 12:
                raise ValueError(
                    tr('barcode.ean13Need12', data=ean_payload, len=len(ean_payload))
                )

            barcode_data = self.calculate_ean13_checksum(ean_payload)

        is_2d = barcode_type in TWO_D_BARCODE_TYPES

        if is_2d:
            barcode_options = {
                'dpi': '203',
                'includetext': False,
            }
        else:
            barcode_options = {
                'dpi': '203',
                'includetext': True,
                'textfont': 'Helvetica',
                'textsize': '10',
                'textyoffset': '-10',
                'width': '5'
            }

        barcode_image = treepoem.generate_barcode(
            barcode_type=barcode_type,
            data=barcode_data,
            options=barcode_options
        )

        buffer = io.BytesIO()
        barcode_image.save(buffer, format='PNG')
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return image_base64, barcode_data, warnings

    def decode_structure_barcode(self, structure, product=None, barcode_type='ean13'):
        """Assemble the barcode data string from the structure fields.

        Returns a tuple: (assembled_string, warnings_list).
        """
        warnings = []

        if isinstance(structure, str):
            try:
                structure = json.loads(structure)
            except (ValueError, TypeError):
                return str(structure), warnings

        if not isinstance(structure, list):
            return "", warnings

        is_fixed_weight = bool(product and getattr(product, 'is_fixed_weight', False))
        warned_runtime = False

        string_for_generation = ''

        for item in structure:
            if not isinstance(item, dict):
                continue

            f_type = item.get('field_type')

            if f_type == 'constanta':
                string_for_generation += str(item.get('value', ''))

            elif f_type == 'ai':
                # GS1 (AI) parenthesis notation; BWIPP inserts the FNC1 automatically.
                string_for_generation += '(' + str(item.get('value', '')) + ')'

            elif f_type == 'fnc1':
                # For GS1 symbologies FNC1 is auto-inserted from the (AI) notation,
                # so this is a no-op marker, but we acknowledge it explicitly.
                warnings.append(tr('barcode.fnc1Noted'))

            elif f_type == 'gs':
                # Group separator -> ASCII 29.
                string_for_generation += chr(29)

            elif f_type == 'article':
                value, warn = self._resolve_article(item, product)
                string_for_generation += value
                if warn:
                    warnings.append(warn)

            elif f_type == 'pack_count':
                value, warn = self._resolve_pack_count(item, product)
                string_for_generation += value
                if warn:
                    warnings.append(warn)

            elif f_type == 'extra_data':
                value, warn = self._resolve_extra_data(item, product)
                string_for_generation += value
                if warn:
                    warnings.append(warn)

            elif f_type in self.weight_types:
                value, warn = self._resolve_weight(item, product, is_fixed_weight)
                string_for_generation += value
                if warn:
                    warnings.append(warn)

            elif f_type in self.date_types:
                string_for_generation += self._resolve_date(item, product, f_type)

            elif f_type in self.runtime_dummies:
                # Runtime-only fields with no product source: sample data + a single warning.
                length = item.get('length', '12')
                string_for_generation += self.format_runtime_dummy(f_type, length)
                if not warned_runtime:
                    warnings.append(
                        tr('barcode.previewTestData')
                    )
                    warned_runtime = True

        return string_for_generation, warnings

    # --- Field resolvers ---

    def _resolve_article(self, item, product):
        length = safe_int(item.get('length', '12'), 12)
        if product and getattr(product, 'article', None):
            raw = str(product.article)
            return self._fit_digits_or_raw(raw, length), None
        # No product source available.
        if self.AI_presence:
            data_for_barcode = (max(length, 1) - 1) * '9'
            return self.calculate_gtin14_checksum(data_for_barcode), \
                tr('barcode.articleNotSelected')
        return (max(length, 0) * '9'), tr('barcode.articleNotSelected')

    def _resolve_pack_count(self, item, product):
        length = safe_int(item.get('length', '2'), 2)
        if product and getattr(product, 'close_box_counter', None) is not None:
            raw = str(int(product.close_box_counter))
            return self._fit_number(raw, length), None
        return self._fit_number('99', length), \
            tr('barcode.packCountTestData')

    def _resolve_extra_data(self, item, product):
        field_name = item.get('value', '')
        length = safe_int(item.get('length', '12'), 12)
        if (product and isinstance(getattr(product, 'extra_data', None), dict)
                and field_name in product.extra_data):
            raw = str(product.extra_data[field_name])
            return self._fit_number(raw, length), None
        return self._fit_number('9' * max(length, 1), length), \
            tr('barcode.extraFieldTestData', field=field_name)

    def _resolve_weight(self, item, product, is_fixed_weight):
        length = item.get('length', '6')
        decimal_places = item.get('decimalPlaces', '3')
        if is_fixed_weight:
            # Product stores grams; the barcode expects kilograms.
            grams = getattr(product, 'fixed_weight_grams', 0) or 0
            kilograms = grams / 1000.0
            return self.format_weight_types(kilograms, length, decimal_places), None
        # No fixed weight available -> sampled value.
        return self.format_weight_types(99.999, length, decimal_places), \
            tr('barcode.weightTestData')

    def _resolve_date(self, item, product, f_type):
        date_format = item.get('dateFormat', 'ddMMyy')
        length = item.get('length', '6')
        if f_type == 'production_date':
            date_value = datetime.today()
        else:  # exp_date
            days = 0
            if product and getattr(product, 'exp_date', None) is not None:
                days = safe_int(product.exp_date, 0)
            date_value = datetime.today() + timedelta(days=days)
        return self.format_date_types(date_value, date_format, length)

    # --- Formatting helpers ---

    def _fit_digits_or_raw(self, raw, length):
        if length <= 0:
            return raw
        if len(raw) > length:
            return raw[:length]
        return raw.zfill(length) if raw.isdigit() else raw.rjust(length, '0')

    def _fit_number(self, raw, length):
        if length <= 0:
            return raw
        if len(raw) > length:
            return raw[:length]
        return raw.zfill(length)

    def format_runtime_dummy(self, field_type, length):
        target_len = safe_int(length, 12)
        base = self.runtime_dummies.get(field_type, '')
        if target_len <= 0:
            return base
        if len(base) > target_len:
            return base[:target_len]
        return base.zfill(target_len)

    def format_weight_types(self, value, length, decimal_places):
        length_int = safe_int(length, 6)
        decimals_int = safe_int(decimal_places, 3)
        try:
            scaled_value = round(float(value) * (10 ** decimals_int))
            scaled_str = str(int(scaled_value))
        except (TypeError, ValueError):
            scaled_str = '0'

        if length_int <= 0:
            return scaled_str
        if len(scaled_str) > length_int:
            return scaled_str[:length_int]
        return scaled_str.zfill(length_int)

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
        except (ValueError, TypeError):
            formatted_date = date_value.strftime('%d%m%y')

        length_int = safe_int(length, 6)
        if length_int <= 0:
            return formatted_date
        if len(formatted_date) > length_int:
            return formatted_date[:length_int]
        return formatted_date.zfill(length_int)

    def calculate_gtin14_checksum(self, gtin14_partial):
        if not gtin14_partial.isdigit() or len(gtin14_partial) != 13:
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
        # Caller guarantees ean12_partial is exactly 12 digits.
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
